"""End-to-end API, authentication, authorization, and MongoDB tests for Phase 2."""

from datetime import datetime, timezone
from cryptography.fernet import Fernet
import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError
from app.authentication.encryption import TokenEncryptor
from app.core.config import Settings
from app.database.mongodb import MongoDatabaseManager, db_manager
from app.main import create_app
from app.models.enums import AccountSyncStatus, EmailCategory


@pytest.mark.asyncio
async def test_health_check(client):
    ac, _ = client
    resp = await ac.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


@pytest.mark.asyncio
async def test_auth_register_login_and_profile(client):
    ac, _ = client

    reg = await ac.post(
        "/auth/register",
        json={
            "name": "Hithesh",
            "email": "hithesh@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert reg.status_code == 201
    token_data = reg.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["email"] == "hithesh@example.com"
    token = token_data["access_token"]

    # Duplicate registration should conflict cleanly
    dup = await ac.post(
        "/auth/register",
        json={
            "name": "Hithesh",
            "email": "hithesh@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert dup.status_code == 409

    # Wrong password returns 401
    bad_login = await ac.post(
        "/auth/login",
        json={"email": "hithesh@example.com", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    # Valid login succeeds
    login = await ac.post(
        "/auth/login",
        json={"email": "hithesh@example.com", "password": "StrongPassword123!"},
    )
    assert login.status_code == 200

    # Protected profile requires JWT or session cookie (clear client cookie jar first)
    ac.cookies.clear()
    unauth = await ac.get("/auth/me")
    assert unauth.status_code == 401

    me = await ac.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Hithesh"

    updated = await ac.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Hithesh K"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Hithesh K"


@pytest.mark.asyncio
async def test_dashboard_emails_search_feedback_and_isolation(client):
    ac, db = client

    # Register two separate users to test ownership isolation
    r1 = await ac.post(
        "/auth/register",
        json={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "Password123!",
        },
    )
    r2 = await ac.post(
        "/auth/register",
        json={
            "name": "Bob",
            "email": "bob@example.com",
            "password": "Password123!",
        },
    )
    alice_token = r1.json()["access_token"]
    alice_id = r1.json()["user"]["id"]
    bob_token = r2.json()["access_token"]

    now = datetime.now(timezone.utc)
    inserted = await db.emails.insert_many(
        [
            {
                "user_id": alice_id,
                "account_id": "acc-1",
                "gmail_message_id": "msg-1",
                "sender": "Infosys Careers <careers@infosys.com>",
                "subject": "Software Developer Interview Invitation",
                "body_preview": "You are shortlisted for Software Developer interview at Infosys.",
                "received_at": now,
                "category": EmailCategory.INTERVIEW.value,
                "confidence": 0.95,
                "company_name": "Infosys",
                "job_role": "Software Developer",
                "is_read": False,
            },
            {
                "user_id": alice_id,
                "account_id": "acc-1",
                "gmail_message_id": "msg-2",
                "sender": "Power Utility <billing@power.example>",
                "subject": "Electricity bill ready",
                "body_preview": "Your electricity bill is ready for payment.",
                "received_at": now,
                "category": EmailCategory.OTHER.value,
                "confidence": 0.99,
                "company_name": None,
                "job_role": None,
                "is_read": True,
            },
        ]
    )
    interview_id = str(inserted.inserted_ids[0])

    # Dashboard excludes OTHER emails
    stats_resp = await ac.get(
        "/dashboard/statistics",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_job_emails"] == 1
    assert stats["interview_invitations"] == 1
    assert stats["unread_count"] == 1

    # Search finds Infosys interview
    search_resp = await ac.get(
        "/emails/search",
        params={"q": "Infosys"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert search_resp.status_code == 200
    assert search_resp.json()["total"] == 1

    # Cross-user access is denied (404)
    bob_resp = await ac.get(
        f"/emails/{interview_id}",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_resp.status_code == 404

    # Mark email read and submit classification feedback
    patch_resp = await ac.patch(
        f"/emails/{interview_id}",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={"is_read": True},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_read"] is True

    fb_resp = await ac.post(
        "/classification/feedback",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={
            "email_id": interview_id,
            "corrected_category": EmailCategory.OFFER_LETTER.value,
        },
    )
    assert fb_resp.status_code == 200
    assert fb_resp.json()["corrected_category"] == "OFFER_LETTER"
    assert await db.classification_feedback.count_documents({"email_id": interview_id}) == 1


@pytest.mark.asyncio
async def test_connected_accounts_and_unique_indexes(client):
    ac, db = client
    reg = await ac.post(
        "/auth/register",
        json={
            "name": "User",
            "email": "user@example.com",
            "password": "Password123!",
        },
    )
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    acc_res = await db.connected_accounts.insert_one(
        {
            "user_id": user_id,
            "email_address": "user.jobs@gmail.com",
            "provider": "google",
            "encrypted_refresh_token": "encrypted-secret-value",
            "connected_at": datetime.now(timezone.utc),
            "last_synced_at": None,
            "sync_status": AccountSyncStatus.SYNCED.value,
        }
    )
    acc_id = str(acc_res.inserted_id)

    listed = await ac.get(
        "/auth/accounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert "encrypted_refresh_token" not in items[0]

    # Unique index prevents duplicate email message per account
    now = datetime.now(timezone.utc)
    await db.emails.insert_one(
        {
            "user_id": user_id,
            "account_id": acc_id,
            "gmail_message_id": "unique-msg-1",
            "sender": "hr@example.com",
            "subject": "Opening",
            "body_preview": "Role open",
            "received_at": now,
            "category": EmailCategory.JOB.value,
            "confidence": 0.9,
            "is_read": False,
        }
    )
    with pytest.raises(DuplicateKeyError):
        await db.emails.insert_one(
            {
                "user_id": user_id,
                "account_id": acc_id,
                "gmail_message_id": "unique-msg-1",
                "sender": "hr@example.com",
                "subject": "Opening",
                "body_preview": "Role open",
                "received_at": now,
                "category": EmailCategory.JOB.value,
                "confidence": 0.9,
                "is_read": False,
            }
        )

    # Disconnecting removes the account credentials cleanly
    del_resp = await ac.delete(
        f"/auth/accounts/{acc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204
    assert await db.connected_accounts.count_documents({"_id": acc_res.inserted_id}) == 0


@pytest.mark.asyncio
async def test_notifications_and_preferences(client):
    ac, db = client
    reg = await ac.post(
        "/auth/register",
        json={
            "name": "NotifUser",
            "email": "notif@example.com",
            "password": "Password123!",
        },
    )
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    # Register device token
    dev = await ac.post(
        "/notifications/register-device",
        headers={"Authorization": f"Bearer {token}"},
        json={"token": "sample-fcm-device-token-12345", "platform": "android"},
    )
    assert dev.status_code == 204

    # Update preferences
    pref_patch = await ac.patch(
        "/notifications/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "push_enabled": True,
            "job_opportunities": True,
            "internship_opportunities": False,
            "interview_invitations": True,
            "online_assessments": True,
            "recruitment_drives": False,
            "offer_letters": True,
            "application_updates": True,
        },
    )
    assert pref_patch.status_code == 200
    assert pref_patch.json()["application_updates"] is True

    # Insert notification & mark as read
    ins = await db.notifications.insert_one(
        {
            "user_id": user_id,
            "email_id": "email-123",
            "title": "New Interview Invitation!",
            "message": "You have received an interview invitation from Infosys.",
            "category": EmailCategory.INTERVIEW.value,
            "created_at": datetime.now(timezone.utc),
            "is_read": False,
        }
    )
    notif_id = str(ins.inserted_id)

    feed = await ac.get(
        "/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert feed.status_code == 200
    assert len(feed.json()["items"]) == 1

    mark = await ac.patch(
        f"/notifications/{notif_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_read": True},
    )
    assert mark.status_code == 200
    assert mark.json()["is_read"] is True


def test_token_encryptor_roundtrip():
    key = Fernet.generate_key().decode("ascii")
    encryptor = TokenEncryptor(key)
    ciphertext = encryptor.encrypt("refresh-token-xyz")
    assert ciphertext != "refresh-token-xyz"
    assert encryptor.decrypt(ciphertext) == "refresh-token-xyz"


@pytest.mark.asyncio
async def test_mongodb_connect_requires_explicit_uri_and_health_degrades_safely(monkeypatch):
    manager = MongoDatabaseManager()
    empty_settings = Settings(_env_file=None, environment="development", mongodb_uri="")
    with pytest.raises(ValueError, match="MONGODB_URI"):
        await manager.connect(empty_settings)

    # Reads MONGODB_URI and MONGODB_DB_NAME cleanly from OS environment variables
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGODB_DB_NAME", "jobmail_env_check")
    env_settings = Settings(_env_file=None, environment="development")
    assert env_settings.mongodb_uri == "mongodb://localhost:27017"
    assert env_settings.mongodb_db_name == "jobmail_env_check"

    # Verify FastAPI lifespan initializes pool + selected DB name and closes cleanly
    lifespan_settings = Settings(
        _env_file=None,
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="jobmail_test",
        jwt_secret_key="l" * 40,
        token_encryption_key=Fernet.generate_key().decode("ascii"),
    )
    test_app = create_app(lifespan_settings)
    async with test_app.router.lifespan_context(test_app):
        assert db_manager.db is not None
        assert db_manager.db.name == "jobmail_test"
        assert await db_manager.ping() is True
    assert db_manager.db is None
    assert db_manager.client is None


@pytest.mark.asyncio
async def test_health_returns_503_safely_when_ping_fails(client, monkeypatch):
    ac, _ = client

    async def broken_ping() -> bool:
        return False

    monkeypatch.setattr(db_manager, "ping", broken_ping)
    degraded = await ac.get("/health")
    assert degraded.status_code == 503
    assert degraded.json()["status"] == "degraded"
    assert degraded.json()["database"] == "disconnected"

    # Also verify MongoDatabaseManager.ping() catches PyMongoError safely
    class _BrokenDb:
        async def command(self, _cmd: str):
            raise PyMongoError("network down")

    failing_manager = MongoDatabaseManager()
    failing_manager.client = object()  # type: ignore[assignment]
    failing_manager.db = _BrokenDb()  # type: ignore[assignment]
    assert await failing_manager.ping() is False
