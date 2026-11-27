"""User-isolated recruitment email query, encrypted field decryption, search, and read-status services."""

from datetime import datetime, timezone
import math
from typing import Any
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.authentication.encryption import TokenEncryptor
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthorizationError, NotFoundError
from app.models.enums import EmailCategory
from app.models.schemas import EmailListResponse, EmailResponse
from app.services.db_utils import parse_object_id


def _decrypt_field(
    doc: dict[str, Any],
    *,
    encrypted_key: str,
    plain_key: str,
    encryptor: TokenEncryptor | None,
    default: str | None = "",
) -> str | None:
    enc_val = doc.get(encrypted_key)
    if isinstance(enc_val, str) and enc_val.strip() and encryptor is not None:
        try:
            return encryptor.decrypt(enc_val)
        except Exception:
            return default
    raw = doc.get(plain_key)
    if raw is None:
        return default
    return str(raw)


def _coerce_category(raw: object) -> EmailCategory:
    if isinstance(raw, EmailCategory):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().upper()
        try:
            return EmailCategory(normalized)
        except ValueError:
            pass
    return EmailCategory.OTHER


def _coerce_confidence(raw: object) -> float:
    if raw is None:
        return 0.0
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _coerce_received_at(raw: object) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def email_doc_to_response(
    doc: dict[str, Any],
    *,
    encryptor: TokenEncryptor | None = None,
) -> EmailResponse:
    sender = _decrypt_field(
        doc, encrypted_key="encrypted_sender", plain_key="sender", encryptor=encryptor, default="Unknown Sender"
    ) or "Unknown Sender"
    subject = _decrypt_field(
        doc, encrypted_key="encrypted_subject", plain_key="subject", encryptor=encryptor, default="(No Subject)"
    ) or "(No Subject)"
    body_preview = _decrypt_field(
        doc, encrypted_key="encrypted_body_preview", plain_key="body_preview", encryptor=encryptor, default=""
    ) or ""
    company_name = _decrypt_field(
        doc, encrypted_key="encrypted_company_name", plain_key="company_name", encryptor=encryptor, default=None
    )
    job_role = _decrypt_field(
        doc, encrypted_key="encrypted_job_role", plain_key="job_role", encryptor=encryptor, default=None
    )

    return EmailResponse(
        id=str(doc["_id"]),
        account_id=str(doc.get("account_id") or ""),
        gmail_message_id=str(doc.get("gmail_message_id") or doc["_id"]),
        sender=sender,
        subject=subject,
        body_preview=body_preview,
        received_at=_coerce_received_at(doc.get("received_at")),
        category=_coerce_category(doc.get("category")),
        confidence=_coerce_confidence(doc.get("confidence", 0.0)),
        company_name=company_name,
        job_role=job_role,
        is_read=bool(doc.get("is_read", False)),
        has_attachments=bool(doc.get("has_attachments", False)),
        attachment_names=[
            str(n) for n in (doc.get("attachment_names") or []) if isinstance(n, str)
        ][:10],
    )


class EmailService:
    """Queries and updates user-scoped classified emails in MongoDB."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        resolved = settings or get_settings()
        self._encryptor = TokenEncryptor(resolved.encryption_key_list)

    async def list_emails(
        self,
        user_id: str,
        *,
        query: str | None = None,
        category: EmailCategory | None = None,
        account_id: str | None = None,
        company: str | None = None,
        is_read: bool | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
        include_other: bool = False,
    ) -> EmailListResponse:
        mongo_filter: dict[str, Any] = {"user_id": user_id}

        if account_id and account_id.strip():
            clean_account_id = account_id.strip()
            if ObjectId.is_valid(clean_account_id):
                owner_doc = await self._db.connected_accounts.find_one(
                    {"_id": ObjectId(clean_account_id)},
                    projection={"user_id": 1},
                )
                if owner_doc and str(owner_doc.get("user_id")) != user_id:
                    raise AuthorizationError("You do not have access to this Gmail account.")
            mongo_filter["account_id"] = clean_account_id

        if category is not None:
            mongo_filter["category"] = category.value
        elif not include_other:
            mongo_filter["category"] = {"$ne": EmailCategory.OTHER.value}

        if is_read is not None:
            mongo_filter["is_read"] = is_read

        if start_date is not None or end_date is not None:
            date_filter: dict[str, Any] = {}
            if start_date is not None:
                date_filter["$gte"] = start_date
            if end_date is not None:
                date_filter["$lte"] = end_date
            mongo_filter["received_at"] = date_filter

        q_norm = (query or "").strip().lower()
        company_norm = (company or "").strip().lower()

        if not q_norm and not company_norm:
            total = await self._db.emails.count_documents(mongo_filter)
            cursor = (
                self._db.emails.find(mongo_filter)
                .sort("received_at", -1)
                .skip(skip)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            return EmailListResponse(
                items=[email_doc_to_response(doc, encryptor=self._encryptor) for doc in docs],
                total=total,
            )

        # Decrypt owning user's bounded records in memory for encrypted text filtering.
        cursor = self._db.emails.find(mongo_filter).sort("received_at", -1)
        docs = await cursor.to_list(length=2000)
        matched: list[EmailResponse] = []
        for doc in docs:
            item = email_doc_to_response(doc, encryptor=self._encryptor)
            if company_norm and company_norm not in (item.company_name or "").lower():
                continue
            if q_norm:
                haystack = " ".join(
                    [
                        item.subject,
                        item.sender,
                        item.company_name or "",
                        item.job_role or "",
                        item.body_preview,
                    ]
                ).lower()
                if q_norm not in haystack:
                    continue
            matched.append(item)

        return EmailListResponse(
            items=matched[skip : skip + limit],
            total=len(matched),
        )

    async def get_email_by_id(self, user_id: str, email_id: str) -> EmailResponse:
        oid = parse_object_id(email_id, "Email")
        doc = await self._db.emails.find_one({"_id": oid, "user_id": user_id})
        if not doc:
            raise NotFoundError("Email not found.")
        return email_doc_to_response(doc, encryptor=self._encryptor)

    async def update_read_status(
        self, user_id: str, email_id: str, is_read: bool
    ) -> EmailResponse:
        oid = parse_object_id(email_id, "Email")
        doc = await self._db.emails.find_one_and_update(
            {"_id": oid, "user_id": user_id},
            {"$set": {"is_read": is_read}},
            return_document=True,
        )
        if not doc:
            raise NotFoundError("Email not found.")
        return email_doc_to_response(doc, encryptor=self._encryptor)
