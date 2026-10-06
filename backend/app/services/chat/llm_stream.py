import json
import os
import re
from collections.abc import AsyncGenerator, Callable, Sequence
from functools import partial
from typing import Any

import httpx
import structlog

from app.core.config import get_settings
from app.models.chat import ChatMessage
from app.services.chat.prompts import (
    INTENT_GUIDANCE,
    REFUSAL_MESSAGE,
    SYSTEM_RAG_PROMPT,
    USER_RAG_TEMPLATE,
)
from app.services.retrieval.hybrid_search import RetrievedChunk

logger = structlog.get_logger("chat.llm_stream")
settings = get_settings()


def _is_real_key(key: str) -> bool:
    return bool(key) and not key.startswith("dummy_")


def _sanitize_em_dashes(text: str) -> str:
    """Institutional constraint: remove em dashes from generated response."""
    # Only a double hyphen between two word characters is a dash. A bare "--" must survive
    # because markdown table separator rows (|---|---|) are made of it.
    return re.sub(r"(?<=\w)--(?=\w)", ", ", text.replace("—", ", "))


def _strip_inline_sources(text: str) -> str:
    """Keep source metadata in citation chips, not in the answer prose."""
    cleaned = re.sub(r"\s*\[source:[^\]]+\]", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(source:[^)]+\)", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _offline_answer(content: str) -> str:
    """Return readable reference text when the local development key is absent."""
    answer = re.sub(r"^#{1,6}\s+.*?(?:\n\n|\n)", "", content.strip(), count=1)
    answer = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", answer)
    answer = re.sub(r"\n\s*[-*_]\s*$", "", answer)
    return _strip_inline_sources(_sanitize_em_dashes(answer)).strip()


