"""Service layer managing Google OAuth 2.0 PKCE flow, MultiFernet encrypted tokens, refresh, and complete disconnect."""

from datetime import datetime, timedelta, timezone
import logging
import secrets
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.authentication.encryption import TokenEncryptor
from app.authentication.google_oauth import GoogleOAuthClient
from app.authentication.security import generate_pkce_pair
from app.core.config import Settings
from app.core.exceptions import (
    NotFoundError,
    OAuthError,
    OAuthRevokedError,
    ServiceNotConfiguredError,
)
from app.core.logging import mask_email
from app.models.enums import AccountSyncStatus
from app.models.schemas import ConnectedAccountResponse, GoogleConnectResponse
from app.services.auth_service import account_doc_to_response
from app.services.db_utils import parse_object_id
from app.services.security_audit_service import SecurityAuditService

logger = logging.getLogger("jobmail.oauth_service")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class GoogleOAuthService:
    """Coordinates PKCE OAuth state validation, encrypted token storage, refresh, and disconnection."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        oauth_client: GoogleOAuthClient,
    ) -> None:
        self._db = db
        self._settings = settings
        self._oauth = oauth_client
        self._encryptor = TokenEncryptor(settings.encryption_key_list)
        self._audit = SecurityAuditService(db)

    async def create_connect_url(
        self, user_id: str, *, ip_address: str | None = None
    ) -> GoogleConnectResponse:
        if not self._settings.google_oauth_client_configured:
            raise ServiceNotConfiguredError(
                "Google OAuth 2.0 credentials are not configured yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env."
            )

        state = secrets.token_urlsafe(32)
        code_verifier, code_challenge = generate_pkce_pair()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(
            minutes=self._settings.oauth_state_expire_minutes
        )
        await self._db.oauth_states.insert_one(
            {
                "state": state,
                "user_id": user_id,
                "encrypted_code_verifier": self._encryptor.encrypt(code_verifier),
                "created_at": now,
                "expires_at": expires_at,
            }
        )
        auth_url = self._oauth.build_authorization_url(
            state, code_challenge=code_challenge
        )
        await self._audit.log_event(
            event_type="GOOGLE_OAUTH_INITIATED",
            user_id=user_id,
            ip_address=ip_address,
            summary="Initiated Google OAuth 2.0 read-only PKCE authorization.",
        )
        return GoogleConnectResponse(
            authorization_url=auth_url,
            state=state,
            pkce_enabled=True,
        )

    async def handle_callback(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None = None,
        error_description: str | None = None,
        ip_address: str | None = None,
    ) -> ConnectedAccountResponse:
        if not state:
            raise OAuthError("Missing OAuth state parameter.")

        state_doc = await self._db.oauth_states.find_one_and_delete({"state": state})
        if not state_doc:
            await self._audit.log_event(
                event_type="OAUTH_REPLAY_OR_INVALID_STATE",
                severity="high",
                ip_address=ip_address,
                alert=True,
                summary="Rejected OAuth callback with invalid or already-used state.",
            )
            raise OAuthError("Invalid or already-used OAuth state. Please try connecting again.")

        expires_at = _as_utc(state_doc["expires_at"])
        if expires_at <= datetime.now(timezone.utc):
            raise OAuthError("OAuth session expired. Please initiate Connect Gmail again.")

        if error:
            detail = error_description or error
            raise OAuthError(f"Google authorization was not completed: {detail}")

        if not code:
            raise OAuthError("Missing OAuth authorization code.")

        if not self._settings.google_oauth_client_configured:
            raise ServiceNotConfiguredError(
                "Google OAuth 2.0 credentials are not configured on the server."
            )

        user_id = str(state_doc["user_id"])
        code_verifier: str | None = None
        if state_doc.get("encrypted_code_verifier"):
            code_verifier = self._encryptor.decrypt(
                str(state_doc["encrypted_code_verifier"])
            )

        token_payload = await self._oauth.exchange_code_for_tokens(
            code, code_verifier=code_verifier
        )
        profile = await self._oauth.fetch_gmail_profile(token_payload.access_token)

        now = datetime.now(timezone.utc)
        access_expires_at = now + timedelta(seconds=token_payload.expires_in)
        encrypted_access = self._encryptor.encrypt(token_payload.access_token)

        existing = await self._db.connected_accounts.find_one(
            {"user_id": user_id, "email_address": profile.email_address}
        )

        if token_payload.refresh_token:
            encrypted_refresh = self._encryptor.encrypt(token_payload.refresh_token)
        elif existing and existing.get("encrypted_refresh_token"):
            encrypted_refresh = str(existing["encrypted_refresh_token"])
        else:
            raise OAuthError(
                "Google did not return a refresh token. Please remove prior access in your Google Account permissions and try again."
            )

        scopes = [s for s in token_payload.scope.split() if s]
        update_fields: dict[str, object] = {
            "provider": "google",
            "encrypted_access_token": encrypted_access,
            "access_token_expires_at": access_expires_at,
            "encrypted_refresh_token": encrypted_refresh,
            "scopes": scopes,
            "sync_status": AccountSyncStatus.PENDING.value,
            "status_message": "Connected via Google OAuth 2.0 (read-only).",
        }
        if profile.history_id:
            update_fields["history_id"] = profile.history_id

        doc = await self._db.connected_accounts.find_one_and_update(
            {"user_id": user_id, "email_address": profile.email_address},
            {
                "$set": update_fields,
                "$setOnInsert": {
                    "user_id": user_id,
                    "email_address": profile.email_address,
                    "connected_at": now,
                    "last_synced_at": None,
                },
            },
            upsert=True,
            return_document=True,
        )
        await self._audit.log_event(
            event_type="GOOGLE_ACCOUNT_CONNECTED",
            user_id=user_id,
            ip_address=ip_address,
            summary=f"Connected Gmail account {mask_email(profile.email_address)}.",
        )
        return account_doc_to_response(doc)

    async def get_valid_access_token(
        self,
        user_id: str,
        account_id: str,
        *,
        force_refresh: bool = False,
    ) -> str:
        """Return a valid Gmail access token, automatically refreshing if expired."""
        oid = parse_object_id(account_id, "Connected account")
        doc = await self._db.connected_accounts.find_one(
            {"_id": oid, "user_id": user_id}
        )
        if not doc:
            raise NotFoundError("Connected account not found.")

        if doc.get("sync_status") == AccountSyncStatus.REVOKED.value:
            raise OAuthRevokedError(
                "Gmail access was revoked or expired. Please reconnect this account."
            )

        now = datetime.now(timezone.utc)
        expires_raw = doc.get("access_token_expires_at")
        enc_access = doc.get("encrypted_access_token")
        if (
            not force_refresh
            and enc_access
            and isinstance(expires_raw, datetime)
            and _as_utc(expires_raw) > now + timedelta(seconds=60)
        ):
            return self._encryptor.decrypt(str(enc_access))

        enc_refresh = doc.get("encrypted_refresh_token")
        if not enc_refresh:
            await self._mark_revoked(
                oid, user_id, "Missing refresh token. Please reconnect this account."
            )
            raise OAuthRevokedError(
                "Gmail credentials are missing or expired. Please reconnect this account."
            )

        refresh_token = self._encryptor.decrypt(str(enc_refresh))
        try:
            refreshed = await self._oauth.refresh_access_token(refresh_token)
        except OAuthRevokedError as exc:
            await self._mark_revoked(oid, user_id, exc.detail)
            raise

        new_expires_at = now + timedelta(seconds=refreshed.expires_in)
        update_doc: dict[str, object] = {
            "encrypted_access_token": self._encryptor.encrypt(refreshed.access_token),
            "access_token_expires_at": new_expires_at,
        }
        if refreshed.refresh_token:
            update_doc["encrypted_refresh_token"] = self._encryptor.encrypt(
                refreshed.refresh_token
            )
        if doc.get("sync_status") == AccountSyncStatus.ERROR.value:
            update_doc["sync_status"] = AccountSyncStatus.PENDING.value
            update_doc["status_message"] = "Access token refreshed."

        await self._db.connected_accounts.update_one(
            {"_id": oid, "user_id": user_id},
            {"$set": update_doc},
        )
        return refreshed.access_token

    async def verify_account_connection(
        self, user_id: str, account_id: str
    ) -> ConnectedAccountResponse:
        """Verify token health against Gmail API, refreshing expired tokens if necessary."""
        oid = parse_object_id(account_id, "Connected account")
        access_token = await self.get_valid_access_token(user_id, account_id)
        try:
            profile = await self._oauth.fetch_gmail_profile(access_token)
        except Exception:
            access_token = await self.get_valid_access_token(
                user_id, account_id, force_refresh=True
            )
            profile = await self._oauth.fetch_gmail_profile(access_token)

        doc = await self._db.connected_accounts.find_one_and_update(
            {"_id": oid, "user_id": user_id},
            {
                "$set": {
                    "email_address": profile.email_address,
                    "status_message": "OAuth connection active (read-only).",
                }
            },
            return_document=True,
        )
        if not doc:
            raise NotFoundError("Connected account not found.")
        return account_doc_to_response(doc)

    async def disconnect_account(
        self,
        user_id: str,
        account_id: str,
        *,
        purge_emails: bool = True,
        ip_address: str | None = None,
    ) -> None:
        """Revoke Google OAuth tokens (best effort), remove credentials, and optionally purge associated emails."""
        oid = parse_object_id(account_id, "Connected account")
        doc = await self._db.connected_accounts.find_one(
            {"_id": oid, "user_id": user_id}
        )
        if not doc:
            raise NotFoundError("Connected account not found.")

        await self.revoke_account_tokens_for_doc(doc)

        await self._db.connected_accounts.delete_one(
            {"_id": oid, "user_id": user_id}
        )
        if purge_emails:
            email_ids = [
                str(e["_id"])
                async for e in self._db.emails.find(
                    {"user_id": user_id, "account_id": account_id},
                    projection={"_id": 1},
                )
            ]
            await self._db.emails.delete_many(
                {"user_id": user_id, "account_id": account_id}
            )
            await self._db.sync_history.delete_many(
                {"user_id": user_id, "account_id": account_id}
            )
            if email_ids:
                await self._db.notifications.delete_many(
                    {"user_id": user_id, "email_id": {"$in": email_ids}}
                )
                await self._db.classification_feedback.delete_many(
                    {"user_id": user_id, "email_id": {"$in": email_ids}}
                )

        await self._audit.log_event(
            event_type="GOOGLE_ACCOUNT_DISCONNECTED",
            user_id=user_id,
            ip_address=ip_address,
            summary=(
                f"Disconnected Gmail account {mask_email(doc.get('email_address'))} "
                f"(purge_emails={purge_emails})."
            ),
        )

    async def revoke_account_tokens_for_doc(self, doc: dict) -> None:
        """Decrypt stored tokens for a connected account document and revoke with Google."""
        token_to_revoke = ""
        for field in ("encrypted_refresh_token", "encrypted_access_token"):
            enc_val = doc.get(field)
            if enc_val:
                try:
                    token_to_revoke = self._encryptor.decrypt(str(enc_val))
                    break
                except Exception:
                    continue
        if token_to_revoke:
            await self._oauth.revoke_token(token_to_revoke)

    async def _mark_revoked(self, oid, user_id: str, message: str) -> None:
        await self._db.connected_accounts.update_one(
            {"_id": oid, "user_id": user_id},
            {
                "$set": {
                    "sync_status": AccountSyncStatus.REVOKED.value,
                    "status_message": message,
                    "encrypted_access_token": "",
                    "encrypted_refresh_token": "",
                }
            },
        )
        await self._audit.log_event(
            event_type="GOOGLE_TOKEN_REFRESH_FAILED",
            severity="medium",
            user_id=user_id,
            summary=f"OAuth token refresh failed/revoked for account {oid}.",
        )
