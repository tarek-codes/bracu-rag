import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user_success(async_client: AsyncClient) -> None:
    unique_email = f"student_{uuid.uuid4().hex[:8]}@g.bracu.ac.bd"
    payload = {
        "email": unique_email,
        "password": "Password123!",
        "full_name": "Test Student",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == unique_email
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(async_client: AsyncClient) -> None:
    unique_email = f"student_{uuid.uuid4().hex[:8]}@g.bracu.ac.bd"
    payload = {
        "email": unique_email,
        "password": "Password123!",
        "full_name": "Initial Student",
    }
    first_resp = await async_client.post("/api/v1/auth/register", json=payload)
    assert first_resp.status_code == 201

    dup_payload = {
        "email": unique_email,
        "password": "AnotherPassword123!",
        "full_name": "Duplicate Student",
    }
    response = await async_client.post("/api/v1/auth/register", json=dup_payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient) -> None:
    unique_email = f"student_{uuid.uuid4().hex[:8]}@g.bracu.ac.bd"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "Password123!", "full_name": "Login Tester"},
    )

    payload = {
        "email": unique_email,
        "password": "Password123!",
    }
    response = await async_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == unique_email
    # Verify httpOnly cookies
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_password_fails(async_client: AsyncClient) -> None:
    unique_email = f"student_{uuid.uuid4().hex[:8]}@g.bracu.ac.bd"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "Password123!", "full_name": "Login Tester"},
    )

    payload = {
        "email": unique_email,
        "password": "WrongPassword123!",
    }
    response = await async_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_cookie(async_client: AsyncClient) -> None:
    unique_email = f"student_{uuid.uuid4().hex[:8]}@g.bracu.ac.bd"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "Password123!", "full_name": "Me Tester"},
    )

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "Password123!"},
    )
    access_cookie = login_resp.cookies["access_token"]
    async_client.cookies.set("access_token", access_cookie)

    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == unique_email


@pytest.mark.asyncio
async def test_token_refresh_and_logout(async_client: AsyncClient) -> None:
    unique_email = f"student_{uuid.uuid4().hex[:8]}@g.bracu.ac.bd"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "Password123!", "full_name": "Refresh Tester"},
    )

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "Password123!"},
    )
    refresh_cookie = login_resp.cookies["refresh_token"]
    async_client.cookies.set("refresh_token", refresh_cookie)

    # Refresh token
    refresh_resp = await async_client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
    new_refresh = refresh_resp.cookies["refresh_token"]
    async_client.cookies.set("refresh_token", new_refresh)

    # Logout
    logout_resp = await async_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert "Successfully logged out" in logout_resp.json()["message"]
