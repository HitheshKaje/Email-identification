"""Phase 4 tests for Gmail API message retrieval, pagination, deduplication, rate limits, and multi-account sync."""

import base64
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from app.api.deps import get_gmail_client, get_google_oauth_client
from app.authentication.encryption import TokenEncryptor
from app.authentication.google_oauth import GoogleOAuthClient, REQUIRED_GMAIL_SCOPE
from app.core.config import Settings, get_settings
from app.models.enums import AccountSyncStatus, EmailCategory
from app.services.gmail_client import GmailClient


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _test_oauth_settings() -> Settings:
    return Settings(
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="jobmail_test",
        jwt_secret_key="test-only-jwt-secret-key-at-least-32-bytes-long",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        google_oauth_scopes=REQUIRED_GMAIL_SCOPE,
        gmail_sync_page_size=2,
        gmail_sync_max_messages=20,
    )


async def _register(ac, email: str = "sync@example.com") -> tuple[str, str]:
    resp = await ac.post(
        "/auth/register",
        json={"name": "Sync User", "email": email, "password": "StrongPassword123!"},
    )
    assert resp.status_code == 201
    data = resp.json()
    return data["access_token"], data["user"]["id"]


async def _noop_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_gmail_pagination_deduplication_and_rate_limit_retry(
    client, fastapi_app
):
    ac, db = client
    app, _ = fastapi_app
    cfg = _test_oauth_settings()
    encryptor = TokenEncryptor(cfg.token_encryption_key)
    fetched_detail_ids: list[str] = []
    rate_limit_triggered = False

    def gmail_handler(request: httpx.Request) -> httpx.Response:
        nonlocal rate_limit_triggered
        path = request.url.path

        if path == "/gmail/v1/users/me/messages":
            page_token = request.url.params.get("pageToken")
            if not page_token:
                return httpx.Response(
                    200,
                    json={
                        "messages": [{"id": "g-1"}, {"id": "g-2"}],
                        "nextPageToken": "page-2",
                    },
                )
            return httpx.Response(
                200,
                json={"messages": [{"id": "g-3"}]},
            )

        if path == "/gmail/v1/users/me/messages/g-1":
            if not rate_limit_triggered:
                rate_limit_triggered = True
                return httpx.Response(429, headers={"Retry-After": "0.1"})
            fetched_detail_ids.append("g-1")
            return httpx.Response(
                200,
                json={
                    "id": "g-1",
                    "threadId": "t-1",
                    "historyId": "500",
                    "snippet": "Interview invite snippet",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Infosys HR <careers@infosys.com>"},
                            {"name": "Subject", "value": "Software Developer Interview"},
                            {"name": "Date", "value": "Thu, 26 Nov 2026 10:00:00 +0000"},
                        ],
                        "mimeType": "text/plain",
                        "body": {
                            "data": _b64(
                                "Congratulations! You are shortlisted for Software Developer at Infosys."
                            )
                        },
                    },
                },
            )

        if path == "/gmail/v1/users/me/messages/g-2":
            fetched_detail_ids.append("g-2")
            return httpx.Response(
                200,
                json={
                    "id": "g-2",
                    "threadId": "t-2",
                    "historyId": "501",
                    "snippet": "HTML body snippet",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "TechCorp <jobs@techcorp.io>"},
                            {"name": "Subject", "value": "Backend Engineer Opening"},
                        ],
                        "internalDate": "1795680000000",
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {
                                "mimeType": "text/html",
                                "body": {
                                    "data": _b64(
                                        "<html><body><p>Apply for <b>Backend Engineer</b> role.</p></body></html>"
                                    )
                                },
                            }
                        ],
                    },
                },
            )

        if path == "/gmail/v1/users/me/messages/g-3":
            fetched_detail_ids.append("g-3")
            return httpx.Response(
                200,
                json={
                    "id": "g-3",
                    "threadId": "t-3",
                    "historyId": "502",
                    "snippet": "Duplicate check message",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Recruiter <hr@acme.io>"},
                            {"name": "Subject", "value": "Assessment Link"},
                        ],
                        "internalDate": "1795683600000",
                    },
                },
            )

        if path == "/gmail/v1/users/me/history":
            return httpx.Response(
                200,
                json={
                    "historyId": "510",
                    "history": [
                        {
                            "messagesAdded": [
                                {"message": {"id": "g-3"}},
                                {"message": {"id": "g-4"}},
                            ]
                        }
                    ],
                },
            )

        if path == "/gmail/v1/users/me/messages/g-4":
            fetched_detail_ids.append("g-4")
            return httpx.Response(
                200,
                json={
                    "id": "g-4",
                    "threadId": "t-4",
                    "historyId": "510",
                    "snippet": "New history message",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Startup <talent@startup.dev>"},
                            {"name": "Subject", "value": "Offer Letter"},
                        ],
                        "internalDate": "1795687200000",
                    },
                },
            )

        return httpx.Response(404)

    oauth_client = GoogleOAuthClient(cfg)
    gmail_client = GmailClient(
        transport=httpx.MockTransport(gmail_handler),
        sleep_fn=_noop_sleep,
    )
    app.dependency_overrides[get_settings] = lambda: cfg
    app.dependency_overrides[get_google_oauth_client] = lambda: oauth_client
    app.dependency_overrides[get_gmail_client] = lambda: gmail_client

    jwt_token, user_id = await _register(ac)
    now = datetime.now(timezone.utc)
    acc_res = await db.connected_accounts.insert_one(
        {
            "user_id": user_id,
            "email_address": "sync.user@gmail.com",
            "provider": "google",
            "encrypted_access_token": encryptor.encrypt("valid-token"),
            "access_token_expires_at": now + timedelta(minutes=30),
            "encrypted_refresh_token": encryptor.encrypt("refresh-token"),
            "connected_at": now,
            "last_synced_at": None,
            "sync_status": AccountSyncStatus.PENDING.value,
        }
    )
    acc_id = str(acc_res.inserted_id)

    # First sync: paginates across 2 pages, retries 429 on g-1, stores 3 messages
    sync1 = await ac.post(
        "/emails/sync",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"account_id": acc_id},
    )
    assert sync1.status_code == 200
    body1 = sync1.json()
    assert body1["synced_accounts"] == 1
    assert body1["new_messages"] == 3
    assert body1["skipped_duplicates"] == 0
    assert rate_limit_triggered is True
    assert fetched_detail_ids == ["g-1", "g-2", "g-3"]

    g2_doc = await db.emails.find_one({"account_id": acc_id, "gmail_message_id": "g-2"})
    assert "body_preview" not in g2_doc
    assert "Apply for Backend Engineer role." in encryptor.decrypt(
        g2_doc["encrypted_body_preview"]
    )

    # Second sync uses historyId; g-3 is skipped WITHOUT re-downloading, only g-4 fetched!
    fetched_detail_ids.clear()
    sync2 = await ac.post(
        "/emails/sync",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={},
    )
    assert sync2.status_code == 200
    body2 = sync2.json()
    assert body2["new_messages"] == 1
    assert body2["skipped_duplicates"] == 1
    assert fetched_detail_ids == ["g-4"]

    # Verify account_id filtering returns all 4 classified recruitment emails
    filtered = await ac.get(
        "/emails",
        params={"account_id": acc_id},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 4
    assert await db.emails.count_documents({"account_id": acc_id}) == 4

    by_cat = await ac.get(
        "/emails",
        params={"account_id": acc_id, "category": EmailCategory.INTERVIEW.value},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert by_cat.status_code == 200
    assert by_cat.json()["total"] == 1
    assert by_cat.json()["items"][0]["company_name"] == "Infosys"


@pytest.mark.asyncio
async def test_multi_account_sync_history_fallback_and_revoked_isolation(
    client, fastapi_app
):
    ac, db = client
    app, _ = fastapi_app
    cfg = _test_oauth_settings()
    encryptor = TokenEncryptor(cfg.token_encryption_key)
    saw_after_query = False

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://oauth2.googleapis.com/token":
            return httpx.Response(
                400,
                json={"error": "invalid_grant", "error_description": "Revoked"},
            )
        return httpx.Response(404)

    def gmail_handler(request: httpx.Request) -> httpx.Response:
        nonlocal saw_after_query
        if request.url.path == "/gmail/v1/users/me/history":
            return httpx.Response(404, json={"error": {"message": "History expired"}})
        if request.url.path == "/gmail/v1/users/me/messages":
            q = request.url.params.get("q", "")
            if q.startswith("after:"):
                saw_after_query = True
            return httpx.Response(200, json={"messages": [{"id": "acc1-msg-1"}]})
        if request.url.path == "/gmail/v1/users/me/messages/acc1-msg-1":
            return httpx.Response(
                200,
                json={
                    "id": "acc1-msg-1",
                    "threadId": "t-9",
                    "historyId": "900",
                    "snippet": "Placement drive",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Placement Cell <placement@uni.edu>"},
                            {"name": "Subject", "value": "Campus Drive"},
                        ],
                        "internalDate": "1795690000000",
                    },
                },
            )
        return httpx.Response(404)

    oauth_client = GoogleOAuthClient(cfg, transport=httpx.MockTransport(oauth_handler))
    gmail_client = GmailClient(
        transport=httpx.MockTransport(gmail_handler),
        sleep_fn=_noop_sleep,
    )
    app.dependency_overrides[get_settings] = lambda: cfg
    app.dependency_overrides[get_google_oauth_client] = lambda: oauth_client
    app.dependency_overrides[get_gmail_client] = lambda: gmail_client

    jwt_token, user_id = await _register(ac, email="multi@example.com")
    now = datetime.now(timezone.utc)

    acc1 = await db.connected_accounts.insert_one(
        {
            "user_id": user_id,
            "email_address": "healthy@gmail.com",
            "provider": "google",
            "encrypted_access_token": encryptor.encrypt("healthy-access"),
            "access_token_expires_at": now + timedelta(minutes=30),
            "encrypted_refresh_token": encryptor.encrypt("healthy-refresh"),
            "history_id": "100",
            "connected_at": now - timedelta(days=1),
            "last_synced_at": now - timedelta(hours=2),
            "sync_status": AccountSyncStatus.SYNCED.value,
        }
    )
    acc2 = await db.connected_accounts.insert_one(
        {
            "user_id": user_id,
            "email_address": "revoked@gmail.com",
            "provider": "google",
            "encrypted_access_token": encryptor.encrypt("expired-access"),
            "access_token_expires_at": now - timedelta(minutes=10),
            "encrypted_refresh_token": encryptor.encrypt("revoked-refresh"),
            "connected_at": now - timedelta(days=1),
            "last_synced_at": now - timedelta(hours=2),
            "sync_status": AccountSyncStatus.SYNCED.value,
        }
    )

    resp = await ac.post(
        "/emails/sync",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "partial"
    assert body["synced_accounts"] == 1
    assert body["failed_accounts"] == 1
    assert body["new_messages"] == 1
    assert saw_after_query is True

    healthy_doc = await db.connected_accounts.find_one({"_id": acc1.inserted_id})
    revoked_doc = await db.connected_accounts.find_one({"_id": acc2.inserted_id})
    assert healthy_doc["sync_status"] == AccountSyncStatus.SYNCED.value
    assert healthy_doc["history_id"] == "900"
    assert revoked_doc["sync_status"] == AccountSyncStatus.REVOKED.value
