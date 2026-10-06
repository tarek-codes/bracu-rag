# ruff: noqa: E402
import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncGenerator

# Enforce testing environment for fast, deterministic mock model execution
from app.core.config import get_settings

os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "test"

# Tests must never touch the real knowledge base, so they run on their own database.
_live_url = os.environ.get("DATABASE_URL") or get_settings().DATABASE_URL
TEST_DB_NAME = "bracu_rag_test"
_base_url, _, _live_db = _live_url.rpartition("/")
os.environ["DATABASE_URL"] = f"{_base_url}/{TEST_DB_NAME}"
get_settings.cache_clear()

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

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


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database() -> None:
    """Create the test database if missing and bring it to the latest migration."""
    import asyncpg

    async def ensure_database() -> None:
        admin_url = f"{_base_url}/postgres".replace("postgresql+asyncpg", "postgresql")
        conn = await asyncpg.connect(admin_url)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()

    asyncio.run(ensure_database())
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=os.environ.copy(),
    )
    # Several tests log in as this admin; the live database is no longer shared with tests.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "create-admin",
            "--email",
            "admin@bracu.ac.bd",
            "--password",
            "AdminPassword123!",
        ],
        check=True,
        env=os.environ.copy(),
    )
