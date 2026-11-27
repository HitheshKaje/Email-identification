"""Centralized environment-based application settings with production safety validation."""

from functools import lru_cache
import logging
import secrets
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("jobmail.config")

_PLACEHOLDER_SECRETS = {
    "",
    "replace-with-strong-random-secret",
    "replace-with-fernet-base64-key",
    "your_jwt_secret",
    "your_google_client_id",
    "your_google_client_secret",
}

_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


def _parse_key_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _validate_fernet_key(key: str) -> None:
    Fernet(key.encode("ascii"))


def _has_localhost(url_or_origin: str) -> bool:
    parsed = urlparse(url_or_origin.strip())
    host = (parsed.hostname or "").lower()
    return host in _LOCALHOST_HOSTS


class Settings(BaseSettings):
    """Application settings loaded from environment variables and optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "JobMail API"
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "jobmail"
    mongodb_tls_ca_file: str = ""
    mongodb_max_pool_size: int = Field(default=50, ge=5, le=500)
    mongodb_min_pool_size: int = Field(default=2, ge=0, le=50)

    # Security, Hashing, Sessions & MultiFernet Encryption
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=15, ge=5, le=43200)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    token_encryption_key: str = ""
    token_encryption_keys: str = ""
    mfa_issuer: str = "JobMail"
    max_failed_login_attempts: int = Field(default=5, ge=3, le=20)
    account_lockout_minutes: int = Field(default=15, ge=1, le=120)
    require_email_verification: bool | None = None

    # Cookies, Frontend URL & CORS
    frontend_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"
    trusted_hosts: str = ""
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cookie_domain: str = ""
    enable_api_docs: bool | None = None

    # API Hardening & Rate Limiting
    rate_limit_enabled: bool = True
    redis_url: str = ""
    max_request_body_bytes: int = Field(default=1_048_576, ge=16384, le=10_485_760)
    sync_cooldown_seconds: int = Field(default=30, ge=0, le=3600)
    enforce_sync_cooldown_in_test: bool = False
    default_data_retention_days: int = Field(default=180, ge=7, le=3650)

    # Google OAuth 2.0 (Phase 3)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    google_oauth_scopes: str = "https://www.googleapis.com/auth/gmail.readonly"
    oauth_state_expire_minutes: int = Field(default=10, ge=1, le=60)
    gmail_sync_max_messages: int = Field(default=100, ge=1, le=500)
    gmail_sync_page_size: int = Field(default=25, ge=1, le=100)
    auto_sync_enabled: bool = True
    auto_sync_interval_seconds: int = Field(default=900, ge=60, le=86400)

    # Outbound Email (SMTP for verification / password reset in production)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    # Firebase Cloud Messaging (Phase 6)
    firebase_credentials_path: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def google_oauth_client_configured(self) -> bool:
        cid = self.google_client_id.strip()
        csec = self.google_client_secret.strip()
        return bool(
            cid
            and csec
            and cid not in _PLACEHOLDER_SECRETS
            and csec not in _PLACEHOLDER_SECRETS
        )

    @property
    def encryption_key_list(self) -> list[str]:
        keys = _parse_key_list(self.token_encryption_keys)
        single = self.token_encryption_key.strip()
        if single and single not in _PLACEHOLDER_SECRETS and single not in keys:
            keys.append(single)
        return keys

    @property
    def effective_cookie_secure(self) -> bool:
        return self.is_production or self.cookie_secure

    @property
    def enforce_email_verification(self) -> bool:
        if self.require_email_verification is not None:
            return self.require_email_verification
        return self.is_production

    @property
    def effective_sync_cooldown_seconds(self) -> int:
        if self.environment == "test" and not self.enforce_sync_cooldown_in_test:
            return 0
        return self.sync_cooldown_seconds

    @property
    def docs_enabled(self) -> bool:
        if self.enable_api_docs is not None:
            return self.enable_api_docs
        return not self.is_production

    @field_validator("environment")
    @classmethod
    def _normalize_environment(cls, value: str) -> str:
        normalized = value.strip().lower() or "development"
        if normalized not in {"development", "test", "staging", "production"}:
            return normalized
        return normalized

    @field_validator("cookie_samesite")
    @classmethod
    def _normalize_samesite(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            return "lax"
        return normalized

    def model_post_init(self, __context: object) -> None:
        is_prod = self.is_production

        if self.jwt_secret_key.strip() in _PLACEHOLDER_SECRETS or (
            is_prod and len(self.jwt_secret_key.strip()) < 32
        ):
            if is_prod:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a strong >=32-char secret in production."
                )
            self.jwt_secret_key = secrets.token_urlsafe(48)
            logger.warning(
                "Using ephemeral development JWT_SECRET_KEY; set JWT_SECRET_KEY in .env for persistent tokens."
            )

        keys = self.encryption_key_list
        if not keys:
            if is_prod:
                raise ValueError(
                    "TOKEN_ENCRYPTION_KEY or TOKEN_ENCRYPTION_KEYS must be set to valid Fernet key(s) in production."
                )
            generated = Fernet.generate_key().decode("ascii")
            self.token_encryption_key = generated
            self.token_encryption_keys = generated
            logger.warning(
                "Using ephemeral development TOKEN_ENCRYPTION_KEY; set TOKEN_ENCRYPTION_KEY in .env for persistence."
            )
        else:
            for key in keys:
                _validate_fernet_key(key)
            if not self.token_encryption_key.strip():
                self.token_encryption_key = keys[0]

        if is_prod:
            if self.debug:
                raise ValueError("DEBUG must be false in production.")
            if _has_localhost(self.google_redirect_uri):
                raise ValueError(
                    "GOOGLE_REDIRECT_URI must use your public HTTPS domain in production (no localhost)."
                )
            if _has_localhost(self.frontend_url):
                raise ValueError(
                    "FRONTEND_URL must not use localhost in production."
                )
            if any(_has_localhost(origin) for origin in self.cors_origin_list):
                raise ValueError(
                    "CORS_ORIGINS must not allow localhost origins in production."
                )
            if "*" in self.cors_origin_list:
                raise ValueError(
                    "CORS_ORIGINS cannot use wildcard '*' in production."
                )
            if not self.google_redirect_uri.startswith("https://"):
                raise ValueError(
                    "GOOGLE_REDIRECT_URI must use HTTPS in production."
                )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def trusted_host_list(self) -> list[str]:
        return [
            host.strip()
            for host in self.trusted_hosts.split(",")
            if host.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
