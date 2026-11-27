"""Async Motor MongoDB client, TLS configuration, connection pooling, lifecycle, and index initialization."""

import logging
try:
    import certifi
except ImportError:  # pragma: no cover - optional fallback if certifi is absent
    certifi = None  # type: ignore[assignment]
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
from app.core.config import Settings, _has_localhost_mongodb
from app.core.logging import sanitize_mongodb_uri

logger = logging.getLogger("jobmail.database")


class MongoDatabaseManager:
    """Holds the Motor client and database handle for the FastAPI lifespan."""

    def __init__(self) -> None:
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    async def connect(self, settings: Settings) -> AsyncIOMotorDatabase:
        uri = settings.mongodb_uri.strip()
        db_name = settings.mongodb_db_name.strip()

        if not uri:
            raise ValueError(
                "MONGODB_URI is not configured. Set MONGODB_URI to your MongoDB Atlas connection string."
            )
        if not uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError(
                "Invalid MONGODB_URI scheme. Expected a connection string starting with 'mongodb://' or 'mongodb+srv://'."
            )
        if settings.is_production and _has_localhost_mongodb(uri):
            raise ValueError(
                "MONGODB_URI cannot target localhost in production. Configure your MongoDB Atlas URI."
            )
        if not db_name:
            raise ValueError("MONGODB_DB_NAME must be configured to a non-empty database name.")

        client_kwargs: dict[str, object] = {
            "serverSelectionTimeoutMS": settings.mongodb_server_selection_timeout_ms,
            "connectTimeoutMS": settings.mongodb_connect_timeout_ms,
            "socketTimeoutMS": settings.mongodb_socket_timeout_ms,
            "maxPoolSize": settings.mongodb_max_pool_size,
            "minPoolSize": settings.mongodb_min_pool_size,
            "retryWrites": True,
            "retryReads": True,
            "appname": "jobmail-api",
        }
        if settings.mongodb_tls_ca_file.strip():
            client_kwargs["tls"] = True
            client_kwargs["tlsCAFile"] = settings.mongodb_tls_ca_file.strip()
        elif uri.startswith("mongodb+srv://") or "tls=true" in uri.lower() or "ssl=true" in uri.lower():
            client_kwargs["tls"] = True
            if certifi is not None:
                client_kwargs["tlsCAFile"] = certifi.where()

        safe_target = sanitize_mongodb_uri(uri)
        try:
            self.client = AsyncIOMotorClient(uri, **client_kwargs)
            self.db = self.client[db_name]
            await self.db.command("ping")
            await ensure_indexes(self.db)
        except Exception as exc:
            logger.error(
                "Failed to connect to MongoDB database '%s' (%s): %s",
                db_name,
                safe_target,
                type(exc).__name__,
            )
            await self.close()
            raise

        logger.info("Connected to MongoDB database '%s' (%s).", db_name, safe_target)
        return self.db

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("Closed MongoDB connection.")

    async def ping(self) -> bool:
        if self.client is None or self.db is None:
            return False
        try:
            await self.db.command("ping")
            return True
        except PyMongoError as exc:
            logger.warning("MongoDB health check failed: %s", type(exc).__name__)
            return False


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
