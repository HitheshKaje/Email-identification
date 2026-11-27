"""Notifications feed, FCM token registration, and alert preference routes."""

from typing import Annotated
from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.api.deps import get_current_user, get_db
from app.models.schemas import (
    DeviceRegisterRequest,
    NotificationListResponse,
    NotificationPreferencesSchema,
    NotificationResponse,
    NotificationUpdateRequest,
    UserResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List notifications for the authenticated user",
)
async def list_notifications(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> NotificationListResponse:
    items = await NotificationService(db).list_notifications(current_user.id)
    return NotificationListResponse(items=items)


@router.post(
    "/register-device",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Register or update an FCM device token for push notifications",
)
async def register_device(
    payload: DeviceRegisterRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> None:
    await NotificationService(db).register_device(current_user.id, payload)


@router.get(
    "/preferences",
    response_model=NotificationPreferencesSchema,
    summary="Get the authenticated user's notification preferences",
)
async def get_preferences(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> NotificationPreferencesSchema:
    return await NotificationService(db).get_preferences(current_user.id)


@router.patch(
    "/preferences",
    response_model=NotificationPreferencesSchema,
    summary="Update the authenticated user's notification preferences",
)
async def update_preferences(
    payload: NotificationPreferencesSchema,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> NotificationPreferencesSchema:
    return await NotificationService(db).update_preferences(
        current_user.id, payload
    )


@router.patch(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Mark a notification as read or unread",
)
async def mark_notification_read(
    notification_id: str,
    payload: NotificationUpdateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> NotificationResponse:
    return await NotificationService(db).mark_read(
        current_user.id, notification_id, is_read=payload.is_read
    )
