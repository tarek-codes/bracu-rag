import pytest
from httpx import AsyncClient


async def _get_authenticated_client(
    async_client: AsyncClient, email: str = "chat_user@g.bracu.ac.bd"
) -> AsyncClient:
    # Try login first
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    if login_resp.status_code != 200:
        # Register new student user
        reg_resp = await async_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password123!", "full_name": "Chat Test User"},
        )
        assert reg_resp.status_code == 201
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        assert login_resp.status_code == 200

    token = login_resp.cookies["access_token"]
    async_client.cookies.set("access_token", token)
    return async_client


@pytest.mark.asyncio
async def test_create_and_list_chat_sessions(async_client: AsyncClient) -> None:
    client = await _get_authenticated_client(async_client, "session_user@g.bracu.ac.bd")

    # 1. Create a session
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={"title": "Admissions Inquiries"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Admissions Inquiries"
    session_id = data["id"]

    # 2. List sessions
    list_resp = await client.get("/api/v1/chat/sessions")
    assert list_resp.status_code == 200
    sessions = list_resp.json()
    assert len(sessions) >= 1
    assert any(s["id"] == session_id for s in sessions)

    # 3. Get session detail
    detail_resp = await client.get(f"/api/v1/chat/sessions/{session_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == session_id
    assert "messages" in detail

    # 4. Delete session
    del_resp = await client.delete(f"/api/v1/chat/sessions/{session_id}")
    assert del_resp.status_code == 204

    # 5. Verify deleted
    get_del = await client.get(f"/api/v1/chat/sessions/{session_id}")
    assert get_del.status_code == 404


@pytest.mark.asyncio
async def test_chat_message_streaming_endpoint(async_client: AsyncClient) -> None:
    client = await _get_authenticated_client(async_client, "stream_user@g.bracu.ac.bd")

    # Send message via quick chat endpoint
    resp = await client.post(
        "/api/v1/chat/message",
        json={"content": "What is the tuition fee per credit?"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # Read SSE text body
    text = resp.text
    assert "event" in text
    assert "token" in text
    assert "done" in text


@pytest.mark.asyncio
async def test_chat_stream_endpoint_contract(async_client: AsyncClient) -> None:
    client = await _get_authenticated_client(async_client, "stream_contract@g.bracu.ac.bd")

    # 1. Create a session
    sess_resp = await client.post("/api/v1/chat/sessions", json={"title": "Contract Session"})
    assert sess_resp.status_code == 201
    session_id = sess_resp.json()["id"]

    # 2. Call /api/v1/chat/stream with session_id
    resp = await client.post(
        "/api/v1/chat/stream",
        json={"content": "What is the grading policy?", "session_id": session_id},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert "done" in resp.text


@pytest.mark.asyncio
async def test_bulk_delete_chat_sessions(async_client: AsyncClient) -> None:
    client = await _get_authenticated_client(async_client, "bulk_user@g.bracu.ac.bd")

    # 1. Create multiple sessions
    s1 = await client.post("/api/v1/chat/sessions", json={"title": "Session 1"})
    s2 = await client.post("/api/v1/chat/sessions", json={"title": "Session 2"})
    assert s1.status_code == 201
    assert s2.status_code == 201

    id1 = s1.json()["id"]
    id2 = s2.json()["id"]

    # 2. Bulk delete sessions
    del_resp = await client.request(
        "DELETE",
        "/api/v1/chat/sessions/bulk",
        json={"ids": [id1, id2]},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_count"] == 2

    # 3. Verify deleted
    get1 = await client.get(f"/api/v1/chat/sessions/{id1}")
    get2 = await client.get(f"/api/v1/chat/sessions/{id2}")
    assert get1.status_code == 404
    assert get2.status_code == 404
