"""In-app notifications, device token registration, alert preferences, and push dispatch."""

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from app.core.exceptions import NotFoundError
from app.models.enums import EmailCategory
from app.models.schemas import (
    DeviceRegisterRequest,
    NotificationPreferencesSchema,
    NotificationResponse,
)
from app.notifications.fcm_service import FCMDispatcher
from app.services.db_utils import parse_object_id


def _notification_doc_to_response(doc: dict) -> NotificationResponse:
    return NotificationResponse(
        id=str(doc["_id"]),
        email_id=doc["email_id"],
        title=doc["title"],
        message=doc["message"],
        category=EmailCategory(doc.get("category", EmailCategory.JOB.value)),
        created_at=doc["created_at"],
        is_read=bool(doc.get("is_read", False)),
    )


def _category_enabled(
    prefs: NotificationPreferencesSchema, category: EmailCategory
) -> bool:
    mapping = {
        EmailCategory.JOB: prefs.job_opportunities,
        EmailCategory.INTERNSHIP: prefs.internship_opportunities,
        EmailCategory.INTERVIEW: prefs.interview_invitations,
        EmailCategory.ASSESSMENT: prefs.online_assessments,
        EmailCategory.RECRUITMENT_DRIVE: prefs.recruitment_drives,
        EmailCategory.OFFER_LETTER: prefs.offer_letters,
        EmailCategory.APPLICATION_UPDATE: prefs.application_updates,
    }
    return mapping.get(category, False)


def build_notification_copy(
    category: EmailCategory,
    *,
    company_name: str | None,
    job_role: str | None,
) -> tuple[str, str]:
    company = company_name or "a recruiter"
    role_prefix = f"{job_role} " if job_role else ""
    if category == EmailCategory.INTERVIEW:
        return (
            "New Interview Invitation!",
            f"You have received an interview invitation from {company}.",
        )
    if category == EmailCategory.INTERNSHIP:
        return (
            "New Internship Opportunity!",
            f"A new {role_prefix}internship email from {company} has arrived.",
        )
    if category == EmailCategory.OFFER_LETTER:
        return (
            "New Offer Letter!",
            f"You have received an offer letter from {company}.",
        )
    if category == EmailCategory.ASSESSMENT:
        return (
            "New Assessment Invitation!",
            f"An online assessment invitation from {company} has arrived.",
        )
    if category == EmailCategory.RECRUITMENT_DRIVE:
        return (
            "New Recruitment Drive!",
            f"A new placement or recruitment announcement from {company} has arrived.",
        )
    if category == EmailCategory.APPLICATION_UPDATE:
        return (
            "Application Status Update",
            f"Your application update from {company} is ready to review.",
        )
    return (
        "New Job Opportunity!",
        f"A new {role_prefix}job opportunity from {company} has arrived.",
    )


class NotificationService:
    """Manages MongoDB-backed user notifications, FCM device tokens, and preferences."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        fcm_dispatcher: FCMDispatcher | None = None,
    ) -> None:
        self._db = db
        self._fcm = fcm_dispatcher or FCMDispatcher()

    async def list_notifications(
        self, user_id: str, limit: int = 50
    ) -> list[NotificationResponse]:
        cursor = (
            self._db.notifications.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_notification_doc_to_response(doc) for doc in docs]

    async def mark_read(
        self, user_id: str, notification_id: str, is_read: bool = True
    ) -> NotificationResponse:
        oid = parse_object_id(notification_id, "Notification")
        doc = await self._db.notifications.find_one_and_update(
            {"_id": oid, "user_id": user_id},
            {"$set": {"is_read": is_read}},
            return_document=True,
        )
        if not doc:
            raise NotFoundError("Notification not found.")
        return _notification_doc_to_response(doc)

    async def register_device(
        self, user_id: str, payload: DeviceRegisterRequest
    ) -> None:
        # Ensure physical device tokens cannot remain bound to a previous user on shared devices.
        await self._db.device_tokens.delete_many(
            {"token": payload.token, "user_id": {"$ne": user_id}}
        )
        await self._db.device_tokens.update_one(
            {"user_id": user_id, "token": payload.token},
            {
                "$set": {
                    "platform": payload.platform,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def get_preferences(self, user_id: str) -> NotificationPreferencesSchema:
        oid = parse_object_id(user_id, "User")
        doc = await self._db.users.find_one(
            {"_id": oid}, {"notification_preferences": 1}
        )
        raw = (doc or {}).get("notification_preferences")
        if isinstance(raw, dict):
            return NotificationPreferencesSchema(**raw)
        return NotificationPreferencesSchema()

    async def update_preferences(
        self, user_id: str, prefs: NotificationPreferencesSchema
    ) -> NotificationPreferencesSchema:
        oid = parse_object_id(user_id, "User")
        await self._db.users.update_one(
            {"_id": oid},
            {"$set": {"notification_preferences": prefs.model_dump()}},
        )
        return prefs

    async def notify_for_new_email(
        self,
        *,
        user_id: str,
        email_id: str,
        category: EmailCategory,
        company_name: str | None = None,
        job_role: str | None = None,
    ) -> bool:
        """Create deduplicated in-app notification and dispatch FCM push when enabled."""
        if category in (EmailCategory.OTHER, EmailCategory.REJECTION):
            return False

        prefs = await self.get_preferences(user_id)
        if not prefs.push_enabled or not _category_enabled(prefs, category):
            return False

        title, message = build_notification_copy(
            category,
            company_name=company_name,
            job_role=job_role,
        )
        try:
            await self._db.notifications.insert_one(
                {
                    "user_id": user_id,
                    "email_id": email_id,
                    "title": title,
                    "message": message,
                    "category": category.value,
                    "created_at": datetime.now(timezone.utc),
                    "is_read": False,
                }
            )
        except DuplicateKeyError:
            return False

        token_docs = await self._db.device_tokens.find(
            {"user_id": user_id},
            projection={"token": 1},
        ).to_list(length=20)
        tokens = [str(d["token"]) for d in token_docs if d.get("token")]
        if tokens:
            await self._fcm.send_to_tokens(
                tokens,
                title=title,
                body=message,
                data={"email_id": email_id, "category": category.value},
            )
        return True
