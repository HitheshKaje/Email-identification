"""Password hashing (Argon2id with bcrypt migration), strong JWTs, PKCE, TOTP MFA, and opaque tokens."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from typing import Any
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError
import bcrypt
import jwt
import pyotp
from app.core.config import Settings
from app.core.exceptions import AppError, AuthenticationError

_ARGON2_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

_COMMON_WEAK_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "admin123",
    "letmein123",
    "welcome123",
}


def hash_password(password: str) -> str:
    """Hash a user password using memory-hard Argon2id."""
    return _ARGON2_HASHER.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against Argon2id or legacy bcrypt hashes."""
    if not plain_password or not hashed_password:
        return False

    if hashed_password.startswith("$argon2"):
        try:
            return _ARGON2_HASHER.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except ValueError:
            return False

    return False


def needs_password_rehash(hashed_password: str) -> bool:
    """Return True if a stored hash uses legacy bcrypt or outdated Argon2 parameters."""
    if not hashed_password:
        return True
    if not hashed_password.startswith("$argon2id$"):
        return True
    try:
        return _ARGON2_HASHER.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return True


def validate_password_strength(password: str) -> None:
    """Enforce production password complexity guidelines (NIST / OWASP ASVS)."""
    if len(password) < 8 or len(password) > 128:
        raise AppError("Password must be between 8 and 128 characters.", status_code=422)
    if password.strip().lower() in _COMMON_WEAK_PASSWORDS:
        raise AppError("Choose a stronger, non-common password.", status_code=422)
    checks = (
        re.search(r"[a-z]", password),
        re.search(r"[A-Z]", password),
        re.search(r"\d", password),
        re.search(r"[^A-Za-z0-9]", password),
    )
    if not all(checks):
        raise AppError(
            "Password must include uppercase, lowercase, digit, and special character.",
            status_code=422,
        )


def generate_opaque_token(nbytes: int = 32) -> str:
    """Generate a high-entropy URL-safe random token."""
    return secrets.token_urlsafe(nbytes)


def hash_opaque_token(token: str) -> str:
    """Hash a single-use or refresh token using SHA-256 before persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_opaque_token_hash(token: str, expected_hash: str) -> bool:
    """Constant-time comparison of an opaque token's SHA-256 digest."""
    if not token or not expected_hash:
        return False
    return hmac.compare_digest(hash_opaque_token(token), expected_hash)


def generate_pkce_pair() -> tuple[str, str]:
    """Generate an RFC 7636 S256 (code_verifier, code_challenge) PKCE pair."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def create_access_token(
    subject: str,
    settings: Settings,
    *,
    session_id: str | None = None,
    role: str = "user",
    expires_delta: timedelta | None = None,
    token_type: str = "access",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a signed JWT access or challenge token with unique JTI and optional session binding."""
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = now + delta
    payload: dict[str, Any] = {
        "sub": subject,
        "jti": secrets.token_hex(16),
        "typ": token_type,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if session_id:
        payload["sid"] = session_id
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(
    token: str,
    settings: Settings,
    *,
    expected_type: str = "access",
) -> dict[str, Any]:
    """Decode and validate a JWT token's signature, expiry, subject, and type."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc

    if not payload.get("sub"):
        raise AuthenticationError("Token missing subject claim.")
    tok_type = payload.get("typ", "access")
    if tok_type != expected_type:
        raise AuthenticationError("Invalid token type.")
    return payload


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(secret: str, email: str, issuer: str = "JobMail") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    cleaned = re.sub(r"\s+", "", code or "")
    if not cleaned:
        return False
    return bool(pyotp.TOTP(secret).verify(cleaned, valid_window=1))


def generate_recovery_codes(count: int = 8) -> tuple[list[str], list[str]]:
    """Return (plaintext_codes, hashed_codes) for one-time MFA recovery backup codes."""
    plain: list[str] = []
    hashed: list[str] = []
    for _ in range(count):
        raw = f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        plain.append(raw)
        hashed.append(hash_opaque_token(raw))
    return plain, hashed
