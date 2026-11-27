"""FastAPI dependency providers for DB, settings, dual Bearer/Cookie auth, CSRF checks, and RBAC."""

import hmac
from typing import Annotated
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.authentication.google_oauth import GoogleOAuthClient
from app.authentication.security import decode_access_token
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.database.mongodb import db_manager
from app.models.enums import UserRole
from app.models.schemas import UserResponse
from app.services.auth_service import AuthService
from app.services.email_delivery_service import EmailDeliveryService
from app.services.gmail_client import GmailClient

bearer_scheme = HTTPBearer(auto_error=False)

ACCESS_COOKIE_NAME = "jobmail_access_token"
REFRESH_COOKIE_NAME = "jobmail_refresh_token"
CSRF_COOKIE_NAME = "jobmail_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"


def get_db() -> AsyncIOMotorDatabase:
    if db_manager.db is None:
        raise RuntimeError("Database connection has not been initialized.")
    return db_manager.db


def get_google_oauth_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GoogleOAuthClient:
    return GoogleOAuthClient(settings)


def get_gmail_client() -> GmailClient:
    return GmailClient()


def get_email_delivery_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailDeliveryService:
    return EmailDeliveryService(settings)


def _verify_cookie_csrf(request: Request, settings: Settings) -> None:
    """Enforce CSRF double-submit token or same-origin header when using cookie auth."""
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    csrf_header = request.headers.get(CSRF_HEADER_NAME, "")
    if csrf_cookie and csrf_header and hmac.compare_digest(csrf_cookie, csrf_header):
        return

    origin = request.headers.get("origin", "").strip().rstrip("/")
    allowed = {o.rstrip("/") for o in settings.cors_origin_list}
    allowed.add(settings.frontend_url.rstrip("/"))
    if origin and origin in allowed and csrf_header == "1":
        return

    raise AuthorizationError("CSRF validation failed for cookie-authenticated request.")


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    raw_token: str | None = None
    via_cookie = False

    if credentials is not None:
        if credentials.scheme.lower() != "bearer":
            raise AuthenticationError("Authentication required.")
        raw_token = credentials.credentials
    else:
        cookie_tok = request.cookies.get(ACCESS_COOKIE_NAME)
        if cookie_tok:
            _verify_cookie_csrf(request, settings)
            raw_token = cookie_tok
            via_cookie = True

    if not raw_token:
        raise AuthenticationError("Authentication required.")

    payload = decode_access_token(raw_token, settings, expected_type="access")
    user_id = str(payload["sub"])
    session_id = payload.get("sid")
    auth_service = AuthService(db, settings)
    await auth_service.validate_active_session(user_id, str(session_id) if session_id else None)
    user = await auth_service.get_user_by_id(user_id)

    request.state.session_id = session_id
    request.state.via_cookie = via_cookie
    return user


async def require_verified_user(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    if settings.enforce_email_verification and not current_user.email_verified:
        raise AuthorizationError(
            "Please verify your email address before connecting or syncing Gmail accounts."
        )
    return current_user


async def require_admin_user(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> UserResponse:
    if current_user.role != UserRole.ADMIN.value:
        raise AuthorizationError("Administrator privileges required.")
    return current_user
