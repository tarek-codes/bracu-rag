import uuid

import pytest

from app.services.chat.llm_stream import (
    GroqChatStreamService,
    _normalize_answer_spacing,
    _sanitize_em_dashes,
    _strip_inline_sources,
)
from app.services.chat.prompts import REFUSAL_MESSAGE
from app.services.retrieval.hybrid_search import RetrievedChunk


def test_sanitize_em_dashes() -> None:
    text_with_dashes = "Undergraduate advising—starts in Spring 2026--check portal."
    clean = _sanitize_em_dashes(text_with_dashes)
    assert "—" not in clean
    assert "--" not in clean


def test_strip_inline_sources() -> None:
    assert _strip_inline_sources("Tuition is 8,250 BDT. [Source: Fees]") == "Tuition is 8,250 BDT."


def test_normalize_answer_spacing() -> None:
    answer = "Thestandardundergraduatetuitionfeeis**BDT8,250percredit**."
    context = "The standard undergraduate tuition fee is BDT 8,250 per credit."
    assert _normalize_answer_spacing(answer, context) == (
        "The standard undergraduate tuition fee is **BDT 8,250 per credit**."
    )


def test_normalize_answer_list_formatting() -> None:
    answer = "-Early Childhood Development (ECD)-Executive Master of Business Administration (EMBA)"
    assert _normalize_answer_spacing(answer) == (
        "- Early Childhood Development (ECD)\n- Executive Master of Business Administration (EMBA)"
    )


def test_normalize_biography_spacing_and_protected_contacts() -> None:
    answer = (
        "**Pollock Nag** isa **Lecturer** inthe **Computer Science and Engineering Department**. "
        "Heearneda B. Sc. andservedasa teachingassistant. "
        "*Email:*pollock.nag@bracu.ac.bd *Profile URL:*https://cse.bracu.ac.bd/faculty_profile/292/pollock_nag"
    )
    normalized = _normalize_answer_spacing(answer)
    assert "is a **Lecturer** in the **Computer Science and Engineering Department**." in normalized
    assert "He earned a B. Sc. and served as a teaching assistant." in normalized
    assert "pollock.nag@bracu.ac.bd" in normalized
    assert "https://cse.bracu.ac.bd/faculty_profile/292/pollock_nag" in normalized


def test_format_context() -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Student Handbook",
        content="Graduation requires 130 credits.",
        page=12,
        source_path="handbook.pdf",
    )
    formatted = GroqChatStreamService.format_context([(chunk, 0.92)])
    assert "Student Handbook" in formatted
    assert "Page: 12" in formatted
    assert "Graduation requires 130 credits." in formatted


def test_user_prompt_template_accepts_conversation_history() -> None:
    from app.services.chat.prompts import USER_RAG_TEMPLATE

    rendered = USER_RAG_TEMPLATE.format(
        context="Umme Jannat Taposhi is a Lecturer at BRAC University.",
        conversation_history="(No previous conversation.)",
        question="Who is Umme Jannat Taposhi?",
    )
    assert "Who is Umme Jannat Taposhi?" in rendered
    assert "conversation_history" not in rendered


def test_greeting_detection() -> None:
    from app.services.chat.intent_router import is_greeting as _is_greeting

    assert _is_greeting("Hi!") is True
    assert _is_greeting("good morning") is True
    assert _is_greeting("What is the tuition fee?") is False


@pytest.mark.asyncio
async def test_stream_answer_threshold_fallback() -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Unrelated Document",
        content="Unrelated text.",
    )
    # Score below SIMILARITY_THRESHOLD (0.5)
    events = []
    async for event in GroqChatStreamService.stream_answer(
        question="What is the tuition fee?",
        retrieved_chunks=[(chunk, 0.25)],
    ):
        events.append(event)

    types = [e["type"] for e in events]
    assert "sources" in types
    assert "token" in types
    assert "done" in types

    done_event = [e for e in events if e["type"] == "done"][0]
    assert done_event["fallback"] is True
    assert REFUSAL_MESSAGE in done_event["full_text"]


@pytest.mark.asyncio
async def test_stream_answer_success_mock() -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Tuition Policy",
        content="BRACUniversityislocatedin Dhaka,Bangladesh.",
    )
    events = []
    async for event in GroqChatStreamService.stream_answer(
        question="What is the tuition fee?",
        retrieved_chunks=[(chunk, 0.85)],
    ):
        events.append(event)

    types = [e["type"] for e in events]
    assert "sources" in types
    assert "token" in types
    assert "done" in types

    done_event = [e for e in events if e["type"] == "done"][0]
    assert done_event["fallback"] is False
    assert done_event["full_text"] == "BRAC University is located in Dhaka, Bangladesh."


@pytest.mark.asyncio
async def test_stream_falls_back_to_next_provider_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.chat import llm_stream

    async def failing(messages: list[dict[str, str]]):  # type: ignore[no-untyped-def]
        raise RuntimeError("402 Payment Required")
        yield ""

    async def working(messages: list[dict[str, str]]):  # type: ignore[no-untyped-def]
        yield "Tuition is BDT 8,250 per credit."

    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(llm_stream.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(llm_stream.settings, "OPENROUTER_API_KEY", "real-or")
    monkeypatch.setattr(llm_stream.settings, "GROQ_API_KEY", "real-groq")
    monkeypatch.setattr(GroqChatStreamService, "_stream_openrouter", staticmethod(failing))
    monkeypatch.setattr(GroqChatStreamService, "_stream_groq", staticmethod(working))

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Fees",
        content="Tuition is BDT 8,250 per credit.",
    )
    events = [e async for e in GroqChatStreamService.stream_answer("Tuition?", [(chunk, 0.9)])]
    done = events[-1]
    assert done["type"] == "done"
    assert done["fallback"] is False
    assert "8,250" in done["full_text"]


@pytest.mark.asyncio
async def test_stream_keeps_spaces_between_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.chat import llm_stream

    async def provider(messages: list[dict[str, str]], model: str):  # type: ignore[no-untyped-def]
        for piece in ["It", " was", " established", " in 2001", "."]:
            yield piece

    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(llm_stream.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(llm_stream.settings, "OPENROUTER_API_KEY", "real-or")
    monkeypatch.setattr(llm_stream.settings, "OPENROUTER_FALLBACK_MODELS", "")
    monkeypatch.setattr(llm_stream.settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(GroqChatStreamService, "_stream_openrouter", staticmethod(provider))
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), title="About", content="Founded 2001."
    )
    events = [e async for e in GroqChatStreamService.stream_answer("When?", [(chunk, 0.9)])]
    tokens = "".join(e["token"] for e in events if e["type"] == "token")
    assert tokens == "It was established in 2001."
    assert events[-1]["full_text"] == "It was established in 2001."


def test_sanitizer_keeps_markdown_table_separators() -> None:
    table = "| Course | Prerequisite |\n|---|---|\n| CSE221 | CSE220 |"
    assert _sanitize_em_dashes(table) == table
    assert _sanitize_em_dashes("|:--|--:|") == "|:--|--:|"
