"""Authentication lifecycle, MFA, rotating sessions, cookies, security events, and Google OAuth routes."""

import html
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.api.deps import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    get_current_user,
    get_db,
    get_email_delivery_service,
    get_google_oauth_client,
    require_verified_user,
)
from app.authentication.google_oauth import GoogleOAuthClient
from app.authentication.security import generate_opaque_token
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, AuthenticationError
from app.models.schemas import (
    ChangePasswordRequest,
    ConnectedAccountListResponse,
    ConnectedAccountResponse,
    EmailVerificationConfirmRequest,
    ForgotPasswordRequest,
    GoogleConnectResponse,
    LoginRequest,
    MfaConfirmRequest,
    MfaDisableRequest,
    MfaSetupResponse,
    MfaVerifyLoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SecurityEventListResponse,
    SessionListResponse,
    StatusMessageResponse,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.auth_service import AuthService
from app.services.email_delivery_service import EmailDeliveryService
from app.services.google_oauth_service import GoogleOAuthService
from app.services.rate_limiter import (
    SharedRateLimiter,
    extract_client_ip,
    extract_device_info,
)
from app.services.security_audit_service import SecurityAuditService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_auth_cookies(response: Response, token_res: TokenResponse, settings: Settings) -> None:
    if not token_res.access_token:
        return
    secure = settings.effective_cookie_secure
    samesite = settings.cookie_samesite
    domain = settings.cookie_domain.strip() or None

    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token_res.access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=secure,
        samesite=samesite,
        domain=domain,
        path="/",
    )
    if token_res.refresh_token:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=token_res.refresh_token,
            max_age=settings.refresh_token_expire_days * 86400,
            httponly=True,
            secure=secure,
            samesite=samesite,
            domain=domain,
            path="/auth",
        )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=generate_opaque_token(24),
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=False,
        secure=secure,
        samesite=samesite,
        domain=domain,
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    domain = settings.cookie_domain.strip() or None
    response.delete_cookie(key=ACCESS_COOKIE_NAME, domain=domain, path="/")
    response.delete_cookie(key=REFRESH_COOKIE_NAME, domain=domain, path="/auth")
    response.delete_cookie(key=CSRF_COOKIE_NAME, domain=domain, path="/")


