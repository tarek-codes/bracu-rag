from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.db.session import get_db


@pytest.mark.asyncio
async def test_health_endpoint_degraded_when_no_db(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "environment" in data
    assert "database" in data
    # Verify request ID middleware
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_api_v1_health_endpoint(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "0.1.0"
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_health_with_mocked_db_ok(async_client: AsyncClient) -> None:
    class MockResult:
        def scalar(self) -> int:
            return 1

    class MockSession:
        async def execute(self, query: object) -> MockResult:
            return MockResult()

    async def mock_get_db() -> AsyncGenerator[MockSession, None]:
        yield MockSession()

    from app.main import app

    app.dependency_overrides[get_db] = mock_get_db

    try:
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
    finally:
        app.dependency_overrides.clear()
