import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_endpoints_require_authentication(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin_endpoints(async_client: AsyncClient) -> None:
    email = f"user_{uuid.uuid4().hex[:8]}@g.bracu.ac.bd"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Regular User"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    access_cookie = login_resp.cookies["access_token"]
    async_client.cookies.set("access_token", access_cookie)

    response = await async_client.get("/api/v1/users")
    assert response.status_code == 403
    assert "admin privileges" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_user_can_access_and_manage_users(async_client: AsyncClient) -> None:
    # Login as admin created via CLI
    admin_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@bracu.ac.bd", "password": "AdminPassword123!"},
    )
    assert admin_login.status_code == 200
    admin_cookie = admin_login.cookies["access_token"]
    async_client.cookies.set("access_token", admin_cookie)

    # List users
    response = await async_client.get("/api/v1/users?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert data["total"] >= 1
    assert len(data["users"]) > 0

    # Verify admin can inspect self
    me_resp = await async_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "admin@bracu.ac.bd"
    assert me_resp.json()["role"] == "admin"
