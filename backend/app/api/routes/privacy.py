"""Privacy protection, GDPR export, retention policy, Gmail purge, and account deletion routes."""

from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.api.deps import get_current_user, get_db, get_google_oauth_client
from app.api.routes.auth import clear_auth_cookies
from app.authentication.google_oauth import GoogleOAuthClient
from app.core.config import Settings, get_settings
from app.models.schemas import (
    DataRetentionUpdateRequest,
    DeleteAccountRequest,
    PrivacyOverviewResponse,
    StatusMessageResponse,
    UserResponse,
)
from app.services.privacy_service import PrivacyService
from app.services.rate_limiter import SharedRateLimiter, extract_client_ip

router = APIRouter(prefix="/privacy", tags=["Privacy"])


@router.get(
    "/overview",
    response_model=PrivacyOverviewResponse,
    summary="Inspect user data retention policy, Gmail scope, and stored counts",
)
async def privacy_overview(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PrivacyOverviewResponse:
    return await PrivacyService(db, settings).get_overview(current_user.id)


@router.patch(
    "/retention",
    response_model=PrivacyOverviewResponse,
    summary="Configure personal email retention policy and purge expired records",
)
async def update_retention(
    payload: DataRetentionUpdateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PrivacyOverviewResponse:
    return await PrivacyService(db, settings).update_retention(
        current_user.id, payload.retention_days
    )


@router.get(
    "/export",
    summary="Download all personal JobMail profile, account, email, and notification data as JSON",
)
async def export_data(
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    ip = extract_client_ip(request)
    await SharedRateLimiter(db, settings).enforce(
        bucket="privacy_export",
        identifier=current_user.id,
        limit=10,
        window_seconds=300,
        user_id=current_user.id,
        ip_address=ip,
    )
    return await PrivacyService(db, settings).export_user_data(current_user.id)


@router.delete(
    "/gmail-data",
    response_model=StatusMessageResponse,
    summary="Delete all synced Gmail messages, notifications, and feedback (optionally disconnecting accounts)",
)
async def delete_gmail_data(
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
    disconnect_accounts: bool = Query(default=False),
) -> StatusMessageResponse:
    result = await PrivacyService(db, settings, oauth_client).delete_gmail_data(
        current_user.id,
        disconnect_accounts=disconnect_accounts,
        ip_address=extract_client_ip(request),
    )
    return StatusMessageResponse(
        status="ok",
        message=(
            f"Deleted {result['emails_deleted']} email(s) and {result['notifications_deleted']} notification(s)."
        ),
    )


@router.delete(
    "/account",
    response_model=StatusMessageResponse,
    summary="Permanently delete user account, revoke OAuth tokens, and erase all stored data",
)
async def delete_account(
    request: Request,
    response: Response,
    payload: DeleteAccountRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
) -> StatusMessageResponse:
    await PrivacyService(db, settings, oauth_client).delete_account(
        user_id=current_user.id,
        password=payload.password,
        confirm_text=payload.confirm_text,
        ip_address=extract_client_ip(request),
    )
    clear_auth_cookies(response, settings)
    return StatusMessageResponse(
        status="ok",
        message="Account and all associated Gmail data have been permanently deleted.",
    )
