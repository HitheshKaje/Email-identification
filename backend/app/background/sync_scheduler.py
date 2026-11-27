"""Bounded periodic background Gmail synchronization scheduler."""

import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.authentication.google_oauth import GoogleOAuthClient
from app.core.config import Settings
from app.models.enums import AccountSyncStatus
from app.services.gmail_client import GmailClient
from app.services.gmail_sync_service import GmailSyncService

logger = logging.getLogger("jobmail.sync_scheduler")


class BackgroundSyncScheduler:
    """Runs periodic email synchronization across active connected accounts."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        oauth_client: GoogleOAuthClient | None = None,
        gmail_client: GmailClient | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._oauth = oauth_client or GoogleOAuthClient(settings)
        self._gmail = gmail_client or GmailClient()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Started background Gmail sync scheduler (interval=%ss).",
            self._settings.auto_sync_interval_seconds,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Stopped background Gmail sync scheduler.")

    async def run_once(self) -> dict[str, int]:
        """Execute a single bounded sync pass across all users with active accounts."""
        if not self._settings.google_oauth_client_configured:
            return {"users_processed": 0, "synced_accounts": 0, "new_messages": 0}

        user_ids: list[str] = await self._db.connected_accounts.distinct(
            "user_id",
            {"sync_status": {"$ne": AccountSyncStatus.REVOKED.value}},
        )

        sync_service = GmailSyncService(
            self._db,
            self._settings,
            self._oauth,
            self._gmail,
        )
        users_processed = 0
        total_accounts = 0
        total_new = 0

        for user_id in user_ids:
            try:
                res = await sync_service.sync_user_accounts(
                    str(user_id), enforce_cooldown=False
                )
                users_processed += 1
                total_accounts += res.synced_accounts
                total_new += res.new_messages
            except Exception as exc:
                logger.warning(
                    "Background sync error for user %s: %s",
                    user_id,
                    type(exc).__name__,
                )

        return {
            "users_processed": users_processed,
            "synced_accounts": total_accounts,
            "new_messages": total_new,
        }

    async def _run_loop(self) -> None:
        interval = max(60, self._settings.auto_sync_interval_seconds)
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                await self.run_once()
