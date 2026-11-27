"""Phase 14 OWASP ASVS / API Security Top 10 automated security test suite."""

import base64
from datetime import datetime, timedelta, timezone
import logging
from urllib.parse import parse_qs, urlparse
import bcrypt
from cryptography.fernet import Fernet
import httpx
import pyotp
import pytest
from app.api.deps import get_email_delivery_service, get_gmail_client, get_google_oauth_client
from app.authentication.encryption import TokenEncryptor, rotate_document_fields
from app.authentication.google_oauth import GoogleOAuthClient, REQUIRED_GMAIL_SCOPE
from app.authentication.security import verify_password
from app.core.config import Settings, get_settings
from app.core.logging import SensitiveDataFilter, mask_email
from app.main import create_app
from app.models.enums import AccountSyncStatus, EmailCategory
from app.services.classification_service import ClassificationService
from app.services.gmail_client import GmailClient, parse_gmail_message


class _CapturingMailer:
    """In-memory test double capturing verification/reset tokens without leaking via API."""

    def __init__(self) -> None:
        self.verification_tokens: list[tuple[str, str]] = []
        self.reset_tokens: list[tuple[str, str]] = []

    async def send_verification_email(self, *, recipient: str, token: str) -> bool:
        self.verification_tokens.append((recipient, token))
        return True

    async def send_password_reset_email(self, *, recipient: str, token: str) -> bool:
        self.reset_tokens.append((recipient, token))
        return True


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


async def _register(ac, email: str, password: str = "StrongPassword123!") -> dict:
    res = await ac.post(
        "/auth/register",
        json={"name": email.split("@")[0].title(), "email": email, "password": password},
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_argon2id_hashing_password_policy_and_bcrypt_migration(client):
    ac, db = client

    # Weak password rejected
    weak = await ac.post(
        "/auth/register",
        json={"name": "Weak", "email": "weak@example.com", "password": "password"},
    )
    assert weak.status_code == 422

    # Registered user uses Argon2id hash (never stored plaintext)
    reg = await _register(ac, "argon@example.com", "StrongPassword123!")
    user_doc = await db.users.find_one({"email": "argon@example.com"})
    assert user_doc["hashed_password"].startswith("$argon2id$")
    assert verify_password("StrongPassword123!", user_doc["hashed_password"])

    # Legacy bcrypt user transparently upgrades to Argon2id on login
    legacy_hash = bcrypt.hashpw(b"LegacyPass123!", bcrypt.gensalt()).decode("utf-8")
    await db.users.update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"hashed_password": legacy_hash, "password_algo": "bcrypt"}},
    )
    login = await ac.post(
        "/auth/login",
        json={"email": "argon@example.com", "password": "LegacyPass123!"},
    )
    assert login.status_code == 200
    upgraded = await db.users.find_one({"_id": user_doc["_id"]})
    assert upgraded["hashed_password"].startswith("$argon2id$")
    assert reg["access_token"] != login.json()["access_token"]


