"""User-isolated email classification service with encrypted feedback and zero cross-user data leakage."""

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.authentication.encryption import TokenEncryptor
from app.classification.nlp_classifier import get_classifier
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.models.enums import EmailCategory
from app.models.schemas import (
    ClassificationFeedbackResponse,
    ClassificationPredictRequest,
    ClassificationPredictResponse,
)
from app.services.db_utils import parse_object_id
from app.services.email_service import email_doc_to_response


class ClassificationService:
    """Classifies incoming recruitment emails and stores encrypted per-user correction feedback."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        resolved = settings or get_settings()
        self._encryptor = TokenEncryptor(resolved.encryption_key_list)
        self._classifier = get_classifier()

    async def predict(
        self, payload: ClassificationPredictRequest
    ) -> ClassificationPredictResponse:
        result = self._classifier.classify(
            subject=payload.subject,
            body=payload.body,
            sender=payload.sender,
        )
        return ClassificationPredictResponse(
            category=result.category,
            confidence=result.confidence,
            company_name=result.company_name,
            job_role=result.job_role,
        )

    async def record_feedback(
        self,
        user_id: str,
        email_id: str,
        corrected_category: EmailCategory,
    ) -> ClassificationFeedbackResponse:
        oid = parse_object_id(email_id, "Email")
        existing = await self._db.emails.find_one({"_id": oid, "user_id": user_id})
        if not existing:
            raise NotFoundError("Email not found.")

        decrypted = email_doc_to_response(existing, encryptor=self._encryptor)
        await self._db.emails.update_one(
            {"_id": oid, "user_id": user_id},
            {
                "$set": {
                    "category": corrected_category.value,
                    "confidence": 1.0,
                }
            },
        )
        await self._db.classification_feedback.insert_one(
            {
                "user_id": user_id,
                "email_id": email_id,
                "encrypted_subject": self._encryptor.encrypt_optional(decrypted.subject),
                "encrypted_body_preview": self._encryptor.encrypt_optional(
                    decrypted.body_preview
                ),
                "encrypted_sender": self._encryptor.encrypt_optional(decrypted.sender),
                "original_category": existing.get("category"),
                "corrected_category": corrected_category.value,
                "created_at": datetime.now(timezone.utc),
            }
        )
        return ClassificationFeedbackResponse(
            status="recorded",
            email_id=email_id,
            corrected_category=corrected_category,
        )

    async def retrain_from_feedback(
        self,
        *,
        user_id: str,
        save_to_disk: bool = False,
    ) -> int:
        """Evaluate user-isolated feedback samples for that user only (never mixing across users)."""
        cursor = self._db.classification_feedback.find(
            {"user_id": user_id},
            projection={
                "encrypted_subject": 1,
                "encrypted_body_preview": 1,
                "encrypted_sender": 1,
                "subject": 1,
                "body_preview": 1,
                "sender": 1,
                "corrected_category": 1,
            },
        )
        docs = await cursor.to_list(length=500)
        extra_samples = []
        for doc in docs:
            if not doc.get("corrected_category"):
                continue
            subject = (
                self._encryptor.decrypt_optional(doc.get("encrypted_subject"))
                or doc.get("subject", "")
            )
            body = (
                self._encryptor.decrypt_optional(doc.get("encrypted_body_preview"))
                or doc.get("body_preview", "")
            )
            sender = (
                self._encryptor.decrypt_optional(doc.get("encrypted_sender"))
                or doc.get("sender", "")
            )
            if subject or body:
                extra_samples.append(
                    {
                        "subject": subject,
                        "body": body,
                        "sender": sender,
                        "category": doc["corrected_category"],
                    }
                )
        return self._classifier.retrain(
            extra_samples=extra_samples,
            save_to_disk=save_to_disk,
        )
