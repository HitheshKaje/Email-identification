"""Email classification prediction and user-isolated feedback routes with rate limiting."""

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.api.deps import get_current_user, get_db
from app.core.config import Settings, get_settings
from app.models.schemas import (
    ClassificationFeedbackRequest,
    ClassificationFeedbackResponse,
    ClassificationPredictRequest,
    ClassificationPredictResponse,
    UserResponse,
)
from app.services.classification_service import ClassificationService
from app.services.rate_limiter import SharedRateLimiter, extract_client_ip

router = APIRouter(prefix="/classification", tags=["Classification"])


@router.post(
    "/predict",
    response_model=ClassificationPredictResponse,
    summary="Predict recruitment category for an email",
)
async def predict_email(
    request: Request,
    payload: ClassificationPredictRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClassificationPredictResponse:
    await SharedRateLimiter(db, settings).enforce(
        bucket="classification_predict",
        identifier=current_user.id,
        limit=40,
        window_seconds=60,
        user_id=current_user.id,
        ip_address=extract_client_ip(request),
    )
    return await ClassificationService(db, settings).predict(payload)


@router.post(
    "/feedback",
    response_model=ClassificationFeedbackResponse,
    summary="Record user correction for an email classification",
)
async def submit_feedback(
    request: Request,
    payload: ClassificationFeedbackRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClassificationFeedbackResponse:
    await SharedRateLimiter(db, settings).enforce(
        bucket="classification_feedback",
        identifier=current_user.id,
        limit=60,
        window_seconds=60,
        user_id=current_user.id,
        ip_address=extract_client_ip(request),
    )
    return await ClassificationService(db, settings).record_feedback(
        current_user.id,
        payload.email_id,
        payload.corrected_category,
    )
