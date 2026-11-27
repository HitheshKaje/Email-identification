"""User privacy controls: data retention, JSON export, Gmail data purge, and full account erasure."""

from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.authentication.google_oauth import GoogleOAuthClient, REQUIRED_GMAIL_SCOPE
from app.authentication.security import verify_password
from app.core.config import Settings
from app.core.exceptions import AppError, AuthenticationError, NotFoundError
from app.models.schemas import PrivacyOverviewResponse
from app.services.db_utils import parse_object_id
from app.services.email_service import EmailService
from app.services.google_oauth_service import GoogleOAuthService
from app.services.security_audit_service import SecurityAuditService


class PrivacyService:
    """Implements privacy overview, retention updates, Gmail data purge, data export, and account deletion."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        oauth_client: GoogleOAuthClient | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._oauth_client = oauth_client or GoogleOAuthClient(settings)
        self._audit = SecurityAuditService(db)

    async def get_overview(self, user_id: str) -> PrivacyOverviewResponse:
        oid = parse_object_id(user_id, "User")
        user_doc = await self._db.users.find_one(
            {"_id": oid}, {"data_retention_days": 1}
        )
        if not user_doc:
            raise NotFoundError("User not found.")

        retention_days = int(
            user_doc.get("data_retention_days", self._settings.default_data_retention_days)
        )
        emails_stored = await self._db.emails.count_documents({"user_id": user_id})
        accounts_count = await self._db.connected_accounts.count_documents({"user_id": user_id})
        notifs_count = await self._db.notifications.count_documents({"user_id": user_id})

        return PrivacyOverviewResponse(
            data_retention_days=retention_days,
            gmail_scope=REQUIRED_GMAIL_SCOPE,
            emails_stored=emails_stored,
            connected_accounts=accounts_count,
            notifications_stored=notifs_count,
            encryption_at_rest="MultiFernet AES-CBC + HMAC-SHA256 for OAuth tokens and sensitive email fields",
            limited_use_notice=(
                "JobMail accesses Gmail strictly with read-only permissions for your personal career inbox. "
                "Your email content is never shared across users or used to train generalized AI models."
            ),
        )

    async def update_retention(self, user_id: str, retention_days: int) -> PrivacyOverviewResponse:
        oid = parse_object_id(user_id, "User")
        await self._db.users.update_one(
            {"_id": oid},
            {"$set": {"data_retention_days": retention_days}},
        )
        await self.purge_expired_emails_for_user(user_id, retention_days)
        await self._audit.log_event(
            event_type="DATA_RETENTION_UPDATED",
            user_id=user_id,
            summary=f"Updated email retention period to {retention_days} days.",
        )
        return await self.get_overview(user_id)

    async def purge_expired_emails_for_user(
        self, user_id: str, retention_days: int
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        expired_ids = [
            str(doc["_id"])
            async for doc in self._db.emails.find(
                {"user_id": user_id, "received_at": {"$lt": cutoff}},
                projection={"_id": 1},
            )
        ]
        if not expired_ids:
            return 0
        await self._db.emails.delete_many(
            {"user_id": user_id, "received_at": {"$lt": cutoff}}
        )
        await self._db.notifications.delete_many(
            {"user_id": user_id, "email_id": {"$in": expired_ids}}
        )
        await self._db.classification_feedback.delete_many(
            {"user_id": user_id, "email_id": {"$in": expired_ids}}
        )
        return len(expired_ids)

    async def export_user_data(self, user_id: str) -> dict[str, object]:
        oid = parse_object_id(user_id, "User")
        user_doc = await self._db.users.find_one(
            {"_id": oid},
            projection={
                "hashed_password": 0,
                "mfa_secret_enc": 0,
                "mfa_recovery_hashes": 0,
                "mfa_pending_secret_enc": 0,
                "mfa_pending_recovery_hashes": 0,
            },
        )
        if not user_doc:
            raise NotFoundError("User not found.")

        accounts = await self._db.connected_accounts.find(
            {"user_id": user_id},
            projection={"encrypted_access_token": 0, "encrypted_refresh_token": 0},
        ).to_list(length=50)
        emails_res = await EmailService(self._db, self._settings).list_emails(
            user_id, limit=500, include_other=True
        )
        notifications = await self._db.notifications.find(
            {"user_id": user_id}
        ).sort("created_at", -1).to_list(length=500)

        await self._audit.log_event(
            event_type="PRIVACY_DATA_EXPORTED",
            user_id=user_id,
            summary="User exported personal JobMail data.",
        )

        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user": {
                "id": str(user_doc["_id"]),
                "name": user_doc.get("name"),
                "email": user_doc.get("email"),
                "email_verified": bool(user_doc.get("email_verified", False)),
                "mfa_enabled": bool(user_doc.get("mfa_enabled", False)),
                "data_retention_days": user_doc.get("data_retention_days", 180),
                "created_at": user_doc["created_at"].isoformat(),
            },
            "connected_accounts": [
                {
                    "id": str(a["_id"]),
                    "email_address": a.get("email_address"),
                    "provider": a.get("provider", "google"),
                    "sync_status": a.get("sync_status"),
                    "connected_at": a["connected_at"].isoformat() if a.get("connected_at") else None,
                    "last_synced_at": a["last_synced_at"].isoformat() if a.get("last_synced_at") else None,
                }
                for a in accounts
            ],
            "emails": [item.model_dump(mode="json") for item in emails_res.items],
            "notifications": [
                {
                    "id": str(n["_id"]),
                    "email_id": n.get("email_id"),
                    "title": n.get("title"),
                    "message": n.get("message"),
                    "category": n.get("category"),
                    "created_at": n["created_at"].isoformat() if n.get("created_at") else None,
                    "is_read": bool(n.get("is_read", False)),
                }
                for n in notifications
            ],
        }

    async def delete_gmail_data(
        self, user_id: str, *, disconnect_accounts: bool = False, ip_address: str | None = None
    ) -> dict[str, int]:
        emails_del = await self._db.emails.delete_many({"user_id": user_id})
        notifs_del = await self._db.notifications.delete_many({"user_id": user_id})
        fb_del = await self._db.classification_feedback.delete_many({"user_id": user_id})
        hist_del = await self._db.sync_history.delete_many({"user_id": user_id})

        disconnected = 0
        if disconnect_accounts:
            oauth_svc = GoogleOAuthService(self._db, self._settings, self._oauth_client)
            accounts = await self._db.connected_accounts.find({"user_id": user_id}).to_list(length=50)
            for acc in accounts:
                await oauth_svc.revoke_account_tokens_for_doc(acc)
                disconnected += 1
            await self._db.connected_accounts.delete_many({"user_id": user_id})
        else:
            await self._db.connected_accounts.update_many(
                {"user_id": user_id},
                {"$set": {"last_synced_at": None}, "$unset": {"history_id": ""}},
            )

        await self._audit.log_event(
            event_type="PRIVACY_DATA_DELETED",
            severity="medium",
            user_id=user_id,
            ip_address=ip_address,
            summary=(
                f"Deleted {emails_del.deleted_count} synced email(s) "
                f"(disconnect_accounts={disconnect_accounts})."
            ),
        )
        return {
            "emails_deleted": int(emails_del.deleted_count),
            "notifications_deleted": int(notifs_del.deleted_count),
            "feedback_deleted": int(fb_del.deleted_count),
            "accounts_disconnected": disconnected,
            "sync_history_deleted": int(hist_del.deleted_count),
        }

    async def delete_account(
        self,
        *,
        user_id: str,
        password: str,
        confirm_text: str,
        ip_address: str | None = None,
    ) -> None:
        if confirm_text.strip().upper() != "DELETE":
            raise AppError("Confirmation phrase must equal 'DELETE'.", status_code=422)

        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one({"_id": oid})
        if not doc or not verify_password(password, doc["hashed_password"]):
            raise AuthenticationError("Invalid password.")

        await self.delete_gmail_data(
            user_id, disconnect_accounts=True, ip_address=ip_address
        )
        await self._db.sessions.delete_many({"user_id": user_id})
        await self._db.verification_tokens.delete_many({"user_id": user_id})
        await self._db.device_tokens.delete_many({"user_id": user_id})
        await self._db.oauth_states.delete_many({"user_id": user_id})
        await self._db.users.delete_one({"_id": oid})

        await self._audit.log_event(
            event_type="ACCOUNT_DELETED",
            severity="high",
            user_id=user_id,
            ip_address=ip_address,
            alert=True,
            summary="User permanently deleted account and all associated Gmail data.",
        )
