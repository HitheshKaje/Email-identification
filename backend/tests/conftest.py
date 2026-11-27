"""Pytest fixtures wired to an isolated test MongoDB database."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.core.config import Settings, get_settings
from app.database.mongodb import db_manager
from app.main import create_app

_TEST_COLLECTIONS = (
    "users",
    "connected_accounts",
    "emails",
    "notifications",
    "classification_feedback",
    "device_tokens",
    "oauth_states",
    "sync_history",
    "sessions",
    "verification_tokens",
    "security_events",
    "rate_limits",
)


@pytest_asyncio.fixture
async def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="jobmail_test",
        jwt_secret_key="test-only-jwt-secret-key-at-least-32-bytes-long",
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )


@pytest_asyncio.fixture
async def fastapi_app(test_settings: Settings):
    app = create_app(test_settings)
    db = await db_manager.connect(test_settings)
    for name in _TEST_COLLECTIONS:
        await db[name].delete_many({})

    app.dependency_overrides[get_settings] = lambda: test_settings
    yield app, db

    for name in _TEST_COLLECTIONS:
        await db[name].delete_many({})
    await db_manager.close()


@pytest_asyncio.fixture
async def client(fastapi_app):
    app, db = fastapi_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac, db
