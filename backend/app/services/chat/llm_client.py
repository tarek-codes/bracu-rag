import os

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger("chat.llm_client")
settings = get_settings()


def _is_real_key(key: str) -> bool:
    return bool(key) and not key.startswith("dummy_")


def llm_available() -> bool:
    """True when a real provider key is configured and we are not in test mode."""
    if os.getenv("TESTING") == "1" or settings.ENVIRONMENT == "test":
        return False
    return _is_real_key(settings.OPENROUTER_API_KEY) or _is_real_key(settings.GROQ_API_KEY)


async def complete_small(
    system: str,
    user: str,
    max_tokens: int = 250,
) -> str | None:
    """One short, deterministic completion on the small rewrite model.

    Returns None when no provider is configured. Provider errors propagate so
    callers decide their own fallback.
    """
    if not llm_available():
        return None

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    if _is_real_key(settings.OPENROUTER_API_KEY):
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "BRAC University Chatbot",
        }
        payload: dict[str, object] = {
            "model": settings.OPENROUTER_REWRITE_MODEL,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            resp = await http_client.post(
                f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            content: str | None = resp.json()["choices"][0]["message"].get("content")
            return content

    from groq import AsyncGroq

    groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    response = await groq_client.chat.completions.create(
        model=settings.GROQ_REWRITE_MODEL,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
