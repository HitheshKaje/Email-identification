"""Multi-account incremental Gmail synchronization, encryption at rest, cooldowns, and deduplication."""

from datetime import datetime, timedelta, timezone
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from app.authentication.encryption import TokenEncryptor
from app.authentication.google_oauth import GoogleOAuthClient
from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    NotFoundError,
    OAuthRevokedError,
    RateLimitError,
)
from app.core.logging import mask_email
from app.models.enums import AccountSyncStatus
from app.models.schemas import (
    ClassificationPredictRequest,
    SyncHistoryItem,
    SyncResponse,
)
from app.notifications.fcm_service import FCMDispatcher
from app.services.classification_service import ClassificationService
from app.services.db_utils import parse_object_id
from app.services.gmail_client import GmailClient, HistoryExpiredError
from app.services.google_oauth_service import GoogleOAuthService
from app.services.notification_service import NotificationService

logger = logging.getLogger("jobmail.gmail_sync")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class GmailSyncService:
    """Synchronizes new Gmail messages across one or all connected accounts."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        oauth_client: GoogleOAuthClient,
        gmail_client: GmailClient,
    ) -> None:
        self._db = db
        self._settings = settings
        self._encryptor = TokenEncryptor(settings.encryption_key_list)
        self._oauth_service = GoogleOAuthService(db, settings, oauth_client)
        self._gmail = gmail_client
        self._classifier = ClassificationService(db, settings)
        self._notifications = NotificationService(
            db, fcm_dispatcher=FCMDispatcher(settings.firebase_credentials_path)
        )

    async def sync_user_accounts(
        self,
        user_id: str,
        *,
        account_id: str | None = None,
        enforce_cooldown: bool = True,
    ) -> SyncResponse:
        if account_id:
            oid = parse_object_id(account_id, "Connected account")
            doc = await self._db.connected_accounts.find_one(
                {"_id": oid, "user_id": user_id}
            )
            if not doc:
                raise NotFoundError("Connected account not found.")
            accounts = [doc]
        else:
            accounts = await self._db.connected_accounts.find(
                {
                    "user_id": user_id,
                    "sync_status": {"$ne": AccountSyncStatus.REVOKED.value},
                }
            ).to_list(length=50)

        if not accounts:
            return SyncResponse(
                status="no_accounts",
                message="No active connected Gmail accounts found. Connect or reconnect a Gmail account first.",
                synced_accounts=0,
            )

        cooldown = (
            self._settings.effective_sync_cooldown_seconds
            if enforce_cooldown
            else 0
        )
        if cooldown > 0:
            now = datetime.now(timezone.utc)
            for account in accounts:
                last_synced = account.get("last_synced_at")
                if isinstance(last_synced, datetime):
                    elapsed = (now - _as_utc(last_synced)).total_seconds()
                    if 0 <= elapsed < cooldown:
                        wait_s = max(1, int(cooldown - elapsed))
                        raise RateLimitError(
                            f"Sync ran recently. Wait {wait_s}s before synchronizing again.",
                            retry_after=wait_s,
                        )

        synced_accounts = 0
        failed_accounts = 0
        new_messages = 0
        skipped_duplicates = 0
        last_error: str | None = None

        for account in accounts:
            acc_id_str = str(account["_id"])
            email_addr = str(account.get("email_address") or "")
            started_at = datetime.now(timezone.utc)
            try:
                added, skipped = await self._sync_single_account(user_id, account)
                synced_accounts += 1
                new_messages += added
                skipped_duplicates += skipped
                await self._record_sync_history(
                    user_id=user_id,
                    account_id=acc_id_str,
                    email_address=email_addr,
                    started_at=started_at,
                    status="SYNCED",
                    new_messages=added,
                    skipped_duplicates=skipped,
                )
            except OAuthRevokedError as exc:
                failed_accounts += 1
                last_error = exc.detail
                logger.info("OAuth revoked for account %s", acc_id_str)
                await self._record_sync_history(
                    user_id=user_id,
                    account_id=acc_id_str,
                    email_address=email_addr,
                    started_at=started_at,
                    status="REVOKED",
                    error_message=exc.detail,
                )
            except AppError as exc:
                failed_accounts += 1
                last_error = exc.detail
                await self._db.connected_accounts.update_one(
                    {"_id": account["_id"]},
                    {
                        "$set": {
                            "sync_status": AccountSyncStatus.ERROR.value,
                            "status_message": exc.detail,
                        }
                    },
                )
                await self._record_sync_history(
                    user_id=user_id,
                    account_id=acc_id_str,
                    email_address=email_addr,
                    started_at=started_at,
                    status="ERROR",
                    error_message=exc.detail,
                )
            except Exception:
                failed_accounts += 1
                last_error = "Unexpected synchronization failure."
                await self._db.connected_accounts.update_one(
                    {"_id": account["_id"]},
                    {
                        "$set": {
                            "sync_status": AccountSyncStatus.ERROR.value,
                            "status_message": last_error,
                        }
                    },
                )
                await self._record_sync_history(
                    user_id=user_id,
                    account_id=acc_id_str,
                    email_address=email_addr,
                    started_at=started_at,
                    status="ERROR",
                    error_message=last_error,
                )

        if synced_accounts == 0 and failed_accounts > 0:
            raise AppError(
                last_error or "Failed to synchronize Gmail accounts.",
                status_code=502,
            )

        status_str = "partial" if failed_accounts > 0 else "ok"
        message = (
            f"Synced {synced_accounts} account(s): {new_messages} new email(s), {skipped_duplicates} duplicate(s) skipped."
        )
        if failed_accounts > 0 and last_error:
            message += f" ({failed_accounts} failed: {last_error})"

        return SyncResponse(
            status=status_str,
            message=message,
            synced_accounts=synced_accounts,
            new_messages=new_messages,
            skipped_duplicates=skipped_duplicates,
            failed_accounts=failed_accounts,
        )

    async def _sync_single_account(
        self, user_id: str, account: dict
    ) -> tuple[int, int]:
        acc_oid = account["_id"]
        acc_id = str(acc_oid)

        await self._db.connected_accounts.update_one(
            {"_id": acc_oid},
            {"$set": {"sync_status": AccountSyncStatus.SYNCING.value}},
        )

        access_token = await self._oauth_service.get_valid_access_token(
            user_id, acc_id
        )

        try:
            message_ids, latest_history_id = await self._collect_candidate_ids(
                access_token, account
            )
        except AuthenticationError:
            access_token = await self._oauth_service.get_valid_access_token(
                user_id, acc_id, force_refresh=True
            )
            message_ids, latest_history_id = await self._collect_candidate_ids(
                access_token, account
            )

        existing_ids = set()
        if message_ids:
            cursor = self._db.emails.find(
                {
                    "account_id": acc_id,
                    "gmail_message_id": {"$in": message_ids},
                },
                projection={"gmail_message_id": 1},
            )
            async for existing_doc in cursor:
                existing_ids.add(str(existing_doc["gmail_message_id"]))

        new_count = 0
        skipped_count = 0

        for msg_id in message_ids:
            if msg_id in existing_ids:
                skipped_count += 1
                continue

            try:
                parsed = await self._gmail.get_message(access_token, msg_id)
            except AuthenticationError:
                access_token = await self._oauth_service.get_valid_access_token(
                    user_id, acc_id, force_refresh=True
                )
                parsed = await self._gmail.get_message(access_token, msg_id)

            if parsed.history_id and (
                latest_history_id is None
                or _history_gt(parsed.history_id, latest_history_id)
            ):
                latest_history_id = parsed.history_id

            classification = await self._classifier.predict(
                ClassificationPredictRequest(
                    subject=parsed.subject,
                    body=parsed.body_preview,
                    sender=parsed.sender,
                )
            )

            email_doc = {
                "user_id": user_id,
                "account_id": acc_id,
                "gmail_message_id": parsed.gmail_message_id,
                "thread_id": parsed.thread_id,
                "encrypted_sender": self._encryptor.encrypt_optional(parsed.sender),
                "encrypted_subject": self._encryptor.encrypt_optional(parsed.subject),
                "encrypted_body_preview": self._encryptor.encrypt_optional(
                    parsed.body_preview
                ),
                "received_at": parsed.received_at,
                "category": classification.category.value,
                "confidence": classification.confidence,
                "encrypted_company_name": self._encryptor.encrypt_optional(
                    classification.company_name
                ),
                "encrypted_job_role": self._encryptor.encrypt_optional(
                    classification.job_role
                ),
                "is_read": False,
                "has_attachments": parsed.has_attachments,
                "attachment_names": parsed.attachment_names,
            }
            try:
                insert_res = await self._db.emails.insert_one(email_doc)
                new_count += 1
                existing_ids.add(msg_id)
                await self._notifications.notify_for_new_email(
                    user_id=user_id,
                    email_id=str(insert_res.inserted_id),
                    category=classification.category,
                    company_name=classification.company_name,
                    job_role=classification.job_role,
                )
            except DuplicateKeyError:
                skipped_count += 1

        now = datetime.now(timezone.utc)
        update_doc: dict[str, object] = {
            "sync_status": AccountSyncStatus.SYNCED.value,
            "last_synced_at": now,
            "status_message": f"Last sync fetched {new_count} new message(s).",
        }
        if latest_history_id:
            update_doc["history_id"] = latest_history_id

        await self._db.connected_accounts.update_one(
            {"_id": acc_oid},
            {"$set": update_doc},
        )
        await self._enforce_user_retention(user_id)
        return new_count, skipped_count

    async def _enforce_user_retention(self, user_id: str) -> None:
        oid = parse_object_id(user_id, "User")
        user_doc = await self._db.users.find_one(
            {"_id": oid}, {"data_retention_days": 1}
        )
        retention_days = int(
            (user_doc or {}).get(
                "data_retention_days", self._settings.default_data_retention_days
            )
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        expired = [
            str(d["_id"])
            async for d in self._db.emails.find(
                {"user_id": user_id, "received_at": {"$lt": cutoff}},
                projection={"_id": 1},
            )
        ]
        if expired:
            await self._db.emails.delete_many(
                {"user_id": user_id, "received_at": {"$lt": cutoff}}
            )
            await self._db.notifications.delete_many(
                {"user_id": user_id, "email_id": {"$in": expired}}
            )

    async def _collect_candidate_ids(
        self, access_token: str, account: dict
    ) -> tuple[list[str], str | None]:
        history_id = account.get("history_id")
        last_synced = account.get("last_synced_at")
        max_messages = self._settings.gmail_sync_max_messages
        page_size = self._settings.gmail_sync_page_size

        if history_id and last_synced is not None:
            try:
                return await self._collect_via_history(
                    access_token,
                    start_history_id=str(history_id),
                    max_messages=max_messages,
                )
            except HistoryExpiredError:
                logger.info(
                    "Gmail historyId expired for %s; falling back to timestamp query.",
                    mask_email(account.get("email_address")),
                )

        query: str | None = None
        if isinstance(last_synced, datetime):
            after_epoch = max(0, int(_as_utc(last_synced).timestamp()) - 300)
            query = f"after:{after_epoch}"

        return await self._collect_via_messages_list(
            access_token,
            query=query,
            page_size=page_size,
            max_messages=max_messages,
        )

    async def _collect_via_history(
        self,
        access_token: str,
        *,
        start_history_id: str,
        max_messages: int,
    ) -> tuple[list[str], str | None]:
        collected: list[str] = []
        seen: set[str] = set()
        page_token: str | None = None
        latest_history_id: str | None = start_history_id

        while len(collected) < max_messages:
            page = await self._gmail.list_history(
                access_token,
                start_history_id=start_history_id,
                page_token=page_token,
            )
            if page.history_id:
                latest_history_id = page.history_id
            for msg_id in page.added_message_ids:
                if msg_id not in seen:
                    seen.add(msg_id)
                    collected.append(msg_id)
                    if len(collected) >= max_messages:
                        break
            if not page.next_page_token:
                break
            page_token = page.next_page_token

        return collected, latest_history_id

    async def _collect_via_messages_list(
        self,
        access_token: str,
        *,
        query: str | None,
        page_size: int,
        max_messages: int,
    ) -> tuple[list[str], str | None]:
        collected: list[str] = []
        seen: set[str] = set()
        page_token: str | None = None

        while len(collected) < max_messages:
            remaining = max_messages - len(collected)
            page = await self._gmail.list_messages(
                access_token,
                page_token=page_token,
                max_results=min(page_size, remaining),
                query=query,
            )
            for msg_id in page.message_ids:
                if msg_id not in seen:
                    seen.add(msg_id)
                    collected.append(msg_id)
            if not page.next_page_token:
                break
            page_token = page.next_page_token

        return collected, None

    async def _record_sync_history(
        self,
        *,
        user_id: str,
        account_id: str,
        email_address: str,
        started_at: datetime,
        status: str,
        new_messages: int = 0,
        skipped_duplicates: int = 0,
        error_message: str | None = None,
    ) -> None:
        await self._db.sync_history.insert_one(
            {
                "user_id": user_id,
                "account_id": account_id,
                "email_address": mask_email(email_address),
                "encrypted_email_address": self._encryptor.encrypt_optional(email_address),
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc),
                "status": status,
                "new_messages": new_messages,
                "skipped_duplicates": skipped_duplicates,
                "error_message": error_message,
            }
        )

    async def get_sync_history(
        self, user_id: str, limit: int = 25
    ) -> list[SyncHistoryItem]:
        cursor = (
            self._db.sync_history.find({"user_id": user_id})
            .sort("started_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        items: list[SyncHistoryItem] = []
        for doc in docs:
            addr = doc.get("email_address", "")
            if doc.get("encrypted_email_address"):
                try:
                    addr = self._encryptor.decrypt(str(doc["encrypted_email_address"]))
                except Exception:
                    pass
            items.append(
                SyncHistoryItem(
                    id=str(doc["_id"]),
                    account_id=doc["account_id"],
                    email_address=str(addr),
                    started_at=doc["started_at"],
                    finished_at=doc["finished_at"],
                    status=doc["status"],
                    new_messages=int(doc.get("new_messages", 0)),
                    skipped_duplicates=int(doc.get("skipped_duplicates", 0)),
                    error_message=doc.get("error_message"),
                )
            )
        return items


def _history_gt(candidate: str, current: str) -> bool:
    try:
        return int(candidate) > int(current)
    except ValueError:
        return candidate > current
