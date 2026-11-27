"""Phase 7 & 8 tests for background sync scheduler, sync history, notifications, and dashboard totals."""

from datetime import datetime, timedelta, timezone
import httpx
import pytest
from app.authentication.encryption import TokenEncryptor
from app.authentication.google_oauth import GoogleOAuthClient, REQUIRED_GMAIL_SCOPE
from app.background.sync_scheduler import BackgroundSyncScheduler
from app.core.config import Settings
from app.models.enums import AccountSyncStatus, EmailCategory
from app.services.gmail_client import GmailClient


def _bg_settings() -> Settings:
    return Settings(
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="jobmail_test",
        jwt_secret_key="test-only-jwt-secret-key-at-least-32-bytes-long",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        google_oauth_scopes=REQUIRED_GMAIL_SCOPE,
        auto_sync_enabled=True,
        auto_sync_interval_seconds=900,
    )


async def _noop_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_background_scheduler_sync_creates_notifications_and_sync_history(client):
    ac, db = client
    cfg = _bg_settings()
    encryptor = TokenEncryptor(cfg.token_encryption_key)

    reg = await ac.post(
        "/auth/register",
        json={
            "name": "Scheduler User",
            "email": "sched@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert reg.status_code == 201
    jwt_token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    now = datetime.now(timezone.utc)
    await db.connected_accounts.insert_one(
        {
            "user_id": user_id,
            "email_address": "sched.jobs@gmail.com",
            "provider": "google",
            "encrypted_access_token": encryptor.encrypt("valid-token"),
            "access_token_expires_at": now + timedelta(minutes=30),
            "encrypted_refresh_token": encryptor.encrypt("refresh-token"),
            "connected_at": now,
            "last_synced_at": None,
            "sync_status": AccountSyncStatus.PENDING.value,
        }
    )

    def gmail_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gmail/v1/users/me/messages":
            return httpx.Response(
                200,
                json={"messages": [{"id": "bg-1"}, {"id": "bg-2"}]},
            )
        if request.url.path == "/gmail/v1/users/me/messages/bg-1":
            return httpx.Response(
                200,
                json={
                    "id": "bg-1",
                    "threadId": "t-1",
                    "historyId": "700",
                    "snippet": "Interview invite",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Infosys HR <careers@infosys.com>"},
                            {"name": "Subject", "value": "Shortlisted for Software Developer Interview at Infosys"},
                            {"name": "Date", "value": "Thu, 26 Nov 2026 12:00:00 +0000"},
                        ],
                        "internalDate": "1795694400000",
                    },
                },
            )
        if request.url.path == "/gmail/v1/users/me/messages/bg-2":
            return httpx.Response(
                200,
                json={
                    "id": "bg-2",
                    "threadId": "t-2",
                    "historyId": "701",
                    "snippet": "Your electricity bill is ready for payment.",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "BESCOM <billing@bescom.example>"},
                            {"name": "Subject", "value": "Your electricity bill is ready for payment"},
                            {"name": "Date", "value": "Thu, 26 Nov 2026 12:05:00 +0000"},
                        ],
                        "internalDate": "1795694700000",
                    },
                },
            )
        return httpx.Response(404)

    scheduler = BackgroundSyncScheduler(
        db,
        cfg,
        oauth_client=GoogleOAuthClient(cfg),
        gmail_client=GmailClient(
            transport=httpx.MockTransport(gmail_handler),
            sleep_fn=_noop_sleep,
        ),
    )

    summary = await scheduler.run_once()
    assert summary["users_processed"] == 1
    assert summary["synced_accounts"] == 1
    assert summary["new_messages"] == 2

    # Dashboard differentiates total_processed_emails (2) from total_job_emails (1)
    stats_resp = await ac.get(
        "/dashboard/statistics",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_processed_emails"] == 2
    assert stats["total_job_emails"] == 1
    assert stats["interview_invitations"] == 1

    # Notification was created ONLY for the interview email, NOT for electricity bill
    notifs_resp = await ac.get(
        "/notifications",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert notifs_resp.status_code == 200
    notifs = notifs_resp.json()["items"]
    assert len(notifs) == 1
    assert notifs[0]["title"] == "New Interview Invitation!"
    assert "Infosys" in notifs[0]["message"]
    assert notifs[0]["category"] == EmailCategory.INTERVIEW.value

    # Sync history recorded cleanly and accessible via /emails/sync-history
    hist_resp = await ac.get(
        "/emails/sync-history",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert hist_resp.status_code == 200
    hist_items = hist_resp.json()["items"]
    assert len(hist_items) == 1
    assert hist_items[0]["status"] == "SYNCED"
    assert hist_items[0]["new_messages"] == 2

    # Second run skips duplicates and creates zero duplicate notifications
    summary2 = await scheduler.run_once()
    assert summary2["new_messages"] == 0
    assert await db.notifications.count_documents({"user_id": user_id}) == 1
