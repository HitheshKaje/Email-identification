"""Async Motor MongoDB client, TLS configuration, lifecycle management, and index initialization."""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from app.core.config import Settings

logger = logging.getLogger("jobmail.database")


class MongoDatabaseManager:
    """Holds the Motor client and database handle for the FastAPI lifespan."""

    def __init__(self) -> None:
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    async def connect(self, settings: Settings) -> AsyncIOMotorDatabase:
        client_kwargs: dict[str, object] = {
            "serverSelectionTimeoutMS": 5000,
            "maxPoolSize": settings.mongodb_max_pool_size,
            "minPoolSize": settings.mongodb_min_pool_size,
        }
        if settings.mongodb_tls_ca_file.strip():
            client_kwargs["tls"] = True
            client_kwargs["tlsCAFile"] = settings.mongodb_tls_ca_file.strip()
        elif settings.mongodb_uri.startswith("mongodb+srv://"):
            client_kwargs["tls"] = True

        self.client = AsyncIOMotorClient(
            settings.mongodb_uri,
            **client_kwargs,
        )
        self.db = self.client[settings.mongodb_db_name]
        await self.ping()
        await ensure_indexes(self.db)
        logger.info("Connected to MongoDB database '%s'.", settings.mongodb_db_name)
        return self.db

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("Closed MongoDB connection.")

    async def ping(self) -> bool:
        if self.db is None:
            return False
        await self.db.command("ping")
        return True


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create unique, query-performance, and TTL indexes across JobMail collections."""
    await db.users.create_index([("email", ASCENDING)], unique=True)

    await db.connected_accounts.create_index(
        [("user_id", ASCENDING), ("email_address", ASCENDING)],
        unique=True,
    )

    await db.emails.create_index(
        [("account_id", ASCENDING), ("gmail_message_id", ASCENDING)],
        unique=True,
    )
    await db.emails.create_index(
        [("user_id", ASCENDING), ("category", ASCENDING), ("received_at", DESCENDING)]
    )
    await db.emails.create_index(
        [("user_id", ASCENDING), ("received_at", DESCENDING)]
    )

    await db.notifications.create_index(
        [("user_id", ASCENDING), ("email_id", ASCENDING)],
        unique=True,
    )
    await db.notifications.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)]
    )

    await db.classification_feedback.create_index(
        [("user_id", ASCENDING), ("email_id", ASCENDING)]
    )

    await db.device_tokens.create_index(
        [("user_id", ASCENDING), ("token", ASCENDING)],
        unique=True,
    )
    await db.device_tokens.create_index([("token", ASCENDING)])

    await db.oauth_states.create_index([("state", ASCENDING)], unique=True)
    await db.oauth_states.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
    )

    await db.sync_history.create_index(
        [("user_id", ASCENDING), ("started_at", DESCENDING)]
    )

    # Phase 2 & 9: Sessions, verification/reset tokens, security audit trail, rate limits
    await db.sessions.create_index([("session_id", ASCENDING)], unique=True)
    await db.sessions.create_index([("user_id", ASCENDING), ("revoked_at", ASCENDING)])
    await db.sessions.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
    )

    await db.verification_tokens.create_index([("token_hash", ASCENDING)], unique=True)
    await db.verification_tokens.create_index([("user_id", ASCENDING), ("purpose", ASCENDING)])
    await db.verification_tokens.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
    )

    await db.security_events.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    await db.security_events.create_index([("event_type", ASCENDING), ("created_at", DESCENDING)])
    await db.security_events.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
    )

    await db.rate_limits.create_index([("key", ASCENDING)], unique=True)
    await db.rate_limits.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
    )


db_manager = MongoDatabaseManager()
