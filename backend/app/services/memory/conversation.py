import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.chat import ChatMessage, ChatSession

logger = structlog.get_logger("memory.conversation")
settings = get_settings()


class ConversationMemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_history(
        self,
        session_id: uuid.UUID,
        last_n_turns: int | None = None,
    ) -> Sequence[ChatMessage]:
        """Fetch chronological message history for a session, bounded by last N turns."""
        limit_turns = last_n_turns or settings.CHAT_HISTORY_TURNS
        # Each turn consists of user + assistant message (2 messages)
        max_messages = limit_turns * 2

        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(max_messages)
        )
        result = await self.db.execute(query)
        messages_desc = result.scalars().all()
        # Return in ascending chronological order
        return list(reversed(messages_desc))

    @staticmethod
    def format_history_for_prompt(
        messages: Sequence[ChatMessage],
        max_chars_per_msg: int = 800,
    ) -> list[dict[str, str]]:
        """Format history turns into role/content dicts for LLM prompt."""
        formatted: list[dict[str, str]] = []
        for msg in messages:
            role = "user" if msg.role == "user" else "assistant"
            content = msg.content[:max_chars_per_msg].strip()
            formatted.append({"role": role, "content": content})
        return formatted

    @staticmethod
    def format_history_for_rewrite(
        messages: Sequence[ChatMessage],
        max_chars_per_msg: int = 400,
    ) -> str:
        """Format history turns into Student/Assistant dialogue for query rewriting."""
        lines = []
        for msg in messages:
            speaker = "Student" if msg.role == "user" else "Assistant"
            clean_text = msg.content[:max_chars_per_msg].strip().replace("\n", " ")
            lines.append(f"{speaker}: {clean_text}")
        return "\n".join(lines)

    async def add_user_message(
        self,
        session: ChatSession,
        content: str,
    ) -> ChatMessage:
        """Persist user question and update session activity timestamp."""
        msg = ChatMessage(
            session_id=session.id,
            role="user",
            content=content,
        )
        self.db.add(msg)
        session.updated_at = datetime.now(UTC)

        # Automatically derive session title from first question if default
        if session.title in ("New Conversation", "New Chat", ""):
            clean_title = content[:50].strip().replace("—", ", ").replace("--", ", ")
            session.title = clean_title

        await self.db.flush()
        return msg

    async def add_assistant_message(
        self,
        session_id: uuid.UUID,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """Persist assistant answer and source citations."""
        msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=content,
            citations=citations or [],
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def set_message_feedback(
        self,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        rating: int,
        comment: str | None = None,
    ) -> ChatMessage | None:
        """Attach user feedback (1 for positive, -1 for negative) to an assistant message."""
        result = await self.db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
        msg = result.scalar_one_or_none()
        if not msg:
            return None

        feedback_data: dict[str, Any] = {
            "rating": 1 if rating > 0 else -1,
            "comment": comment.strip() if comment else None,
            "user_id": str(user_id),
            "created_at": datetime.now(UTC).isoformat(),
        }
        msg.feedback = feedback_data
        await self.db.commit()
        await self.db.refresh(msg)
        logger.info(
            "message_feedback_recorded",
            message_id=str(message_id),
            rating=feedback_data["rating"],
            user_id=str(user_id),
        )
        return msg

    async def clear_session_history(self, session_id: uuid.UUID) -> int:
        """Delete all messages belonging to a session while keeping the session."""
        stmt = delete(ChatMessage).where(ChatMessage.session_id == session_id)
        result = await self.db.execute(stmt)
        count = int(getattr(result, "rowcount", 0) or 0)
        await self.db.commit()
        logger.info("session_history_cleared", session_id=str(session_id), messages_deleted=count)
        return count