@pytest.mark.asyncio
async def test_email_verification_and_password_reset_lifecycle(client, fastapi_app):
    ac, db = client
    app, _ = fastapi_app
    mailer = _CapturingMailer()
    app.dependency_overrides[get_email_delivery_service] = lambda: mailer

    strict_cfg = Settings(
        _env_file=None,
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="jobmail_test",
        jwt_secret_key="test-only-jwt-secret-key-at-least-32-bytes-long",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        require_email_verification=True,
        google_client_id="cid",
        google_client_secret="csec",
    )
    app.dependency_overrides[get_settings] = lambda: strict_cfg

    reg = await _register(ac, "verifyme@example.com")
    token = reg["access_token"]
    assert reg["user"]["email_verified"] is False
    assert len(mailer.verification_tokens) == 1

    # Unverified user blocked from OAuth connect when enforcement is active
    blocked = await ac.post(
        "/auth/google/connect", headers={"Authorization": f"Bearer {token}"}
    )
    assert blocked.status_code == 403

    # Confirm email verification using single-use token
    _, verify_tok = mailer.verification_tokens[0]
    confirm = await ac.post("/auth/verify-email/confirm", json={"token": verify_tok})
    assert confirm.status_code == 200
    assert confirm.json()["email_verified"] is True

    # Replay verification token rejected
    replay_v = await ac.post("/auth/verify-email/confirm", json={"token": verify_tok})
    assert replay_v.status_code == 400

    # Connect now succeeds
    allowed = await ac.post(
        "/auth/google/connect", headers={"Authorization": f"Bearer {token}"}
    )
    assert allowed.status_code == 200

    # Forgot & reset password flow (unknown email returns identical 200 status)
    unk = await ac.post("/auth/password/forgot", json={"email": "nobody@example.com"})
    assert unk.status_code == 200
    forgot = await ac.post("/auth/password/forgot", json={"email": "verifyme@example.com"})
    assert forgot.status_code == 200
    assert len(mailer.reset_tokens) == 1
    _, reset_tok = mailer.reset_tokens[0]

    reset_res = await ac.post(
        "/auth/password/reset",
        json={"token": reset_tok, "new_password": "NewStrongPassword!99"},
    )
    assert reset_res.status_code == 200

    # Previous token & old sessions must now be revoked!
    ac.cookies.clear()
    old_session_check = await ac.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert old_session_check.status_code == 401

    # Login with new password works
    new_login = await ac.post(
        "/auth/login",
        json={"email": "verifyme@example.com", "password": "NewStrongPassword!99"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_mfa_totp_recovery_lockout_sessions_and_refresh_reuse(client):
    ac, db = client

    reg = await _register(ac, "mfa@example.com")
    tok1 = reg["access_token"]
    ref1 = reg["refresh_token"]

    # Setup & Enable MFA
    setup = await ac.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {tok1}"})
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    recovery_code = setup.json()["recovery_codes"][0]

    totp_now = pyotp.TOTP(secret).now()
    enabled = await ac.post(
        "/auth/mfa/enable",
        headers={"Authorization": f"Bearer {tok1}"},
        json={"code": totp_now},
    )
    assert enabled.status_code == 200
    assert enabled.json()["mfa_enabled"] is True

    # Refresh token rotation works and invalidates old refresh token
    rotated = await ac.post("/auth/refresh", json={"refresh_token": ref1})
    assert rotated.status_code == 200
    tok2 = rotated.json()["access_token"]
    ref2 = rotated.json()["refresh_token"]
    assert ref2 != ref1

    # Replaying old rotated refresh token triggers SUSPICIOUS_TOKEN_REUSE & revokes whole session!
    reused = await ac.post("/auth/refresh", json={"refresh_token": ref1})
    assert reused.status_code == 401
    after_reuse = await ac.get("/auth/me", headers={"Authorization": f"Bearer {tok2}"})
    assert after_reuse.status_code == 401
    assert (
        await db.security_events.count_documents(
            {"event_type": "SUSPICIOUS_TOKEN_REUSE", "alert": True}
        )
        >= 1
    )

    # MFA Login flow + backup recovery code
    login_mfa = await ac.post(
        "/auth/login",
        json={"email": "mfa@example.com", "password": "StrongPassword123!"},
    )
    assert login_mfa.status_code == 200
    assert login_mfa.json()["mfa_required"] is True
    challenge = login_mfa.json()["mfa_challenge_token"]

    mfa_done = await ac.post(
        "/auth/mfa/verify-login",
        json={"challenge_token": challenge, "code": recovery_code},
    )
    assert mfa_done.status_code == 200
    mfa_tok = mfa_done.json()["access_token"]

    # Sessions list & logout-all
    sessions = await ac.get("/auth/sessions", headers={"Authorization": f"Bearer {mfa_tok}"})
    assert sessions.status_code == 200
    assert len(sessions.json()["items"]) == 1

    logout_all = await ac.post("/auth/logout-all", headers={"Authorization": f"Bearer {mfa_tok}"})
    assert logout_all.status_code == 200
    ac.cookies.clear()
    assert (
        await ac.get("/auth/me", headers={"Authorization": f"Bearer {mfa_tok}"})
    ).status_code == 401

    # Account lockout after 5 repeated wrong passwords
    for _ in range(5):
        bad = await ac.post(
            "/auth/login",
            json={"email": "mfa@example.com", "password": "WrongPassword!1"},
        )
    assert bad.status_code == 423
    assert "Retry-After" in bad.headers


@pytest.mark.asyncio
async def test_cookie_csrf_protection_and_session_expiration(client):
    ac, db = client
    await _register(ac, "cookie@example.com")

    # Cookie jar holds HttpOnly jobmail_access_token & jobmail_csrf_token
    me_get = await ac.get("/auth/me")
    assert me_get.status_code == 200

    # Cookie-authenticated POST/PATCH without X-CSRF-Token is blocked (403)
    no_csrf = await ac.patch("/auth/me", json={"name": "Attacker"})
    assert no_csrf.status_code == 403

    csrf_val = ac.cookies.get("jobmail_csrf_token")
    with_csrf = await ac.patch(
        "/auth/me",
        json={"name": "Cookie Safe"},
        headers={"X-CSRF-Token": csrf_val},
    )
    assert with_csrf.status_code == 200
    assert with_csrf.json()["name"] == "Cookie Safe"

    # Expired session rejected cleanly
    await db.sessions.update_many(
        {}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}}
    )
    expired = await ac.get("/auth/me")
    assert expired.status_code == 401


