"""Dashboard aggregation and decrypted recent recruitment emails service."""

from motor.motor_asyncio import AsyncIOMotorDatabase
from app.authentication.encryption import TokenEncryptor
from app.core.config import Settings, get_settings
from app.models.enums import EmailCategory
from app.models.schemas import DashboardStatsResponse, EmailResponse
from app.services.email_service import email_doc_to_response


class DashboardService:
    """Computes user-scoped career email statistics and recent classified messages."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        resolved = settings or get_settings()
        self._encryptor = TokenEncryptor(resolved.encryption_key_list)

    async def get_statistics(self, user_id: str) -> DashboardStatsResponse:
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "category": {"$ne": EmailCategory.OTHER.value},
                }
            },
            {
                "$group": {
                    "_id": "$category",
                    "count": {"$sum": 1},
                    "unread": {
                        "$sum": {"$cond": [{"$eq": ["$is_read", False]}, 1, 0]}
                    },
                }
            },
        ]
        rows = await self._db.emails.aggregate(pipeline).to_list(length=20)

        category_counts: dict[str, int] = {
            cat.value: 0 for cat in EmailCategory.job_categories()
        }
        total_job_emails = 0
        unread_count = 0

        for row in rows:
            cat_key = row.get("_id")
            count = int(row.get("count", 0))
            unread = int(row.get("unread", 0))
            if cat_key in category_counts:
                category_counts[cat_key] = count
            total_job_emails += count
            unread_count += unread

        total_processed_emails = await self._db.emails.count_documents(
            {"user_id": user_id}
        )

        return DashboardStatsResponse(
            total_processed_emails=total_processed_emails,
            total_job_emails=total_job_emails,
            new_opportunities=(
                category_counts[EmailCategory.JOB.value]
                + category_counts[EmailCategory.INTERNSHIP.value]
            ),
            interview_invitations=category_counts[EmailCategory.INTERVIEW.value],
            assessment_invitations=category_counts[EmailCategory.ASSESSMENT.value],
            unread_count=unread_count,
            category_counts=category_counts,
        )

    async def get_recent_emails(
        self, user_id: str, limit: int = 10
    ) -> list[EmailResponse]:
        cursor = (
            self._db.emails.find(
                {
                    "user_id": user_id,
                    "category": {"$ne": EmailCategory.OTHER.value},
                }
            )
            .sort("received_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [email_doc_to_response(doc, encryptor=self._encryptor) for doc in docs]
