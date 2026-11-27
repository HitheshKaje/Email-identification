"""Service layer managing Google OAuth 2.0 PKCE flow, MultiFernet encrypted tokens, refresh, and complete disconnect."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlparse
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from app.authentication.encryption import TokenEncryptor
from app.authentication.google_oauth import GoogleOAuthClient
from app.authentication.security import generate_pkce_pair, hash_opaque_token
from app.core.config import Settings
from app.core.exceptions import (
    ExternalServiceError,
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

_IN_FLIGHT_WAIT_SECONDS = 5.0
_IN_FLIGHT_POLL_INTERVAL_SECONDS = 0.15
_CONSUMED_STATE_RETENTION_MINUTES = 5


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _state_fingerprint(state: str) -> str:
    """Return a non-reversible 8-char SHA-256 prefix for safe diagnostic logs."""
    return hashlib.sha256(state.encode("utf-8")).hexdigest()[:8]


def _safe_redirect_target(redirect_uri: str) -> str:
    """Return scheme://host/path without query parameters or credentials."""
    parsed = urlparse(redirect_uri.strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}"
    return "[invalid-redirect-uri]"


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
        state_fp = _state_fingerprint(state)
        code_verifier, code_challenge = generate_pkce_pair()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(
            minutes=self._settings.oauth_state_expire_minutes
        )
        await self._db.oauth_states.insert_one(
            {
                "state": state,
                "state_fingerprint": state_fp,
                "user_id": user_id,
                "encrypted_code_verifier": self._encryptor.encrypt(code_verifier),
                "status": "pending",
                "created_at": now,
                "expires_at": expires_at,
            }
        )
        auth_url = self._oauth.build_authorization_url(
            state, code_challenge=code_challenge
        )
        logger.info(
            "OAuth state created state_fp=%s user_id=%s redirect_uri=%s expires_in_min=%d",
            state_fp,
            user_id,
            _safe_redirect_target(self._settings.google_redirect_uri),
            self._settings.oauth_state_expire_minutes,
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
            logger.warning(
                "OAuth callback rejected reason=missing_state has_code=%s has_error=%s",
                bool(code),
                bool(error),
            )
            raise OAuthError("Missing OAuth state parameter.")

        state_fp = _state_fingerprint(state)
        now = datetime.now(timezone.utc)

        # Preserve pending OAuth state if an incomplete probe arrives with neither code nor error.
        if not error and not code:
            return await self._handle_missing_code_probe(
                state=state, state_fp=state_fp, now=now, ip_address=ip_address
            )

        code_hash = hash_opaque_token(code) if code else ""
        pending_filter = {
            "state": state,
            "$or": [{"status": "pending"}, {"status": {"$exists": False}}],
        }
        claimed_doc = await self._db.oauth_states.find_one_and_update(
            pending_filter,
            {
                "$set": {
                    "status": "processing",
                    "code_hash": code_hash,
                    "processing_started_at": now,
                }
            },
            return_document=ReturnDocument.BEFORE,
        )
        if not claimed_doc:
            return await self._handle_unclaimed_state(
                state=state,
                state_fp=state_fp,
                code=code,
                code_hash=code_hash,
                error=error,
                now=now,
                ip_address=ip_address,
            )

        expires_at = _as_utc(claimed_doc["expires_at"])
        if expires_at <= now:
            await self._finalize_state(
                state=state,
                status="expired",
                expires_at=expires_at,
                consumed_at=now,
            )
            logger.warning("OAuth callback rejected reason=expired state_fp=%s", state_fp)
            raise OAuthError("OAuth session expired. Please initiate Connect Gmail again.")

        if error:
            detail = error_description or error
            err_msg = f"Google authorization was not completed: {detail}"
            await self._finalize_state(
                state=state,
                status="failed",
                expires_at=expires_at,
                consumed_at=now,
                error_detail=err_msg,
            )
            logger.warning(
                "OAuth callback failed reason=provider_error state_fp=%s provider_error=%s",
                state_fp,
                error,
            )
            raise OAuthError(err_msg)

        if not self._settings.google_oauth_client_configured:
            await self._release_state_to_pending(state=state)
            raise ServiceNotConfiguredError(
                "Google OAuth 2.0 credentials are not configured on the server."
            )

        user_id = str(claimed_doc["user_id"])
        code_verifier: str | None = None
        if claimed_doc.get("encrypted_code_verifier"):
            code_verifier = self._encryptor.decrypt(
                str(claimed_doc["encrypted_code_verifier"])
            )

        try:
            assert code is not None
            token_payload = await self._oauth.exchange_code_for_tokens(
                code, code_verifier=code_verifier
            )
            profile = await self._oauth.fetch_gmail_profile(token_payload.access_token)

            done_at = datetime.now(timezone.utc)
            access_expires_at = done_at + timedelta(seconds=token_payload.expires_in)
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
                        "connected_at": done_at,
                        "last_synced_at": None,
                    },
                },
                upsert=True,
                return_document=True,
            )
        except ExternalServiceError as exc:
            # Preserve pending state only if Google servers were transiently unreachable before consumption.
            if datetime.now(timezone.utc) < expires_at:
                await self._release_state_to_pending(state=state)
                logger.warning(
                    "OAuth callback transient error; state preserved state_fp=%s user_id=%s exc=%s",
                    state_fp,
                    user_id,
                    type(exc).__name__,
                )
            else:
                await self._finalize_state(
                    state=state,
                    status="expired",
                    expires_at=expires_at,
                    consumed_at=datetime.now(timezone.utc),
                )
            raise
        except OAuthError as exc:
            await self._finalize_state(
                state=state,
                status="failed",
                expires_at=expires_at,
                consumed_at=datetime.now(timezone.utc),
                error_detail=exc.detail,
            )
            logger.warning(
                "OAuth callback failed state_fp=%s user_id=%s status_code=%d",
                state_fp,
                user_id,
                exc.status_code,
            )
            raise
        except Exception as exc:
            await self._finalize_state(
                state=state,
                status="failed",
                expires_at=expires_at,
                consumed_at=datetime.now(timezone.utc),
                error_detail="Unexpected error completing Google OAuth callback.",
            )
            logger.error(
                "OAuth callback unexpected error state_fp=%s user_id=%s exc=%s",
                state_fp,
                user_id,
                type(exc).__name__,
            )
            raise

        await self._finalize_state(
            state=state,
            status="completed",
            expires_at=expires_at,
            consumed_at=done_at,
            connected_account_id=str(doc["_id"]),
        )
        logger.info(
            "OAuth callback succeeded state_fp=%s user_id=%s account=%s",
            state_fp,
            user_id,
            mask_email(profile.email_address),
        )
        await self._audit.log_event(
            event_type="GOOGLE_ACCOUNT_CONNECTED",
            user_id=user_id,
            ip_address=ip_address,
            summary=f"Connected Gmail account {mask_email(profile.email_address)}.",
        )
        return account_doc_to_response(doc)

    async def _handle_missing_code_probe(
        self,
        *,
        state: str,
        state_fp: str,
        now: datetime,
        ip_address: str | None,
    ) -> ConnectedAccountResponse:
        existing = await self._db.oauth_states.find_one({"state": state})
        if not existing:
            logger.warning(
                "OAuth callback rejected reason=not_found_missing_code state_fp=%s",
                state_fp,
            )
            await self._log_invalid_state_audit(ip_address=ip_address)
            raise OAuthError("Invalid or already-used OAuth state. Please try connecting again.")

        expires_at = _as_utc(existing["expires_at"])
        if expires_at <= now:
            if existing.get("status") in (None, "pending"):
                await self._finalize_state(
                    state=state,
                    status="expired",
                    expires_at=expires_at,
                    consumed_at=now,
                )
            logger.warning(
                "OAuth callback rejected reason=expired_missing_code state_fp=%s",
                state_fp,
            )
            raise OAuthError("OAuth session expired. Please initiate Connect Gmail again.")

        if existing.get("status") not in (None, "pending"):
            logger.warning(
                "OAuth callback rejected reason=already_used_missing_code state_fp=%s prior_status=%s",
                state_fp,
                existing.get("status"),
            )
            await self._log_invalid_state_audit(ip_address=ip_address)
            raise OAuthError("Invalid or already-used OAuth state. Please try connecting again.")

        logger.warning(
            "OAuth callback missing authorization code; pending state preserved state_fp=%s",
            state_fp,
        )
        raise OAuthError("Missing OAuth authorization code.")

    async def _handle_unclaimed_state(
        self,
        *,
        state: str,
        state_fp: str,
        code: str | None,
        code_hash: str,
        error: str | None,
        now: datetime,
        ip_address: str | None,
    ) -> ConnectedAccountResponse:
        existing = await self._db.oauth_states.find_one({"state": state})
        if not existing:
            logger.warning(
                "OAuth callback rejected reason=not_found state_fp=%s has_code=%s has_error=%s",
                state_fp,
                bool(code),
                bool(error),
            )
            await self._log_invalid_state_audit(ip_address=ip_address)
            raise OAuthError("Invalid or already-used OAuth state. Please try connecting again.")

        current_status = existing.get("status")
        expires_at = _as_utc(existing["expires_at"])
        if current_status == "expired" or (
            expires_at <= now and current_status in (None, "pending", "processing")
        ):
            await self._finalize_state(
                state=state,
                status="expired",
                expires_at=expires_at,
                consumed_at=now,
            )
            logger.warning(
                "OAuth callback rejected reason=expired state_fp=%s prior_status=%s",
                state_fp,
                current_status,
            )
            raise OAuthError("OAuth session expired. Please initiate Connect Gmail again.")

        if current_status == "processing":
            existing_code_hash = str(existing.get("code_hash") or "")
            if (
                error is None
                and code
                and existing_code_hash
                and hmac.compare_digest(existing_code_hash, code_hash)
            ):
                logger.info(
                    "OAuth callback coalescing concurrent in-flight request state_fp=%s",
                    state_fp,
                )
                return await self._await_in_flight_callback(state=state, state_fp=state_fp)

            logger.warning(
                "OAuth callback rejected reason=code_mismatch_in_flight state_fp=%s has_error=%s",
                state_fp,
                bool(error),
            )
            await self._log_invalid_state_audit(ip_address=ip_address)
            raise OAuthError("Invalid or already-used OAuth state. Please try connecting again.")

        consumed_raw = existing.get("consumed_at")
        consumed_ago = (
            f"{(now - _as_utc(consumed_raw)).total_seconds():.1f}s"
            if isinstance(consumed_raw, datetime)
            else "unknown"
        )
        logger.warning(
            "OAuth callback rejected reason=already_used state_fp=%s prior_status=%s consumed_ago=%s",
            state_fp,
            current_status,
            consumed_ago,
        )
        await self._log_invalid_state_audit(ip_address=ip_address)
        raise OAuthError("Invalid or already-used OAuth state. Please try connecting again.")

    async def _await_in_flight_callback(
        self, *, state: str, state_fp: str
    ) -> ConnectedAccountResponse:
        deadline = asyncio.get_running_loop().time() + _IN_FLIGHT_WAIT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(_IN_FLIGHT_POLL_INTERVAL_SECONDS)
            doc = await self._db.oauth_states.find_one({"state": state})
            if not doc:
                raise OAuthError(
                    "Invalid or already-used OAuth state. Please try connecting again."
                )
            st = doc.get("status")
            if st == "completed":
                acc_id_raw = str(doc.get("connected_account_id") or "")
                user_id = str(doc.get("user_id") or "")
                if acc_id_raw and ObjectId.is_valid(acc_id_raw):
                    acc_doc = await self._db.connected_accounts.find_one(
                        {"_id": ObjectId(acc_id_raw), "user_id": user_id}
                    )
                    if acc_doc:
                        logger.info(
                            "OAuth callback coalesced successfully state_fp=%s",
                            state_fp,
                        )
                        return account_doc_to_response(acc_doc)
                raise OAuthError("Connected Gmail account could not be loaded.")
            if st == "failed":
                raise OAuthError(
                    str(
                        doc.get("error_detail")
                        or "Google authorization failed. Please try connecting again."
                    )
                )
            if st == "expired":
                raise OAuthError("OAuth session expired. Please initiate Connect Gmail again.")
            if st == "pending":
                raise ExternalServiceError(
                    "Unable to reach Google OAuth servers. Please try again."
                )

        logger.warning(
            "OAuth callback timed out awaiting in-flight completion state_fp=%s",
            state_fp,
        )
        raise OAuthError(
            "Gmail connection is still completing. Return to Connected Accounts and refresh."
        )

    async def _finalize_state(
        self,
        *,
        state: str,
        status: str,
        expires_at: datetime,
        consumed_at: datetime,
        connected_account_id: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        retention_deadline = min(
            expires_at,
            consumed_at + timedelta(minutes=_CONSUMED_STATE_RETENTION_MINUTES),
        )
        update_fields: dict[str, object] = {
            "status": status,
            "consumed_at": consumed_at,
            "expires_at": retention_deadline,
        }
        if connected_account_id is not None:
            update_fields["connected_account_id"] = connected_account_id
        if error_detail is not None:
            update_fields["error_detail"] = error_detail[:300]
        await self._db.oauth_states.update_one(
            {"state": state},
            {
                "$set": update_fields,
                "$unset": {"encrypted_code_verifier": ""},
            },
        )

    async def _release_state_to_pending(self, *, state: str) -> None:
        await self._db.oauth_states.update_one(
            {"state": state, "status": "processing"},
            {
                "$set": {"status": "pending"},
                "$unset": {"code_hash": "", "processing_started_at": ""},
            },
        )

    async def _log_invalid_state_audit(self, *, ip_address: str | None) -> None:
        await self._audit.log_event(
            event_type="OAUTH_REPLAY_OR_INVALID_STATE",
            severity="high",
            ip_address=ip_address,
            alert=True,
            summary="Rejected OAuth callback with invalid or already-used state.",
        )

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