@pytest.mark.asyncio
async def test_multi_user_isolation_idor_bola_and_feedback_isolation(client, fastapi_app):
    ac, db = client
    app, _ = fastapi_app
    alice = await _register(ac, "alice.iso@example.com")
    bob = await _register(ac, "bob.iso@example.com")
    alice_tok, alice_id = alice["access_token"], alice["user"]["id"]
    bob_tok, bob_id = bob["access_token"], bob["user"]["id"]

    cfg = Settings(
        _env_file=None,
        environment="test",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        google_client_id="cid",
        google_client_secret="csec",
    )
    encryptor = TokenEncryptor(cfg.token_encryption_key)
    now = datetime.now(timezone.utc)

    alice_acc = await db.connected_accounts.insert_one(
        {
            "user_id": alice_id,
            "email_address": "alice.jobs@gmail.com",
            "provider": "google",
            "encrypted_access_token": encryptor.encrypt("alice-access"),
            "encrypted_refresh_token": encryptor.encrypt("alice-refresh"),
            "connected_at": now,
            "sync_status": AccountSyncStatus.SYNCED.value,
        }
    )
    alice_acc_id = str(alice_acc.inserted_id)

    alice_email = await db.emails.insert_one(
        {
            "user_id": alice_id,
            "account_id": alice_acc_id,
            "gmail_message_id": "alice-msg-1",
            "encrypted_sender": encryptor.encrypt("HR <hr@corp.com>"),
            "encrypted_subject": encryptor.encrypt("Private Offer"),
            "encrypted_body_preview": encryptor.encrypt("Salary details for Alice only."),
            "received_at": now,
            "category": EmailCategory.OFFER_LETTER.value,
            "confidence": 0.99,
            "is_read": False,
        }
    )
    alice_email_id = str(alice_email.inserted_id)

    alice_notif = await db.notifications.insert_one(
        {
            "user_id": alice_id,
            "email_id": alice_email_id,
            "title": "New Offer Letter!",
            "message": "Private alert",
            "category": EmailCategory.OFFER_LETTER.value,
            "created_at": now,
            "is_read": False,
        }
    )
    alice_notif_id = str(alice_notif.inserted_id)
    alice_session_id = alice["session_id"]

    # Bob CANNOT read/modify/verify/sync/disconnect/revoke ANY of Alice's resources!
    assert (
        await ac.get(f"/emails/{alice_email_id}", headers={"Authorization": f"Bearer {bob_tok}"})
    ).status_code == 404
    assert (
        await ac.patch(
            f"/emails/{alice_email_id}",
            headers={"Authorization": f"Bearer {bob_tok}"},
            json={"is_read": True},
        )
    ).status_code == 404
    assert (
        await ac.get(
            "/emails",
            params={"account_id": alice_acc_id},
            headers={"Authorization": f"Bearer {bob_tok}"},
        )
    ).status_code == 403
    assert (
        await ac.post(
            "/emails/sync",
            headers={"Authorization": f"Bearer {bob_tok}"},
            json={"account_id": alice_acc_id},
        )
    ).status_code == 404
    assert (
        await ac.post(
            f"/auth/accounts/{alice_acc_id}/verify",
            headers={"Authorization": f"Bearer {bob_tok}"},
        )
    ).status_code == 404
    assert (
        await ac.delete(
            f"/auth/accounts/{alice_acc_id}",
            headers={"Authorization": f"Bearer {bob_tok}"},
        )
    ).status_code == 404
    assert (
        await ac.patch(
            f"/notifications/{alice_notif_id}",
            headers={"Authorization": f"Bearer {bob_tok}"},
            json={"is_read": True},
        )
    ).status_code == 404
    assert (
        await ac.post(
            "/classification/feedback",
            headers={"Authorization": f"Bearer {bob_tok}"},
            json={"email_id": alice_email_id, "corrected_category": "OTHER"},
        )
    ).status_code == 404
    assert (
        await ac.delete(
            f"/auth/sessions/{alice_session_id}",
            headers={"Authorization": f"Bearer {bob_tok}"},
        )
    ).status_code == 404

    # Cross-user feedback does not leak into another user's retrain_from_feedback
    await ac.post(
        "/classification/feedback",
        headers={"Authorization": f"Bearer {alice_tok}"},
        json={"email_id": alice_email_id, "corrected_category": "OFFER_LETTER"},
    )
    bob_samples_total = await ClassificationService(db, cfg).retrain_from_feedback(
        user_id=bob_id, save_to_disk=False
    )
    alice_samples_total = await ClassificationService(db, cfg).retrain_from_feedback(
        user_id=alice_id, save_to_disk=False
    )
    assert alice_samples_total == bob_samples_total + 1


