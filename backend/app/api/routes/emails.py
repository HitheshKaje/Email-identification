"""Classified recruitment email routes with rate limiting, pagination caps, and user isolation."""

from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.api.deps import (
    get_current_user,
    get_db,
    get_gmail_client,
    get_google_oauth_client,
    require_verified_user,
)
from app.authentication.google_oauth import GoogleOAuthClient
from app.core.config import Settings, get_settings
from app.models.enums import EmailCategory
from app.models.schemas import (
    EmailListResponse,
    EmailResponse,
    EmailUpdateRequest,
    SyncHistoryListResponse,
    SyncRequest,
    SyncResponse,
    UserResponse,
)
from app.services.email_service import EmailService
from app.services.gmail_client import GmailClient
from app.services.gmail_sync_service import GmailSyncService
from app.services.rate_limiter import SharedRateLimiter, extract_client_ip

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.get(
    "",
    response_model=EmailListResponse,
    summary="List classified career emails with optional filters",
)
async def list_emails(
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    category: EmailCategory | None = None,
    account_id: str | None = None,
    company: str | None = None,
    is_read: bool | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    skip: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=50, ge=1, le=200),
) -> EmailListResponse:
    await SharedRateLimiter(db, settings).enforce(
        bucket="emails_list",
        identifier=current_user.id,
        limit=120,
        window_seconds=60,
        user_id=current_user.id,
        ip_address=extract_client_ip(request),
    )
    return await EmailService(db, settings).list_emails(
        current_user.id,
        category=category,
        account_id=account_id,
        company=company,
        is_read=is_read,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/search",
    response_model=EmailListResponse,
    summary="Search classified career emails by keyword, company, account, category, or date",
)
async def search_emails(
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    q: str = Query(default="", max_length=200),
    category: EmailCategory | None = None,
    account_id: str | None = None,
    company: str | None = None,
    is_read: bool | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    skip: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=50, ge=1, le=200),
) -> EmailListResponse:
    await SharedRateLimiter(db, settings).enforce(
        bucket="emails_search",
        identifier=current_user.id,
        limit=60,
        window_seconds=60,
        user_id=current_user.id,
        ip_address=extract_client_ip(request),
    )
    return await EmailService(db, settings).list_emails(
        current_user.id,
        query=q,
        category=category,
        account_id=account_id,
        company=company,
        is_read=is_read,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/category/{category}",
    response_model=EmailListResponse,
    summary="Get classified emails for a specific recruitment category",
)
async def list_emails_by_category(
    category: EmailCategory,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    skip: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=50, ge=1, le=200),
) -> EmailListResponse:
    return await EmailService(db, settings).list_emails(
        current_user.id,
        category=category,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/sync-history",
    response_model=SyncHistoryListResponse,
    summary="Retrieve synchronization history for the authenticated user's accounts",
)
async def get_sync_history(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
    gmail_client: Annotated[GmailClient, Depends(get_gmail_client)],
    limit: int = Query(default=25, ge=1, le=100),
) -> SyncHistoryListResponse:
    items = await GmailSyncService(
        db, settings, oauth_client, gmail_client
    ).get_sync_history(current_user.id, limit=limit)
    return SyncHistoryListResponse(items=items)


@router.get(
    "/{email_id}",
    response_model=EmailResponse,
    summary="Get details for a single classified email",
)
async def get_email_detail(
    email_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailResponse:
    return await EmailService(db, settings).get_email_by_id(current_user.id, email_id)


@router.patch(
    "/{email_id}",
    response_model=EmailResponse,
    summary="Update read/unread status for a classified email",
)
async def update_email_status(
    email_id: str,
    payload: EmailUpdateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailResponse:
    return await EmailService(db, settings).update_read_status(
        current_user.id, email_id, payload.is_read
    )


@router.post(
    "/sync",
    response_model=SyncResponse,
    summary="Synchronize Gmail messages across one or all connected Gmail accounts",
)
async def sync_emails(
    request: Request,
    payload: SyncRequest,
    current_user: Annotated[UserResponse, Depends(require_verified_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    oauth_client: Annotated[GoogleOAuthClient, Depends(get_google_oauth_client)],
    gmail_client: Annotated[GmailClient, Depends(get_gmail_client)],
) -> SyncResponse:
    await SharedRateLimiter(db, settings).enforce(
        bucket="emails_sync",
        identifier=current_user.id,
        limit=12,
        window_seconds=60,
        user_id=current_user.id,
        ip_address=extract_client_ip(request),
    )
    return await GmailSyncService(
        db, settings, oauth_client, gmail_client
    ).sync_user_accounts(current_user.id, account_id=payload.account_id)
