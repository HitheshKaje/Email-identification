"""Phase 3 tests for Google OAuth 2.0 flow, token encryption, refresh, revocation, and multi-account support."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from app.api.deps import get_google_oauth_client
from app.authentication.encryption import TokenEncryptor
from app.authentication.google_oauth import GoogleOAuthClient, REQUIRED_GMAIL_SCOPE
from app.core.config import Settings, get_settings
from app.core.exceptions import OAuthRevokedError
from app.models.enums import AccountSyncStatus
from app.services.google_oauth_service import GoogleOAuthService


def _oauth_settings() -> Settings:
    return Settings(
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="jobmail_test",
        jwt_secret_key="test-only-jwt-secret-key-at-least-32-bytes-long",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        google_client_id="test-google-client-id.apps.googleusercontent.com",
        google_client_secret="test-google-client-secret",
        google_redirect_uri="http://localhost:8000/auth/google/callback",
        google_oauth_scopes=REQUIRED_GMAIL_SCOPE,
    )


async def _register_user(ac, email: str = "oauthuser@example.com") -> tuple[str, str]:
    resp = await ac.post(
        "/auth/register",
        json={"name": "OAuth User", "email": email, "password": "StrongPassword123!"},
    )
    assert resp.status_code == 201
    data = resp.json()
    return data["access_token"], data["user"]["id"]


@pytest.mark.asyncio
async def test_connect_requires_google_credentials_when_unconfigured(client):
    ac, _ = client
    token, _ = await _register_user(ac)
    resp = await ac.post(
        "/auth/google/connect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 501
    assert "GOOGLE_CLIENT_ID" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_multi_account_oauth_connect_callback_encryption_and_disconnect(
    client, fastapi_app
):
    ac, db = client
    transport_app, _ = fastapi_app
    oauth_cfg = _oauth_settings()
    revoked_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://oauth2.googleapis.com/token":
            body = parse_qs(request.content.decode("utf-8"))
            code = body["code"][0]
            return httpx.Response(
                200,
                json={
                    "access_token": f"access-for-{code}",
                    "expires_in": 3600,
                    "refresh_token": f"refresh-for-{code}",
                    "scope": REQUIRED_GMAIL_SCOPE,
                    "token_type": "Bearer",
                },
            )
        if str(request.url) == "https://gmail.googleapis.com/gmail/v1/users/me/profile":
            auth_header = request.headers.get("authorization", "")
            if auth_header == "Bearer access-for-code-1":
                return httpx.Response(
                    200, json={"emailAddress": "first.jobs@gmail.com", "historyId": "101"}
                )
            return httpx.Response(
                200, json={"emailAddress": "second.jobs@gmail.com", "historyId": "202"}
            )
        if request.url.path == "/revoke":
            revoked_tokens.append(request.url.params.get("token", ""))
            return httpx.Response(200, json={})
        return httpx.Response(404)

    mock_client = GoogleOAuthClient(oauth_cfg, transport=httpx.MockTransport(handler))
    transport_app.dependency_overrides[get_settings] = lambda: oauth_cfg
    transport_app.dependency_overrides[get_google_oauth_client] = lambda: mock_client

    jwt_token, user_id = await _register_user(ac)

    # 1. Generate authorization URL for first account and verify read-only scope & state
    connect1 = await ac.post(
        "/auth/google/connect",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert connect1.status_code == 200
    auth_url = connect1.json()["authorization_url"]
    state1 = connect1.json()["state"]
    parsed_qs = parse_qs(urlparse(auth_url).query)
    assert parsed_qs["scope"] == [REQUIRED_GMAIL_SCOPE]
    assert parsed_qs["access_type"] == ["offline"]
    assert parsed_qs["prompt"] == ["consent"]
    assert parsed_qs["state"] == [state1]

    # 2. Callback connects first Gmail account
    cb1 = await ac.get(
        "/auth/google/callback",
        params={"code": "code-1", "state": state1, "format": "json"},
    )
    assert cb1.status_code == 200
    assert cb1.json()["email_address"] == "first.jobs@gmail.com"

    # Replaying the same state must fail
    replay = await ac.get(
        "/auth/google/callback",
        params={"code": "code-1", "state": state1, "format": "json"},
    )
    assert replay.status_code == 400

    # 3. Connect second Gmail account for the same user
    connect2 = await ac.post(
        "/auth/google/connect",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    state2 = connect2.json()["state"]
    cb2 = await ac.get(
        "/auth/google/callback",
        params={"code": "code-2", "state": state2},
    )
    assert cb2.status_code == 200
    assert "second.jobs@gmail.com" in cb2.text

    # 4. Verify tokens are encrypted in MongoDB and NEVER returned in /auth/accounts
    raw_accounts = await db.connected_accounts.find({"user_id": user_id}).to_list(10)
    assert len(raw_accounts) == 2
    encryptor = TokenEncryptor(oauth_cfg.token_encryption_key)
    for doc in raw_accounts:
        assert doc["encrypted_refresh_token"] != "refresh-for-code-1"
        assert doc["encrypted_access_token"] != "access-for-code-1"
        assert encryptor.decrypt(doc["encrypted_refresh_token"]).startswith("refresh-for-")

    listed = await ac.get(
        "/auth/accounts",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 2
    for item in items:
        assert "encrypted_refresh_token" not in item
        assert "encrypted_access_token" not in item

    # 5. Disconnect first account revokes token and removes DB document
    first_id = cb1.json()["id"]
    del_resp = await ac.delete(
        f"/auth/accounts/{first_id}",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert del_resp.status_code == 204
    assert "refresh-for-code-1" in revoked_tokens
    assert await db.connected_accounts.count_documents({"user_id": user_id}) == 1


@pytest.mark.asyncio
async def test_access_token_auto_refresh_and_revoked_handling(client, fastapi_app):
    ac, db = client
    transport_app, _ = fastapi_app
    oauth_cfg = _oauth_settings()
    refresh_calls = 0
    revoke_mode = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_calls
        if str(request.url) == "https://oauth2.googleapis.com/token":
            refresh_calls += 1
            if revoke_mode:
                return httpx.Response(
                    400,
                    json={"error": "invalid_grant", "error_description": "Token has been expired or revoked."},
                )
            return httpx.Response(
                200,
                json={
                    "access_token": "fresh-access-token",
                    "expires_in": 3600,
                    "scope": REQUIRED_GMAIL_SCOPE,
                    "token_type": "Bearer",
                },
            )
        if str(request.url) == "https://gmail.googleapis.com/gmail/v1/users/me/profile":
            return httpx.Response(
                200, json={"emailAddress": "refresh.test@gmail.com", "historyId": "333"}
            )
        return httpx.Response(404)

    mock_client = GoogleOAuthClient(oauth_cfg, transport=httpx.MockTransport(handler))
    transport_app.dependency_overrides[get_settings] = lambda: oauth_cfg
    transport_app.dependency_overrides[get_google_oauth_client] = lambda: mock_client

    jwt_token, user_id = await _register_user(ac, email="refreshuser@example.com")
    encryptor = TokenEncryptor(oauth_cfg.token_encryption_key)
    now = datetime.now(timezone.utc)
    acc_res = await db.connected_accounts.insert_one(
        {
            "user_id": user_id,
            "email_address": "refresh.test@gmail.com",
            "provider": "google",
            "encrypted_access_token": encryptor.encrypt("expired-access-token"),
            "access_token_expires_at": now - timedelta(minutes=5),
            "encrypted_refresh_token": encryptor.encrypt("valid-refresh-token"),
            "connected_at": now,
            "last_synced_at": None,
            "sync_status": AccountSyncStatus.PENDING.value,
        }
    )
    acc_id = str(acc_res.inserted_id)

    # 1. Expired access token triggers automatic refresh via verify endpoint
    verify_resp = await ac.post(
        f"/auth/accounts/{acc_id}/verify",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert verify_resp.status_code == 200
    assert refresh_calls == 1
    updated_doc = await db.connected_accounts.find_one({"_id": acc_res.inserted_id})
    assert encryptor.decrypt(updated_doc["encrypted_access_token"]) == "fresh-access-token"

    # 2. Simulate revoked refresh token (`invalid_grant`)
    revoke_mode = True
    service = GoogleOAuthService(db, oauth_cfg, mock_client)
    with pytest.raises(OAuthRevokedError):
        await service.get_valid_access_token(user_id, acc_id, force_refresh=True)

    revoked_doc = await db.connected_accounts.find_one({"_id": acc_res.inserted_id})
    assert revoked_doc["sync_status"] == AccountSyncStatus.REVOKED.value
    assert revoked_doc["encrypted_refresh_token"] == ""


@pytest.mark.asyncio
async def test_oauth_callback_handles_access_denied_and_expired_state(
    client, fastapi_app
):
    ac, db = client
    transport_app, _ = fastapi_app
    oauth_cfg = _oauth_settings()
    mock_client = GoogleOAuthClient(oauth_cfg)
    transport_app.dependency_overrides[get_settings] = lambda: oauth_cfg
    transport_app.dependency_overrides[get_google_oauth_client] = lambda: mock_client

    jwt_token, user_id = await _register_user(ac, email="deny@example.com")
    connect = await ac.post(
        "/auth/google/connect",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    state = connect.json()["state"]

    denied = await ac.get(
        "/auth/google/callback",
        params={"error": "access_denied", "state": state, "format": "json"},
    )
    assert denied.status_code == 400
    assert "access_denied" in denied.json()["detail"]

    # Expired state is rejected
    await db.oauth_states.insert_one(
        {
            "state": "expired-state-token",
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc) - timedelta(minutes=20),
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=10),
        }
    )
    expired = await ac.get(
        "/auth/google/callback",
        params={"code": "some-code", "state": "expired-state-token", "format": "json"},
    )
    assert expired.status_code == 400
    assert "expired" in expired.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_callback_preserves_state_on_probe_coalesces_duplicates_and_logs_safely(
    client, fastapi_app, caplog
):
    ac, db = client
    transport_app, _ = fastapi_app
    oauth_cfg = Settings(
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="jobmail_test",
        jwt_secret_key="test-only-jwt-secret-key-at-least-32-bytes-long",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        google_client_id="252912608567-test.apps.googleusercontent.com",
        google_client_secret="GOCSPX-SecretValueNeverLog12345",
        google_redirect_uri="https://jobmail-backend-tzwt.onrender.com/auth/google/callback",
        frontend_url="https://email-identification-frontend.vercel.app",
        google_oauth_scopes=REQUIRED_GMAIL_SCOPE,
    )
    token_exchange_calls = 0
    transient_fail_once = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_exchange_calls, transient_fail_once
        if str(request.url) == "https://oauth2.googleapis.com/token":
            if transient_fail_once:
                transient_fail_once = False
                raise httpx.ConnectError("simulated upstream blip")
            token_exchange_calls += 1
            await asyncio.sleep(0.25)
            body = parse_qs(request.content.decode("utf-8"))
            code = body["code"][0]
            return httpx.Response(
                200,
                json={
                    "access_token": f"ya29.access-secret-{code}",
                    "expires_in": 3600,
                    "refresh_token": f"1//refresh-secret-{code}",
                    "scope": REQUIRED_GMAIL_SCOPE,
                    "token_type": "Bearer",
                },
            )
        if str(request.url) == "https://gmail.googleapis.com/gmail/v1/users/me/profile":
            auth_header = request.headers.get("authorization", "")
            email_addr = (
                "first.concurrent@gmail.com"
                if "code-conc-1" in auth_header
                else "second.outoforder@gmail.com"
            )
            return httpx.Response(200, json={"emailAddress": email_addr, "historyId": "404"})
        return httpx.Response(404)

    mock_client = GoogleOAuthClient(oauth_cfg, transport=httpx.MockTransport(handler))
    transport_app.dependency_overrides[get_settings] = lambda: oauth_cfg
    transport_app.dependency_overrides[get_google_oauth_client] = lambda: mock_client

    jwt_token, _ = await _register_user(ac, email="resilient.oauth@example.com")

    with caplog.at_level(logging.INFO, logger="jobmail"):
        # Start two concurrent OAuth flows; neither overwrites the other
        c1 = await ac.post("/auth/google/connect", headers={"Authorization": f"Bearer {jwt_token}"})
        c2 = await ac.post("/auth/google/connect", headers={"Authorization": f"Bearer {jwt_token}"})
        assert c1.status_code == 200 and c2.status_code == 200
        state1 = c1.json()["state"]
        state2 = c2.json()["state"]
        assert state1 != state2
        assert await db.oauth_states.count_documents({"state": {"$in": [state1, state2]}}) == 2

        # 1. Incomplete probe lacking code preserves pending state1
        probe = await ac.get("/auth/google/callback", params={"state": state1, "format": "json"})
        assert probe.status_code == 400
        assert "authorization code" in probe.json()["detail"].lower()
        doc1_after_probe = await db.oauth_states.find_one({"state": state1})
        assert doc1_after_probe is not None and doc1_after_probe["status"] == "pending"

        # 2. Transient upstream network error rolls state1 back to pending for retry
        transient_fail_once = True
        transient = await ac.get(
            "/auth/google/callback",
            params={"code": "code-conc-1", "state": state1, "format": "json"},
        )
        assert transient.status_code == 502
        doc1_after_transient = await db.oauth_states.find_one({"state": state1})
        assert doc1_after_transient is not None and doc1_after_transient["status"] == "pending"

        # 3. Concurrent duplicate callback requests with same (state1, code) coalesce to single exchange,
        #    while a concurrent injected mismatched code is strictly rejected (400)
        task_r1 = asyncio.create_task(
            ac.get("/auth/google/callback", params={"code": "code-conc-1", "state": state1})
        )
        await asyncio.sleep(0.05)
        r2, mismatch = await asyncio.gather(
            ac.get("/auth/google/callback", params={"code": "code-conc-1", "state": state1}),
            ac.get("/auth/google/callback", params={"code": "attacker-code", "state": state1, "format": "json"}),
        )
        r1 = await task_r1
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert mismatch.status_code == 400
        assert token_exchange_calls == 1
        assert "first.concurrent@gmail.com" in r1.text
        assert "first.concurrent@gmail.com" in r2.text
        assert "Return to JobMail Web" in r1.text
        assert "https://email-identification-frontend.vercel.app/" in r1.text

        # PKCE verifier is scrubbed upon completion while consumed metadata remains until TTL
        completed_doc1 = await db.oauth_states.find_one({"state": state1})
        assert completed_doc1 is not None
        assert completed_doc1["status"] == "completed"
        assert "encrypted_code_verifier" not in completed_doc1

        # 4. Sequential post-completion replay is strictly rejected (400 CSRF/replay defense)
        post_replay = await ac.get(
            "/auth/google/callback",
            params={"code": "code-conc-1", "state": state1, "format": "json"},
        )
        assert post_replay.status_code == 400
        assert "already-used" in post_replay.json()["detail"].lower()

        # 5. Second independent attempt state2 remains valid and completes cleanly
        cb2 = await ac.get(
            "/auth/google/callback",
            params={"code": "code-conc-2", "state": state2, "format": "json"},
        )
        assert cb2.status_code == 200
        assert cb2.json()["email_address"] == "second.outoforder@gmail.com"

        # 6. Application logs never expose raw state, code, tokens, or client secret
        rendered_logs = "\n".join(
            r.getMessage() for r in caplog.records if r.name.startswith("jobmail")
        )
        assert state1 not in rendered_logs
        assert state2 not in rendered_logs
        assert "code-conc-1" not in rendered_logs
        assert "code-conc-2" not in rendered_logs
        assert "attacker-code" not in rendered_logs
        assert "ya29.access-secret" not in rendered_logs
        assert "1//refresh-secret" not in rendered_logs
        assert "GOCSPX-SecretValueNeverLog12345" not in rendered_logs
        assert "state_fp=" in rendered_logs

        # 7. SensitiveDataFilter scrubs query-string code/state parameters defensively
        from app.core.logging import redact_sensitive_text

        scrubbed = redact_sensitive_text(
            "GET /auth/google/callback?code=secretcode123&state=secretstate456"
        )
        assert "secretcode123" not in scrubbed
        assert "secretstate456" not in scrubbed
        assert "code=[REDACTED]" in scrubbed
        assert "state=[REDACTED]" in scrubbed