@pytest.mark.asyncio
async def test_pkce_oauth_and_multifernet_rotation(client, fastapi_app):
    ac, db = client
    app, _ = fastapi_app
    old_key = Fernet.generate_key().decode("ascii")
    new_key = Fernet.generate_key().decode("ascii")

    # MultiFernet rotation test
    legacy_enc = TokenEncryptor(old_key)
    cipher_old = legacy_enc.encrypt("top-secret-refresh-token")
    multi_enc = TokenEncryptor(f"{new_key},{old_key}")
    assert multi_enc.decrypt(cipher_old) == "top-secret-refresh-token"
    rotated_cipher = multi_enc.rotate(cipher_old)
    assert TokenEncryptor(new_key).decrypt(rotated_cipher) == "top-secret-refresh-token"

    saw_verifier = None

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        nonlocal saw_verifier
        if str(request.url) == "https://oauth2.googleapis.com/token":
            body = parse_qs(request.content.decode("utf-8"))
            saw_verifier = body.get("code_verifier", [None])[0]
            return httpx.Response(
                200,
                json={
                    "access_token": "pkce-access",
                    "expires_in": 3600,
                    "refresh_token": "pkce-refresh",
                    "scope": REQUIRED_GMAIL_SCOPE,
                },
            )
        if str(request.url) == "https://gmail.googleapis.com/gmail/v1/users/me/profile":
            return httpx.Response(200, json={"emailAddress": "pkce@gmail.com", "historyId": "11"})
        return httpx.Response(404)

    cfg = Settings(
        _env_file=None,
        environment="test",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        google_client_id="cid",
        google_client_secret="csec",
    )
    app.dependency_overrides[get_settings] = lambda: cfg
    app.dependency_overrides[get_google_oauth_client] = lambda: GoogleOAuthClient(
        cfg, transport=httpx.MockTransport(oauth_handler)
    )

    reg = await _register(ac, "pkce.user@example.com")
    tok = reg["access_token"]
    conn = await ac.post("/auth/google/connect", headers={"Authorization": f"Bearer {tok}"})
    assert conn.status_code == 200
    assert conn.json()["pkce_enabled"] is True
    qs = parse_qs(urlparse(conn.json()["authorization_url"]).query)
    assert qs["code_challenge_method"] == ["S256"]
    assert "code_challenge" in qs

    cb = await ac.get(
        "/auth/google/callback",
        params={"code": "auth-code-1", "state": conn.json()["state"], "format": "json"},
    )
    assert cb.status_code == 200
    assert saw_verifier is not None and len(saw_verifier) >= 43