def _normalize_answer_spacing(text: str, context: str = "") -> str:
    """Repair occasional concatenated model tokens without changing Markdown content."""
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"§{len(protected) - 1}§"

    text = re.sub(
        r"https?://[^\s)\]]+|www\.[^\s)\]]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        protect,
        text,
    )
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", ", ")
    text = text.replace("BRACUniversity", "BRAC University")
    text = text.replace("islocatedin", "is located in")
    text = text.replace("****", "**")
    vocabulary = {word.lower() for word in re.findall(r"[A-Za-z]{2,}", context) if len(word) <= 30}
    vocabulary.update(
        {
            "a",
            "an",
            "and",
            "are",
            "all",
            "aid",
            "available",
            "at",
            "based",
            "bachelor",
            "bangladesh",
            "brac",
            "bracu",
            "by",
            "can",
            "completing",
            "contact",
            "compulsory",
            "cover",
            "cost",
            "degree",
            "department",
            "dhaka",
            "desk",
            "do",
            "education",
            "earned",
            "each",
            "email",
            "extension",
            "faculty",
            "found",
            "fall",
            "fee",
            "fees",
            "for",
            "from",
            "have",
            "he",
            "her",
            "highest",
            "human",
            "i",
            "include",
            "information",
            "interests",
            "https",
            "in",
            "is",
            "as",
            "latest",
            "located",
            "merit",
            "navigate",
            "not",
            "of",
            "on",
            "or",
            "official",
            "office",
            "overall",
            "per",
            "please",
            "portal",
            "profile",
            "programs",
            "question",
            "records",
            "registered",
            "relevant",
            "requirements",
            "residential",
            "research",
            "review",
            "scholarship",
            "section",
            "semester",
            "special",
            "sourced",
            "sufficient",
            "students",
            "substantially",
            "systems",
            "taken",
            "the",
            "this",
            "to",
            "tuition",
            "undergraduate",
            "university",
            "waiver",
            "waivers",
            "website",
            "visit",
            "with",
            "your",
            "admissions",
            "answer",
            "awards",
            "discounts",
            "financial",
            "reduce",
            "that",
            "these",
            "both",
            "computer",
            "distinction",
            "graduating",
            "program",
            "science",
            "she",
            "summer",
            "previously",
            "introductory",
            "actively",
            "assistant",
            "classical",
            "contests",
            "courses",
            "deep",
            "experience",
            "introduction",
            "learning",
            "lecturer",
            "object",
            "oriented",
            "participates",
            "pollock",
            "programming",
            "roles",
            "served",
            "teaching",
            "various",
            "vision",
        }
    )

    def split_run(match: re.Match[str]) -> str:
        run = match.group(0)
        lowered = run.lower()
        parts_by_position: dict[int, list[str]] = {len(lowered): []}
        for position in range(len(lowered) - 1, -1, -1):
            candidates = [word for word in vocabulary if lowered.startswith(word, position)]
            for word in sorted(candidates, key=len, reverse=True):
                end = position + len(word)
                suffix = parts_by_position.get(end)
                if suffix is not None:
                    parts_by_position[position] = [word, *suffix]
                    break
        best = parts_by_position.get(0)
        if best is None or len(best) == 1:
            return run
        return " ".join(
            run[position : position + len(word)] for position, word in _word_positions(best)
        )

    def _word_positions(words: list[str]) -> list[tuple[int, str]]:
        position = 0
        result = []
        for word in words:
            result.append((position, word))
            position += len(word)
        return result

    normalized = re.sub(r"[A-Za-z]{3,}", split_run, text)
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"([A-Za-z])(\d)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d)([A-Za-z])", r"\1 \2", normalized)
    normalized = re.sub(r"([%])([A-Za-z])", r"\1 \2", normalized)
    normalized = re.sub(r"(?<=[A-Za-z0-9])\(", " (", normalized)
    normalized = re.sub(r"\)(?=[A-Za-z])", ") ", normalized)
    normalized = re.sub(r"\)\s*-\s*(?=[A-Za-z])", ")\n- ", normalized)
    normalized = re.sub(r"(?m)^-(?=[A-Za-z])", "- ", normalized)
    normalized = re.sub(r"(?<![\w\n])-\s*(?=[A-Za-z])", "\n- ", normalized)
    normalized = re.sub(r"\bMAENG\b", "MA ENG", normalized)
    normalized = re.sub(r"\bMATESOL\b", "MA TESOL", normalized)
    normalized = re.sub(r"\bMSBIO\b", "MS BIO", normalized)
    normalized = re.sub(r"\bMSEEE\b", "MS EEE", normalized)
    normalized = re.sub(r"\*\*([^*]+)\*\*(?=[A-Za-z])", r"**\1** ", normalized)
    normalized = re.sub(r"([A-Za-z0-9])(\*\*)", r"\1 \2", normalized)
    normalized = re.sub(r"\*\*\s*([^*]+?)\s*\*\*", r"**\1**", normalized)
    normalized = re.sub(r"([a-z0-9])\*\*(?=[A-Z])", r"\1 **", normalized)
    normalized = re.sub(r"-\*\*", "- **", normalized)
    normalized = re.sub(r"\*\*(?=[a-z])", "** ", normalized)
    normalized = re.sub(r"\s+\*\*(?=[-.,:])", "**", normalized)
    normalized = re.sub(r"\*\*-\s*", "**\n- ", normalized)
    normalized = re.sub(r"(?<=[a-z)])-(?=[A-Z])", "\n- ", normalized)
    normalized = re.sub(r"\s+(\*\*)(?=[.!?,;:]|$)", r"\1", normalized)
    normalized = re.sub(r"([.!?,])([A-Za-z])", r"\1 \2", normalized)
    normalized = re.sub(r"\s+([,.!?;:])", r"\1", normalized)
    normalized = re.sub(r"(?i)(https?://|www\.)\s+", r"\1", normalized)
    normalized = re.sub(r"(?i)(bracu|ac|edu)\.\s+", r"\1.", normalized)
    normalized = re.sub(r"([.!?])\s*-\s*", r"\1\n- ", normalized)
    normalized = re.sub(r"(?<![A-Za-z])\*\*(?=[a-z])", "** ", normalized)
    normalized = re.sub(r":(?=[A-Za-z0-9])", ": ", normalized)
    normalized = re.sub(r"(?i)(bachelor|master)[’']sdegree", r"\1's degree", normalized)
    normalized = normalized.replace("jannat. taposhi", "jannat.taposhi")
    normalized = re.sub(r"Human\s*-\s*Computer", "Human-Computer", normalized)
    normalized = re.sub(r"Human\s*-\s*AI", "Human-AI", normalized)
    normalized = re.sub(
        r"\s*\*{1,2}Email:\*{1,2}\s*",
        "\n\n**Email:** ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\s*\*{1,2}Profile URL:\*{1,2}\s*",
        "\n\n**Profile URL:** ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+\*\*Contact:\*\*", "\n\n**Contact:**", normalized)
    normalized = re.sub(r"(?<=[a-z])\s+(These awards\b)", r". \1", normalized)
    normalized = re.sub(
        r"§(\d+)§",
        lambda match: protected[int(match.group(1))],
        normalized,
    )
    return normalized.strip()


