import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.services.memory.conversation import ConversationMemoryService
from tests.test_chat_api import _get_authenticated_client


@pytest.mark.asyncio
async def test_conversation_memory_window(db_session: AsyncSession) -> None:
    # Create test user and session
    user = User(
        email=f"mem_test_{uuid.uuid4().hex[:6]}@g.bracu.ac.bd",
        hashed_password="hash",
        role="user",
    )
    db_session.add(user)
    await db_session.flush()

    session = ChatSession(user_id=user.id, title="Test Window")
    db_session.add(session)
    await db_session.flush()

    memory = ConversationMemoryService(db_session)

    # Insert 6 messages (3 turns)
    for i in range(3):
        await memory.add_user_message(session, f"User question {i + 1}")
        await memory.add_assistant_message(session.id, f"Assistant reply {i + 1}")

    # Window of last 2 turns should return last 4 messages in chronological order
    history = await memory.get_history(session.id, last_n_turns=2)
    assert len(history) == 4
    assert history[0].content == "User question 2"
    assert history[1].content == "Assistant reply 2"
    assert history[2].content == "User question 3"
    assert history[3].content == "Assistant reply 3"


@pytest.mark.asyncio
async def test_conversation_memory_formatting() -> None:
    msg1 = ChatMessage(session_id=uuid.uuid4(), role="user", content="Where is UB01?")
    msg2 = ChatMessage(session_id=uuid.uuid4(), role="assistant", content="UB01 is Building 1.")

    prompt_format = ConversationMemoryService.format_history_for_prompt([msg1, msg2])
    assert len(prompt_format) == 2
    assert prompt_format[0] == {"role": "user", "content": "Where is UB01?"}
    assert prompt_format[1] == {"role": "assistant", "content": "UB01 is Building 1."}

    rewrite_format = ConversationMemoryService.format_history_for_rewrite([msg1, msg2])
    assert "Student: Where is UB01?" in rewrite_format
    assert "Assistant: UB01 is Building 1." in rewrite_format


@pytest.mark.asyncio
async def test_conversation_memory_feedback_and_clear(db_session: AsyncSession) -> None:
    user = User(
        email=f"mem_test2_{uuid.uuid4().hex[:6]}@g.bracu.ac.bd",
        hashed_password="hash",
        role="user",
    )
    db_session.add(user)
    await db_session.flush()

    session = ChatSession(user_id=user.id, title="Test Feedback")
    db_session.add(session)
    await db_session.flush()

    memory = ConversationMemoryService(db_session)
    msg = await memory.add_assistant_message(session.id, "Here are the advising hours.")

    # Record feedback
    updated_msg = await memory.set_message_feedback(
        message_id=msg.id,
        user_id=user.id,
        rating=1,
        comment="Very helpful answer",
    )
    assert updated_msg is not None
    assert updated_msg.feedback is not None
    assert updated_msg.feedback["rating"] == 1
    assert updated_msg.feedback["comment"] == "Very helpful answer"

    # Clear history
    deleted = await memory.clear_session_history(session.id)
    assert deleted >= 1

    remaining = await memory.get_history(session.id)
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_feedback_and_clear_api_endpoints(async_client: AsyncClient) -> None:
    client = await _get_authenticated_client(
        async_client, f"fb_user_{uuid.uuid4().hex[:6]}@g.bracu.ac.bd"
    )

    # 1. Create session
    sess_res = await client.post("/api/v1/chat/sessions", json={"title": "Feedback Session"})
    assert sess_res.status_code == 201
    session_id = sess_res.json()["id"]

    # 2. Send message and get assistant response
    msg_res = await client.post(
        f"/api/v1/chat/sessions/{session_id}/message",
        json={"content": "What are the library hours?"},
    )
    assert msg_res.status_code == 200

    # Retrieve message ID from session detail
    detail = (await client.get(f"/api/v1/chat/sessions/{session_id}")).json()
    assert len(detail["messages"]) >= 2
    assistant_msg = [m for m in detail["messages"] if m["role"] == "assistant"][0]
    assistant_msg_id = assistant_msg["id"]

    # 3. Submit feedback
    fb_res = await client.post(
        f"/api/v1/chat/messages/{assistant_msg_id}/feedback",
        json={"rating": 1, "comment": "Accurate and fast!"},
    )
    assert fb_res.status_code == 200
    fb_data = fb_res.json()
    assert fb_data["feedback"]["rating"] == 1
    assert fb_data["feedback"]["comment"] == "Accurate and fast!"

    # 4. Clear session history
    clear_res = await client.post(f"/api/v1/chat/sessions/{session_id}/clear")
    assert clear_res.status_code == 200
    assert clear_res.json()["deleted_count"] >= 2

    # Verify session is empty now
    detail_after = (await client.get(f"/api/v1/chat/sessions/{session_id}")).json()
    assert len(detail_after["messages"]) == 0