def test_gmail_html_xss_neutralization_and_attachment_safety():
    parsed = parse_gmail_message(
        {
            "id": "safe-1",
            "snippet": "Hello",
            "payload": {
                "headers": [
                    {"name": "From", "value": "HR <hr@acme.com>"},
                    {"name": "Subject", "value": "<script>alert(1)</script>Interview Update"},
                ],
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {
                            "data": _b64(
                                "<html><script>stealCookies()</script>"
                                "<svg onload='alert(2)'>bad</svg>"
                                "<p onclick='evil()'>Shortlisted for <b>DevOps</b> role.</p></html>"
                            )
                        },
                    },
                    {
                        "mimeType": "application/pdf",
                        "filename": "<script>x</script>offer.pdf",
                        "body": {"attachmentId": "att-1"},
                    },
                ],
            },
        }
    )
    assert "alert(" not in parsed.subject
    assert "<script" not in parsed.body_preview.lower()
    assert "stealCookies" not in parsed.body_preview
    assert "Shortlisted for DevOps role." in parsed.body_preview
    assert parsed.has_attachments is True
    assert parsed.attachment_names == ["offer.pdf"]


@pytest.mark.asyncio
async def test_rate_limiting_payload_size_limit_headers_and_log_redaction(client):
    ac, _ = client

    # Response security headers present
    health = await ac.get("/health")
    assert health.headers.get("x-content-type-options") == "nosniff"
    assert health.headers.get("x-frame-options") == "DENY"
    assert "default-src 'none'" in health.headers.get("content-security-policy", "")

    # Oversized payload rejected with 413
    oversized = "A" * 1_200_000
    too_big = await ac.post(
        "/auth/login",
        content=oversized,
        headers={"Content-Type": "application/json"},
    )
    assert too_big.status_code == 413

    # Shared rate limiting triggers 429 + Retry-After
    for _ in range(10):
        await ac.post("/auth/password/forgot", json={"email": "ratelimit@example.com"})
    limited = await ac.post("/auth/password/forgot", json={"email": "ratelimit@example.com"})
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers

    # Log filter redacts secrets cleanly and masks emails
    record = logging.LogRecord(
        "jobmail.test",
        logging.INFO,
        __file__,
        1,
        "Bearer eyJhbGciOiJIUzI1NiJ9.aaa.bbb secret GOCSPX-TestSecret123456 email %s",
        (mask_email("candidate@gmail.com"),),
        None,
    )
    SensitiveDataFilter().filter(record)
    assert "GOCSPX-" not in record.msg
    assert "eyJhbG" not in record.msg
    assert "c***@gmail.com" in record.msg


