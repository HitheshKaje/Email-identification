"""Persistent security event auditing and suspicious-activity alerting."""

from datetime import datetime, timedelta, timezone
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging import redact_sensitive_text
from app.models.schemas import SecurityEventResponse

logger = logging.getLogger("jobmail.security")


class SecurityAuditService:
    """Records privacy-safe security audit events in MongoDB and structured security logs."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def log_event(
        self,
        *,
        event_type: str,
        summary: str,
        user_id: str | None = None,
        severity: str = "info",
        ip_address: str | None = None,
        metadata: dict[str, object] | None = None,
        alert: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        clean_summary = redact_sensitive_text(summary)[:300]
        clean_ip = (ip_address or "").strip()[:64] or None
        safe_meta = {
            k: redact_sensitive_text(str(v))[:120]
            for k, v in (metadata or {}).items()
            if k.lower() not in {"password", "token", "secret", "access_token", "refresh_token", "body"}
        }

        doc = {
            "user_id": user_id,
            "event_type": event_type,
            "severity": severity,
            "summary": clean_summary,
            "ip_address": clean_ip,
            "metadata": safe_meta,
            "alert": alert,
            "created_at": now,
            "expires_at": now + timedelta(days=365),
        }
        try:
            await self._db.security_events.insert_one(doc)
        except Exception as exc:
            logger.warning("Failed to persist security event %s: %s", event_type, type(exc).__name__)

        log_msg = "security_event=%s user=%s ip=%s alert=%s summary=%s"
        if alert or severity in {"high", "critical"}:
            logger.warning(log_msg, event_type, user_id or "-", clean_ip or "-", alert, clean_summary)
        else:
            logger.info(log_msg, event_type, user_id or "-", clean_ip or "-", alert, clean_summary)

    async def list_user_events(
        self, user_id: str, *, limit: int = 30
    ) -> list[SecurityEventResponse]:
        cursor = (
            self._db.security_events.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [
            SecurityEventResponse(
                id=str(doc["_id"]),
                event_type=str(doc.get("event_type", "UNKNOWN")),
                severity=str(doc.get("severity", "info")),
                summary=str(doc.get("summary", "")),
                ip_address=doc.get("ip_address"),
                created_at=doc["created_at"],
                alert=bool(doc.get("alert", False)),
            )
            for doc in docs
        ]