class GroqChatStreamService:
    @classmethod
    def format_context(cls, chunks: list[tuple[RetrievedChunk, float]]) -> str:
        """Format retrieved chunks into structured context for the prompt."""
        context_blocks = []
        for i, (chunk, score) in enumerate(chunks, start=1):
            source_info = f"[Document {i}: {chunk.title}"
            if chunk.page is not None:
                source_info += f", Page: {chunk.page}"
            if chunk.source_path:
                source_info += f", File: {chunk.source_path}"
            source_info += f", Relevance: {score:.2f}]"

            block = f"{source_info}\n{chunk.content}"
            context_blocks.append(block)

        return "\n\n---\n\n".join(context_blocks)

    @classmethod
    async def stream_answer(
        cls,
        question: str,
        retrieved_chunks: list[tuple[RetrievedChunk, float]],
        chat_history: Sequence[ChatMessage] | None = None,
        intent_tags: frozenset[str] = frozenset(),
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream answer tokens and citation events.

        Yields dicts with event payloads:
        - {"type": "sources", "citations": [...]}
        - {"type": "token", "token": str}
        - {"type": "done", "full_text": str}
        """
        # Format citations metadata
        citations = []
        for chunk, score in retrieved_chunks:
            snippet = chunk.content[:200].strip().replace("\n", " ") + "..."
            citations.append(
                {
                    "title": chunk.title,
                    "source_path": chunk.source_path,
                    "page": chunk.page,
                    "snippet": snippet,
                    "score": score,
                }
            )

        # Emit sources event first
        yield {"type": "sources", "citations": citations}

        # Check threshold fallback
        top_score = retrieved_chunks[0][1] if retrieved_chunks else 0.0
        if not retrieved_chunks or top_score < settings.SIMILARITY_THRESHOLD:
            logger.info(
                "similarity_threshold_fallback_triggered",
                top_score=top_score,
                threshold=settings.SIMILARITY_THRESHOLD,
            )
            # Stream refusal message
            for word in REFUSAL_MESSAGE.split(" "):
                token = word + " "
                yield {"type": "token", "token": token}
            yield {"type": "done", "full_text": REFUSAL_MESSAGE, "fallback": True}
            return

        context_text = cls.format_context(retrieved_chunks)
        conversation_history = "\n".join(
            f"{'User' if message.role == 'user' else 'Assistant'}: {message.content[:800]}"
            for message in (
                list(chat_history)[-settings.CHAT_HISTORY_TURNS :] if chat_history else []
            )
        )
        user_content = USER_RAG_TEMPLATE.format(
            context=context_text,
            conversation_history=conversation_history or "(No previous conversation.)",
            question=question,
        )
        guidance = [INTENT_GUIDANCE[tag] for tag in sorted(intent_tags) if tag in INTENT_GUIDANCE]
        if guidance:
            user_content += "\nQuestion-specific guidance:\n" + "\n".join(
                f"- {line}" for line in guidance
            )

        # Handle testing / offline mode
        if (
            os.getenv("TESTING") == "1"
            or settings.ENVIRONMENT == "test"
            or (
                (
                    not settings.OPENROUTER_API_KEY
                    or settings.OPENROUTER_API_KEY.startswith("dummy_")
                )
                and (not settings.GROQ_API_KEY or settings.GROQ_API_KEY.startswith("dummy_"))
            )
        ):
            # Synthesize a deterministic test answer from top chunk
            top_chunk = retrieved_chunks[0][0]
            mock_answer = _normalize_answer_spacing(
                _offline_answer(top_chunk.content),
                top_chunk.content,
            )
            for word in mock_answer.split(" "):
                yield {"type": "token", "token": word + " "}
            yield {"type": "done", "full_text": mock_answer, "fallback": False}
            return

        # Prepare messages
        messages = [{"role": "system", "content": SYSTEM_RAG_PROMPT}]

        # Add recent conversation turns
        if chat_history:
            recent = list(chat_history)[-settings.CHAT_HISTORY_TURNS :]
            for msg in recent:
                messages.append(
                    {
                        "role": "user" if msg.role == "user" else "assistant",
                        "content": msg.content[:800],
                    }
                )

        messages.append({"role": "user", "content": user_content})

        full_text_acc: list[str] = []
        used_model: str | None = None
        used_provider: str | None = None
        providers: list[
            tuple[str, str, Callable[[list[dict[str, str]]], AsyncGenerator[str, None]]]
        ] = []
        if _is_real_key(settings.OPENROUTER_API_KEY):
            models = [settings.OPENROUTER_MODEL] + [
                m.strip() for m in settings.OPENROUTER_FALLBACK_MODELS.split(",") if m.strip()
            ]
            for model in dict.fromkeys(models):
                providers.append(
                    ("openrouter", model, partial(cls._stream_openrouter, model=model))
                )
        if _is_real_key(settings.GROQ_API_KEY):
            providers.append(("groq", settings.GROQ_ANSWER_MODEL, cls._stream_groq))

        try:
            for index, (provider_name, model_name, stream_provider) in enumerate(providers):
                try:
                    async for delta in stream_provider(messages):
                        # Never strip a delta: its leading space separates it from the last word.
                        sanitized = _sanitize_em_dashes(delta)
                        full_text_acc.append(sanitized)
                        yield {"type": "token", "token": sanitized}
                    used_model = model_name
                    used_provider = provider_name
                    break
                except Exception as exc:
                    # Switch providers only when nothing was streamed yet, otherwise the
                    # user would see a half answer followed by a different one.
                    if full_text_acc or index == len(providers) - 1:
                        raise
                    logger.warning(
                        "llm_provider_failed_trying_next",
                        provider=provider_name,
                        model=model_name,
                        error=str(exc),
                    )

            complete_answer = _strip_inline_sources("".join(full_text_acc))
            is_refusal = complete_answer.lower().startswith("i do not have sufficient information")
            yield {
                "type": "done",
                "full_text": complete_answer,
                "fallback": is_refusal,
                "model": used_model,
                "provider": used_provider,
            }

        except Exception as exc:
            logger.error("llm_stream_failed", error=str(exc), exc_info=True)
            error_fallback = (
                "An unexpected issue occurred while communicating with the answering service. "
                "Please retry or consult the official BRAC University website at https://www.bracu.ac.bd."
            )
            yield {"type": "token", "token": error_fallback}
            yield {"type": "done", "full_text": error_fallback, "fallback": True}

    @staticmethod
    async def _stream_openrouter(
        messages: list[dict[str, str]], model: str
    ) -> AsyncGenerator[str, None]:
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "BRAC University Chatbot",
        }
        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": settings.OPENROUTER_MAX_COMPLETION_TOKENS,
            "top_p": 1,
            "stream": True,
        }
        if settings.OPENROUTER_REASONING_EFFORT != "none":
            payload["reasoning"] = {"effort": settings.OPENROUTER_REASONING_EFFORT}

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            async with http_client.stream(
                "POST",
                f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk_data.get("choices")
                    if not choices:
                        continue
                    content = choices[0].get("delta", {}).get("content")
                    if content:
                        yield content

    @staticmethod
    async def _stream_groq(messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        from groq import AsyncGroq

        groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        chunk_stream = await groq_client.chat.completions.create(
            model=settings.GROQ_ANSWER_MODEL,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.1,
            max_completion_tokens=settings.GROQ_MAX_COMPLETION_TOKENS,
            top_p=1,
            reasoning_effort=settings.GROQ_REASONING_EFFORT,
            stream=True,
        )
        async for stream_chunk in chunk_stream:  # type: ignore[union-attr]
            delta = stream_chunk.choices[0].delta.content
            if delta:
                yield delta