@pytest.mark.asyncio
async def test_privacy_export_retention_purge_disconnect_and_account_deletion(
    client, fastapi_app
):
    ac, db = client
    app, _ = fastapi_app
    revoked_tokens: list[str] = []

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/revoke":
            revoked_tokens.append(request.url.params.get("token", ""))
            return httpx.Response(200, json={})
        return httpx.Response(404)

    cfg = Settings(
        _env_file=None,
        environment="test",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        google_client_id="cid",
        google_client_secret="csec",
    )
    encryptor = TokenEncryptor(cfg.token_encryption_key)
    app.dependency_overrides[get_settings] = lambda: cfg
    app.dependency_overrides[get_google_oauth_client] = lambda: GoogleOAuthClient(
        cfg, transport=httpx.MockTransport(oauth_handler)
    )

    reg = await _register(ac, "privacy@example.com")
    tok, uid = reg["access_token"], reg["user"]["id"]
    now = datetime.now(timezone.utc)

    acc = await db.connected_accounts.insert_one(
        {
            "user_id": uid,
            "email_address": "priv.gmail@gmail.com",
            "provider": "google",
            "encrypted_access_token": encryptor.encrypt("acc-tok"),
            "encrypted_refresh_token": encryptor.encrypt("ref-tok-privacy"),
            "connected_at": now,
            "sync_status": AccountSyncStatus.SYNCED.value,
        }
    )
    acc_id = str(acc.inserted_id)

    # Insert 1 old email (40 days old) + 1 recent email
    await db.emails.insert_many(
        [
            {
                "user_id": uid,
                "account_id": acc_id,
                "gmail_message_id": "old-msg",
                "encrypted_sender": encryptor.encrypt("Old <old@corp.com>"),
                "encrypted_subject": encryptor.encrypt("Old Job"),
                "encrypted_body_preview": encryptor.encrypt("Old job text"),
                "received_at": now - timedelta(days=45),
                "category": EmailCategory.JOB.value,
                "confidence": 0.9,
                "is_read": True,
            },
            {
                "user_id": uid,
                "account_id": acc_id,
                "gmail_message_id": "new-msg",
                "encrypted_sender": encryptor.encrypt("New <new@corp.com>"),
                "encrypted_subject": encryptor.encrypt("Recent Interview"),
                "encrypted_body_preview": encryptor.encrypt("New invite text"),
                "received_at": now - timedelta(days=2),
                "category": EmailCategory.INTERVIEW.value,
                "confidence": 0.95,
                "is_read": False,
            },
        ]
    )

    # Retention update purges email older than 30 days
    ret = await ac.patch(
        "/privacy/retention",
        headers={"Authorization": f"Bearer {tok}"},
        json={"retention_days": 30},
    )
    assert ret.status_code == 200
    assert ret.json()["emails_stored"] == 1

    # Export returns decrypted data without secrets
    exp = await ac.get("/privacy/export", headers={"Authorization": f"Bearer {tok}"})
    assert exp.status_code == 200
    assert len(exp.json()["emails"]) == 1
    assert exp.json()["emails"][0]["subject"] == "Recent Interview"
    assert "encrypted_refresh_token" not in str(exp.json())

    # Full account deletion revokes Google token & purges user + sessions + emails
    del_acc = await ac.request(
        "DELETE",
        "/privacy/account",
        headers={"Authorization": f"Bearer {tok}"},
        json={"password": "StrongPassword123!", "confirm_text": "DELETE"},
    )
    assert del_acc.status_code == 200
    assert "ref-tok-privacy" in revoked_tokens
    assert await db.emails.count_documents({"user_id": uid}) == 0
    assert await db.connected_accounts.count_documents({"user_id": uid}) == 0
    assert await db.sessions.count_documents({"user_id": uid}) == 0


def test_production_config_rejects_localhost_cors_and_missing_secrets():
    with pytest.raises(ValueError, match="localhost"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="s" * 40,
            token_encryption_key=Fernet.generate_key().decode("ascii"),
            google_redirect_uri="http://localhost:8000/auth/google/callback",
            frontend_url="https://app.jobmail.example",
            cors_origins="https://app.jobmail.example",
        )

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="replace-with-strong-random-secret",
            token_encryption_key=Fernet.generate_key().decode("ascii"),
            google_redirect_uri="https://api.jobmail.example/auth/google/callback",
            frontend_url="https://app.jobmail.example",
            cors_origins="https://app.jobmail.example",
        )

    prod_app = create_app(
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="p" * 40,
            token_encryption_key=Fernet.generate_key().decode("ascii"),
            google_redirect_uri="https://api.jobmail.example/auth/google/callback",
            frontend_url="https://app.jobmail.example",
            cors_origins="https://app.jobmail.example",
        )
    )
    assert prod_app.docs_url is None
    assert prod_app.openapi_url is None
