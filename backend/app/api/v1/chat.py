import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User, UserRole
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    ChatStreamRequest,
    MessageFeedbackCreate,
)
from app.services.chat.llm_stream import GroqChatStreamService
from app.services.chat.prompts import GREETING_MESSAGE
from app.services.memory import ConversationMemoryService, QueryRewriter
from app.services.retrieval.hybrid_search import HybridSearchService
from app.services.retrieval.reranker import RerankerService

logger = structlog.get_logger("api.chat")

router = APIRouter(prefix="/chat", tags=["Chat & RAG"])


def _is_greeting(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False
    import re

    normalized = re.sub(r"[^\w\s']", "", normalized)
    return normalized in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
    }


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create chat session",
)
async def create_chat_session(
    data: ChatSessionCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionResponse:
    """Create a new conversational session for the authenticated user."""
    title = data.title if (data and data.title) else "New Conversation"
    session = ChatSession(user_id=current_user.id, title=title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
    )


@router.get(
    "/sessions",
    response_model=list[ChatSessionResponse],
    summary="List chat sessions",
)
async def list_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatSessionResponse]:
    """List chat sessions for the current user (or all if admin)."""
    query = select(
        ChatSession,
        func.count(ChatMessage.id).label("msg_count"),
    ).outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)

    if current_user.role != UserRole.ADMIN.value:
        query = query.where(ChatSession.user_id == current_user.id)

    query = query.group_by(ChatSession.id).order_by(ChatSession.updated_at.desc())
    result = await db.execute(query)

    sessions = []
    for row in result:
        sess, count = row[0], row[1]
        sessions.append(
            ChatSessionResponse(
                id=sess.id,
                user_id=sess.user_id,
                title=sess.title,
                created_at=sess.created_at,
                updated_at=sess.updated_at,
                message_count=count,
            )
        )
    return sessions


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetailResponse,
    summary="Get chat session details and message history",
)
async def get_chat_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionDetailResponse:
    """Fetch session with all historical messages."""
    query = (
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.user_id != current_user.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return ChatSessionDetailResponse.model_validate(session)


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Rename chat session",
)
async def rename_chat_session(
    session_id: uuid.UUID,
    data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionResponse:
    """Rename a chat session owned by the current user."""
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not data.title or not data.title.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Title required"
        )

    session.title = data.title.strip()
    await db.commit()
    await db.refresh(session)
    count = await db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)
    )
    return ChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=count or 0,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete chat session",
)
async def delete_chat_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a chat session and all associated messages."""
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.user_id != current_user.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await db.delete(session)
    await db.commit()


async def _sse_generator(
    user_query: str,
    session: ChatSession,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Execute RAG pipeline with conversation memory, query rewrite, and yield SSE events."""
    memory = ConversationMemoryService(db)

    if _is_greeting(user_query):
        await memory.add_user_message(session, user_query)
        assistant_msg = await memory.add_assistant_message(
            session_id=session.id,
            content=GREETING_MESSAGE,
            citations=[],
        )
        done_payload = {
            "event": "done",
            "data": {
                "session_id": str(session.id),
                "message_id": str(assistant_msg.id),
                "full_text": GREETING_MESSAGE,
                "fallback": False,
            },
        }
        yield f"data: {json.dumps({'event': 'sources', 'data': {'citations': []}})}\n\n"
        yield f"data: {json.dumps({'event': 'token', 'data': {'token': GREETING_MESSAGE}})}\n\n"
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    # 1. Fetch message history for query rewrite and context (last N turns)
    history = await memory.get_history(session.id)

    # 2. Query rewrite using conversation memory
    standalone_query = await QueryRewriter.rewrite_query(user_query, history)
    yield f"data: {json.dumps({'event': 'query_rewrite', 'data': {'rewritten_query': standalone_query}})}\n\n"

    # 3. Hybrid search (vector + full-text with RRF)
    hybrid_service = HybridSearchService(db)
    candidates = await hybrid_service.search(standalone_query)

    # 4. Reranking with the configured lightweight cross-encoder
    reranked_chunks = await RerankerService.rerank(standalone_query, candidates)

    # 5. Save user message to memory
    await memory.add_user_message(session, user_query)

    # 6. Stream answer from Groq
    full_answer = ""
    citations_data: list[dict[str, Any]] = []
    fallback = False

    async for chunk in GroqChatStreamService.stream_answer(
        question=standalone_query,
        retrieved_chunks=reranked_chunks,
        chat_history=history,
    ):
        event_type = chunk.get("type")
        if event_type == "sources":
            citations_data = chunk.get("citations", [])
            yield f"data: {json.dumps({'event': 'sources', 'data': {'citations': citations_data}})}\n\n"
        elif event_type == "token":
            token = chunk.get("token", "")
            yield f"data: {json.dumps({'event': 'token', 'data': {'token': token}})}\n\n"
        elif event_type == "done":
            full_answer = chunk.get("full_text", "")
            fallback = chunk.get("fallback", False)

    # 7. Persist assistant message in memory
    assistant_msg = await memory.add_assistant_message(
        session_id=session.id,
        content=full_answer,
        citations=citations_data,
    )

    # 8. Emit final done event
    done_payload = {
        "event": "done",
        "data": {
            "session_id": str(session.id),
            "message_id": str(assistant_msg.id),
            "full_text": full_answer,
            "fallback": fallback,
        },
    }
    yield f"data: {json.dumps(done_payload)}\n\n"


