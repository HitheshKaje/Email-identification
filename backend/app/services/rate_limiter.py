"""Shared MongoDB-backed (multi-instance safe) rate limiting and abuse detection."""

from datetime import datetime, timedelta, timezone
import math
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from app.core.config import Settings
from app.core.exceptions import RateLimitError
from app.services.security_audit_service import SecurityAuditService


def extract_client_ip(request: Request) -> str:
    """Extract client IP respecting X-Forwarded-For cleanly without spoofing multi-hop chains."""
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return "unknown"


def extract_device_info(request: Request) -> str:
    ua = request.headers.get("user-agent", "Unknown Client").strip()
    return ua[:120] or "Unknown Client"


class SharedRateLimiter:
    """Enforces fixed-window per-IP and per-user quotas using atomic MongoDB counters."""

    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def enforce(
        self,
        *,
        bucket: str,
        identifier: str,
        limit: int,
        window_seconds: int,
        user_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        if not self._settings.rate_limit_enabled or limit <= 0:
            return

        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())
        window_id = now_ts // window_seconds
        window_end = datetime.fromtimestamp((window_id + 1) * window_seconds, tz=timezone.utc)
        key = f"{bucket}:{identifier}:{window_id}"

        doc = await self._db.rate_limits.find_one_and_update(
            {"key": key},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {
                    "bucket": bucket,
                    "created_at": now,
                    "expires_at": window_end + timedelta(seconds=5),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        count = int((doc or {}).get("count", 1))
        if count > limit:
            retry_after = max(1, math.ceil((window_end - now).total_seconds()))
            await SecurityAuditService(self._db).log_event(
                event_type="RATE_LIMIT_EXCEEDED",
                severity="medium",
                user_id=user_id,
                ip_address=ip_address,
                alert=count >= limit + 3,
                summary=f"Rate limit exceeded on {bucket} ({count}/{limit} in {window_seconds}s).",
            )
            raise RateLimitError(
                "Too many requests. Please slow down and try again shortly.",
                retry_after=retry_after,
            )
