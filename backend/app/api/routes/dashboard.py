"""Dashboard statistics and decrypted recent recruitment email routes."""

from typing import Annotated
from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.api.deps import get_current_user, get_db
from app.core.config import Settings, get_settings
from app.models.schemas import (
    DashboardStatsResponse,
    EmailListResponse,
    UserResponse,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/statistics",
    response_model=DashboardStatsResponse,
    summary="Get recruitment email statistics and per-category counts",
)
async def get_statistics(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DashboardStatsResponse:
    return await DashboardService(db, settings).get_statistics(current_user.id)


@router.get(
    "/recent-emails",
    response_model=EmailListResponse,
    summary="Get the latest classified recruitment emails",
)
async def get_recent_emails(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=10, ge=1, le=50),
) -> EmailListResponse:
    items = await DashboardService(db, settings).get_recent_emails(
        current_user.id, limit=limit
    )
    return EmailListResponse(items=items, total=len(items))
