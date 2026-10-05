import os
from collections.abc import AsyncGenerator

# Enforce testing environment for fast, deterministic mock model execution
os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "test"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app

settings = get_settings()

test_engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    future=True,
)

test_session_factory = async_sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(autouse=True)
def setup_db_override() -> None:
    app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
