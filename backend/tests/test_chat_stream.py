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
    from app.api.v1.chat import _is_greeting

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