def _render_oauth_html(
    *, title: str, heading: str, message: str, success: bool
) -> str:
    accent = "#059669" if success else "#DC2626"
    badge = "Connected" if success else "Connection Failed"
    status_param = "success" if success else "error"
    safe_title = html.escape(title)
    safe_heading = html.escape(heading)
    safe_message = html.escape(message)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{
      margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f6f8fc; color: #0f172a; display: flex; align-items: center;
      justify-content: center; min-height: 100vh; padding: 20px;
    }}
    .card {{
      max-width: 440px; width: 100%; background: #ffffff; border: 1px solid #e2e8f0;
      border-radius: 18px; padding: 28px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
      text-align: center;
    }}
    .pill {{
      display: inline-block; padding: 5px 12px; border-radius: 999px;
      font-size: 12px; font-weight: 700; color: {accent};
      background: rgba(29, 78, 216, 0.08); margin-bottom: 14px;
    }}
    h1 {{ font-size: 22px; margin: 0 0 10px; }}
    p {{ color: #475569; line-height: 1.5; margin: 0 0 18px; }}
    .btn {{
      display: inline-block; background: #1d4ed8; color: #ffffff;
      text-decoration: none; font-weight: 600; font-size: 14px;
      padding: 11px 20px; border-radius: 12px; margin-bottom: 14px;
    }}
    .hint {{ font-size: 13px; color: #64748b; margin-bottom: 0; }}
  </style>
</head>
<body>
  <main class="card">
    <span class="pill">{badge}</span>
    <h1>{safe_heading}</h1>
    <p>{safe_message}</p>
    <a class="btn" href="jobmail://oauth-callback?status={status_param}">Return to JobMail App</a>
    <p class="hint">On desktop, you may close this tab and return to JobMail.</p>
  </main>
</body>
</html>"""


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new JobMail user account using Argon2id and issue rotating session tokens",
)
async def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    mailer: Annotated[EmailDeliveryService, Depends(get_email_delivery_service)],
) -> TokenResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="register_ip", identifier=ip, limit=10, window_seconds=60, ip_address=ip
    )
    token_res = await AuthService(db, settings, mailer=mailer).register_user(
        payload,
        ip_address=ip,
        device_info=extract_device_info(request),
    )
    _set_auth_cookies(response, token_res, settings)
    return token_res


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in with email and password (supports MFA challenge, lockout, and cookie/JWT sessions)",
)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    ip = extract_client_ip(request)
    limiter = SharedRateLimiter(db, settings)
    await limiter.enforce(
        bucket="login_ip", identifier=ip, limit=15, window_seconds=60, ip_address=ip
    )
    await limiter.enforce(
        bucket="login_email",
        identifier=payload.email.strip().lower(),
        limit=12,
        window_seconds=60,
        ip_address=ip,
    )
    token_res = await AuthService(db, settings).authenticate_user(
        payload,
        ip_address=ip,
        device_info=extract_device_info(request),
    )
    if not token_res.mfa_required:
        _set_auth_cookies(response, token_res, settings)
    return token_res


@router.post(
    "/mfa/verify-login",
    response_model=TokenResponse,
    summary="Complete MFA login using authenticator TOTP or backup recovery code",
)
async def verify_mfa_login(
    request: Request,
    response: Response,
    payload: MfaVerifyLoginRequest,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="mfa_verify", identifier=ip, limit=10, window_seconds=60, ip_address=ip
    )
    token_res = await AuthService(db, settings).verify_mfa_login(
        challenge_token=payload.challenge_token,
        code=payload.code,
        ip_address=ip,
        device_info=extract_device_info(request),
    )
    _set_auth_cookies(response, token_res, settings)
    return token_res


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue a fresh short-lived access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: RefreshTokenRequest | None = None,
) -> TokenResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="refresh_ip", identifier=ip, limit=30, window_seconds=60, ip_address=ip
    )
    raw_refresh = (payload.refresh_token if payload and payload.refresh_token else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise AuthenticationError("Refresh token required.")
    token_res = await AuthService(db, settings).refresh_session(
        raw_refresh, ip_address=ip
    )
    _set_auth_cookies(response, token_res, settings)
    return token_res


@router.post(
    "/logout",
    response_model=StatusMessageResponse,
    summary="Revoke the current session and clear auth cookies",
)
async def logout(
    request: Request,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatusMessageResponse:
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        await AuthService(db, settings).revoke_session(
            current_user.id,
            str(session_id),
            ip_address=extract_client_ip(request),
        )
    clear_auth_cookies(response, settings)
    return StatusMessageResponse(status="ok", message="Signed out cleanly.")


@router.post(
    "/logout-all",
    response_model=StatusMessageResponse,
    summary="Revoke all active sessions across all devices",
)
async def logout_all(
    request: Request,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatusMessageResponse:
    revoked_count = await AuthService(db, settings).logout_all_sessions(
        current_user.id,
        ip_address=extract_client_ip(request),
    )
    clear_auth_cookies(response, settings)
    return StatusMessageResponse(
        status="ok",
        message=f"Signed out from {revoked_count} active session(s).",
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List active authenticated sessions for the current user",
)
async def list_sessions(
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionListResponse:
    sid = getattr(request.state, "session_id", None)
    items = await AuthService(db, settings).list_sessions(
        current_user.id,
        current_session_id=str(sid) if sid else None,
    )
    return SessionListResponse(items=items)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an individual session by ID",
)
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    await AuthService(db, settings).revoke_session(
        current_user.id,
        session_id,
        ip_address=extract_client_ip(request),
    )


@router.post(
    "/verify-email/request",
    response_model=StatusMessageResponse,
    summary="Request an email verification message",
)
async def request_email_verification(
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    mailer: Annotated[EmailDeliveryService, Depends(get_email_delivery_service)],
) -> StatusMessageResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="verify_email_req",
        identifier=current_user.id,
        limit=5,
        window_seconds=300,
        user_id=current_user.id,
        ip_address=ip,
    )
    await AuthService(db, settings, mailer=mailer).request_email_verification(
        current_user.id, ip_address=ip
    )
    return StatusMessageResponse(
        status="ok",
        message="Verification email dispatched if your address is not already verified.",
    )


@router.post(
    "/verify-email/confirm",
    response_model=UserResponse,
    summary="Confirm email ownership with a verification token",
)
async def confirm_email_verification(
    request: Request,
    payload: EmailVerificationConfirmRequest,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="verify_email_confirm", identifier=ip, limit=10, window_seconds=60, ip_address=ip
    )
    return await AuthService(db, settings).confirm_email_verification(
        payload.token, ip_address=ip
    )


@router.post(
    "/password/forgot",
    response_model=StatusMessageResponse,
    summary="Request a secure password reset token (privacy-preserving response)",
)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    mailer: Annotated[EmailDeliveryService, Depends(get_email_delivery_service)],
) -> StatusMessageResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="forgot_password_ip", identifier=ip, limit=6, window_seconds=300, ip_address=ip
    )
    await AuthService(db, settings, mailer=mailer).request_password_reset(
        payload.email, ip_address=ip
    )
    return StatusMessageResponse(
        status="ok",
        message="If an account with that email exists, password reset instructions have been dispatched.",
    )


@router.post(
    "/password/reset",
    response_model=StatusMessageResponse,
    summary="Reset password with a single-use token and revoke active sessions",
)
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatusMessageResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="reset_password_ip", identifier=ip, limit=10, window_seconds=300, ip_address=ip
    )
    await AuthService(db, settings).confirm_password_reset(
        token=payload.token, new_password=payload.new_password, ip_address=ip
    )
    return StatusMessageResponse(
        status="ok",
        message="Password reset completed. Please sign in with your new password.",
    )


@router.post(
    "/password/change",
    response_model=StatusMessageResponse,
    summary="Change current password and invalidate other device sessions",
)
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatusMessageResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="change_password",
        identifier=current_user.id,
        limit=6,
        window_seconds=300,
        user_id=current_user.id,
        ip_address=ip,
    )
    sid = getattr(request.state, "session_id", None)
    await AuthService(db, settings).change_password(
        user_id=current_user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        current_session_id=str(sid) if sid else None,
        ip_address=ip,
    )
    return StatusMessageResponse(
        status="ok",
        message="Password updated and other active sessions signed out.",
    )


@router.post(
    "/mfa/setup",
    response_model=MfaSetupResponse,
    summary="Generate TOTP authenticator secret and recovery codes for MFA enrollment",
)
async def setup_mfa(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MfaSetupResponse:
    return await AuthService(db, settings).setup_mfa(current_user.id)


@router.post(
    "/mfa/enable",
    response_model=UserResponse,
    summary="Verify initial TOTP code and enable MFA",
)
async def enable_mfa(
    request: Request,
    payload: MfaConfirmRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    return await AuthService(db, settings).enable_mfa(
        current_user.id, payload.code, ip_address=extract_client_ip(request)
    )


@router.post(
    "/mfa/disable",
    response_model=UserResponse,
    summary="Verify password + MFA code and disable MFA",
)
async def disable_mfa(
    request: Request,
    payload: MfaDisableRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    return await AuthService(db, settings).disable_mfa(
        user_id=current_user.id,
        password=payload.password,
        code=payload.code,
        ip_address=extract_client_ip(request),
    )


@router.get(
    "/security-events",
    response_model=SecurityEventListResponse,
    summary="List recent security activity events for the authenticated user",
)
async def list_security_events(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    limit: int = Query(default=25, ge=1, le=100),
) -> SecurityEventListResponse:
    items = await SecurityAuditService(db).list_user_events(
        current_user.id, limit=limit
    )
    return SecurityEventListResponse(items=items)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated user's profile and security flags",
)
async def get_me(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> UserResponse:
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update the authenticated user's display name",
)
async def update_me(
    payload: UserUpdateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    return await AuthService(db, settings).update_user_name(
        current_user.id, payload.name
    )


@router.post(
    "/google/connect",
    response_model=GoogleConnectResponse,
    summary="Generate Google OAuth 2.0 read-only Gmail PKCE authorization URL",
)
async def connect_google(
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_verified_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
) -> GoogleConnectResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="oauth_connect",
        identifier=current_user.id,
        limit=20,
        window_seconds=60,
        user_id=current_user.id,
        ip_address=ip,
    )
    return await GoogleOAuthService(db, settings, oauth_client).create_connect_url(
        current_user.id, ip_address=ip
    )


@router.get(
    "/google/authorize",
    summary="Redirect authenticated user directly to Google OAuth 2.0 consent",
)
async def authorize_google_redirect(
    request: Request,
    current_user: Annotated[UserResponse, Depends(require_verified_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
) -> RedirectResponse:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="oauth_connect",
        identifier=current_user.id,
        limit=20,
        window_seconds=60,
        user_id=current_user.id,
        ip_address=ip,
    )
    connect_res = await GoogleOAuthService(
        db, settings, oauth_client
    ).create_connect_url(current_user.id, ip_address=ip)
    return RedirectResponse(
        url=connect_res.authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@router.get(
    "/google/callback",
    summary="Handle Google OAuth 2.0 PKCE callback, validate state, exchange tokens, and save encrypted credentials",
)
async def google_callback(
    request: Request,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    response_format: str | None = Query(default=None, alias="format"),
):
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="oauth_callback_ip", identifier=ip, limit=30, window_seconds=60, ip_address=ip
    )
    wants_json = (
        response_format == "json"
        or "application/json" in request.headers.get("accept", "").lower()
    )
    service = GoogleOAuthService(db, settings, oauth_client)
    try:
        account = await service.handle_callback(
            code=code,
            state=state,
            error=error,
            error_description=error_description,
            ip_address=ip,
        )
    except AppError as exc:
        if wants_json:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        return HTMLResponse(
            status_code=exc.status_code,
            content=_render_oauth_html(
                title="JobMail – Gmail Connection Failed",
                heading="Could not connect Gmail",
                message=exc.detail,
                success=False,
            ),
        )

    if wants_json:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=account.model_dump(mode="json"),
        )
    return HTMLResponse(
        status_code=status.HTTP_200_OK,
        content=_render_oauth_html(
            title="JobMail – Gmail Connected",
            heading="Gmail account connected",
            message=(
                f"{account.email_address} is now linked with read-only Gmail access. "
                "Return to JobMail and refresh your Connected Accounts list."
            ),
            success=True,
        ),
    )


@router.get(
    "/accounts",
    response_model=ConnectedAccountListResponse,
    summary="List Gmail accounts linked to the authenticated user",
)
async def list_accounts(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConnectedAccountListResponse:
    accounts = await AuthService(db, settings).list_connected_accounts(
        current_user.id
    )
    return ConnectedAccountListResponse(items=accounts)


@router.post(
    "/accounts/{account_id}/verify",
    response_model=ConnectedAccountResponse,
    summary="Verify connected Gmail OAuth status and refresh expired access tokens if needed",
)
async def verify_account(
    account_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
) -> ConnectedAccountResponse:
    return await GoogleOAuthService(
        db, settings, oauth_client
    ).verify_account_connection(current_user.id, account_id)


@router.delete(
    "/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke OAuth tokens, remove stored credentials, and purge synced Gmail data for an account",
)
async def disconnect_account(
    account_id: str,
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
    purge_emails: bool = Query(default=True),
) -> None:
    await GoogleOAuthService(db, settings, oauth_client).disconnect_account(
        current_user.id,
        account_id,
        purge_emails=purge_emails,
        ip_address=extract_client_ip(request),
    )
