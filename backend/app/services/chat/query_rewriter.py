import os
from collections.abc import Sequence

import structlog

from app.core.config import get_settings
from app.models.chat import ChatMessage
from app.services.chat.prompts import QUERY_REWRITE_SYSTEM_PROMPT

logger = structlog.get_logger("chat.query_rewriter")
settings = get_settings()


class QueryRewriter:
    @classmethod
    async def rewrite_query(
        cls,
        query: str,
        chat_history: Sequence[ChatMessage] | None = None,
    ) -> str:
        """Reformulate a conversational follow-up into a standalone search query.

        If there is no history or the API key is not configured, returns the query unchanged.
        """
        trimmed = query.strip()
        if not trimmed:
            return ""

        if not chat_history:
            return trimmed

        # Only use recent turns (each turn has user + assistant messages)
        max_messages = settings.CHAT_HISTORY_TURNS * 2
        recent_history = list(chat_history)[-max_messages:]
        if not recent_history:
            return trimmed

        # If testing or mock environment
        if (
            os.getenv("TESTING") == "1"
            or settings.ENVIRONMENT == "test"
            or not settings.GROQ_API_KEY
            or settings.GROQ_API_KEY.startswith("dummy_")
        ):
            # In testing/offline mode, return query directly
            return trimmed

        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=settings.GROQ_API_KEY)

            # Build history text
            history_lines = []
            for msg in recent_history:
                role_label = "Student" if msg.role == "user" else "Assistant"
                # Truncate each historical message content to 400 chars to save tokens
                history_lines.append(f"{role_label}: {msg.content[:400]}")

            history_text = "\n".join(history_lines)
            user_prompt = (
                f"Conversation History:\n{history_text}\n\n"
                f"Follow-up Question: {trimmed}\n\n"
                f"Rewrite into a standalone question:"
            )

            response = await client.chat.completions.create(
                model=settings.GROQ_REWRITE_MODEL,
                messages=[
                    {"role": "system", "content": QUERY_REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=150,
            )

            rewritten = response.choices[0].message.content
            if rewritten and rewritten.strip():
                clean_rewritten = rewritten.strip().replace("—", ", ").replace("--", ", ")
                logger.info("query_rewritten", original=trimmed, rewritten=clean_rewritten)
                return clean_rewritten

            return trimmed
        except Exception as exc:
            logger.warning("query_rewrite_failed", query=trimmed, error=str(exc))
            return trimmed