@router.post(
    "/sessions/{session_id}/message",
    summary="Send message in existing session and stream answer via SSE",
)
async def send_message_in_session(
    session_id: uuid.UUID,
    data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send question in an existing conversation session and receive a streaming response."""
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.user_id != current_user.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return StreamingResponse(
        _sse_generator(data.content, session, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/message",
    summary="Send message and stream answer via SSE (creates session if not logged in or specified)",
)
async def send_message_quick(
    data: ChatMessageCreate,
    session_id: uuid.UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Quick chat endpoint. If session_id is not provided, automatically creates a new session."""
    session: ChatSession | None = None

    if session_id:
        result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if (
            current_user
            and session.user_id != current_user.id
            and current_user.role != UserRole.ADMIN.value
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    else:
        # Resolve user
        user_to_assign = current_user
        if not user_to_assign:
            # Fallback to system admin user for anonymous browsing
            admin_res = await db.execute(
                select(User).where(User.role == UserRole.ADMIN.value).limit(1)
            )
            user_to_assign = admin_res.scalar_one_or_none()
            if not user_to_assign:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Default user unavailable",
                )

        session = ChatSession(
            user_id=user_to_assign.id,
            title=data.content[:50].strip(),
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

    return StreamingResponse(
        _sse_generator(data.content, session, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/stream",
    summary="Stream answer via SSE",
)
async def chat_stream(
    data: ChatStreamRequest,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream answer via SSE matching Section 8 API contract."""
    return await send_message_quick(
        data=ChatMessageCreate(content=data.content),
        session_id=data.session_id,
        current_user=current_user,
        db=db,
    )


@router.post(
    "/sessions/{session_id}/clear",
    summary="Clear message history in session",
)
async def clear_session_messages(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clear all messages from a conversation session while preserving the session container."""
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    memory = ConversationMemoryService(db)
    cleared_count = await memory.clear_session_history(session_id)
    return {"message": "Session history cleared", "deleted_count": cleared_count}


@router.post(
    "/messages/{message_id}/feedback",
    response_model=ChatMessageResponse,
    summary="Submit user feedback on assistant message",
)
async def submit_message_feedback(
    message_id: uuid.UUID,
    feedback_in: MessageFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    """Submit thumbs-up (1) or thumbs-down (-1) rating with optional comment."""
    result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    sess_res = await db.execute(select(ChatSession).where(ChatSession.id == msg.session_id))
    session = sess_res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.user_id != current_user.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    memory = ConversationMemoryService(db)
    updated_msg = await memory.set_message_feedback(
        message_id=message_id,
        user_id=current_user.id,
        rating=feedback_in.rating,
        comment=feedback_in.comment,
    )
    if not updated_msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    return ChatMessageResponse.model_validate(updated_msg)
