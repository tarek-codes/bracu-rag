"""Decide how to handle a chat message before any retrieval happens.

Cheap deterministic rules run first (so safety and small talk never depend on an LLM),
then one small LLM call classifies the rest and writes the standalone search query.
Only messages routed to KB_SEARCH reach hybrid search and the answering model.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

import structlog

from app.models.chat import ChatMessage
from app.services.chat.llm_client import complete_small
from app.services.chat.prompts import (
    CLARIFY_APPLY_MESSAGE,
    CLARIFY_COST_MESSAGE,
    CLARIFY_DATE_MESSAGE,
    CLARIFY_GENERIC_MESSAGE,
    CONFIDENTIAL_MESSAGE,
    GIBBERISH_MESSAGE,
    GREETING_MESSAGE,
    HARMFUL_MESSAGE,
    INJECTION_MESSAGE,
    OUT_OF_DOMAIN_MESSAGE,
    ROUTER_DOCUMENT_INSTRUCTIONS,
    ROUTER_SYSTEM_PROMPT,
    THANKS_MESSAGE,
)
from app.services.retrieval.catalog import CatalogEntry

logger = structlog.get_logger("chat.intent_router")


class Intent(StrEnum):
    KB_SEARCH = "kb_search"
    STATIC_REPLY = "static_reply"


@dataclass(frozen=True)
class RouteDecision:
    intent: Intent
    reason: str
    reply: str | None = None
    query: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)
    documents: tuple[str, ...] = ()


_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hi there",
    "hello there",
    "hey there",
    "good morning",
    "good afternoon",
    "good evening",
    "good day",
    "salam",
    "assalamualaikum",
    "assalamu alaikum",
    "how are you",
    "how are you doing",
    "whats up",
    "what's up",
}

_THANKS = {
    "thanks",
    "thank you",
    "thanks a lot",
    "thank you so much",
    "thanks so much",
    "thx",
    "ok",
    "okay",
    "ok thanks",
    "okay thanks",
    "okay got it",
    "ok got it",
    "got it",
    "great",
    "cool",
    "understood",
    "i see",
    "alright",
    "perfect",
}

_INJECTION = re.compile(
    r"ignore (all |any |your |the )*(previous|prior|above|earlier)? ?(instructions|rules|prompt)"
    r"|forget (all |your |the )*(instructions|rules|documents|university|previous)"
    r"|(reveal|show|print|tell me|repeat|leak).{0,30}(system prompt|your instructions|hidden instructions)"
    r"|system prompt"
    r"|pretend (you|that you) (have|are|can)"
    r"|you are now\b|act as (if|an? )|developer mode|jailbreak|\bdan mode\b",
    re.IGNORECASE,
)

_CONFIDENTIAL = re.compile(
    r"(another student|other students?'s|someone else'?s?|this student'?s?|that student'?s?"
    r"|my (friend|classmate|roommate)'?s?)\b.{0,40}"
    r"(grades?|cgpa|gpa|results?|phone|number|address|email|id\b|records?|password|marks)"
    r"|confidential (documents?|files?|records?|information)"
    r"|(show|give|leak).{0,20}(student|employee|staff) (records|data|database)",
    re.IGNORECASE,
)

_HARMFUL = re.compile(
    r"\bhack(ing)?\b.{0,30}(portal|website|server|system|account|university|grades?)"
    r"|bypass.{0,30}(admission|security|login|system|verification)"
    r"|(cheat|cheating) (in|on|during).{0,20}exam"
    r"|(fake|forge|forged|fabricate).{0,20}(certificate|transcript|documents?|result)"
    r"|(crack|steal|guess).{0,20}(password|credentials)"
    r"|\bsql injection\b|\bddos\b",
    re.IGNORECASE,
)

_KEYBOARD_RUN = re.compile(r"asdf|qwer|zxcv|hjkl|sdfg|dfgh|fghj|ghjk|uiop|wert|erty", re.IGNORECASE)

_UNIVERSITY_TERMS = re.compile(
    r"credit|tuition|fee|semester|course|gpa|cgpa|scholarship|waiver|admission|brac|bracu"
    r"|program|department|thesis|exam|grade|campus",
    re.IGNORECASE,
)

_PURE_MATH = re.compile(r"^[\d\s+\-*/x×÷().,%^=?]+$")
_UTILITY = re.compile(
    r"(what is|what's|calculate|compute|solve)?\s*[\d.,]+\s*%\s*of\s*[\d.,]+"
    r"|convert\s+[\d.,]+\s*\w+\s+(to|into)\s+\w+"
    r"|(what is|what's|calculate|compute)\s+[\d.,]+\s*[-+*/x×÷^]\s*[\d.,]+",
    re.IGNORECASE,
)

# Vague follow-ups that only make sense with prior context.
_AMBIGUOUS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"^(how much|what).{0,15}(does|do|is|are)?\s*(it|that|this|they)\s*(cost|charge)?\??$",
            re.IGNORECASE,
        ),
        CLARIFY_COST_MESSAGE,
    ),
    (
        re.compile(
            r"^(when|what time)\s+(does|do|is|are)\s+(it|that|this|they)\s*(start|begin|end|open)?\??$",
            re.IGNORECASE,
        ),
        CLARIFY_DATE_MESSAGE,
    ),
    (
        re.compile(
            r"^(can|could|may) i\s+(apply|register|join|enroll|enrol)( for (it|that|this))?\??$",
            re.IGNORECASE,
        ),
        CLARIFY_APPLY_MESSAGE,
    ),
    (
        re.compile(
            r"^(what about|and|how about)\s+(it|that|this|them)\??$|^(is|are) (it|that|this) (required|free|open)\??$",
            re.IGNORECASE,
        ),
        CLARIFY_GENERIC_MESSAGE,
    ),
)

_TAG_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "calculation",
        re.compile(
            r"\d.{0,60}(credits?|bdt|tk|taka)|(credits?|bdt|tk|taka).{0,60}\d"
            r"|how much (would|will|do|does).{0,40}(total|cost|pay)|total (tuition|cost|fee)",
            re.IGNORECASE,
        ),
    ),
    (
        "personal",
        re.compile(
            r"\b(i|i've|i'm|my)\b.{0,50}"
            r"(failed|fail|probation|retake|withdrew|credits? (done|completed)|have \d+ credits"
            r"|eligible|graduate|dropped)"
            r"|can i (graduate|register|continue|get|take|transfer)|am i (eligible|allowed)",
            re.IGNORECASE,
        ),
    ),
    (
        "recommendation",
        re.compile(
            r"\bshould i\b|\brecommend|which .{0,30}\b(better|best|should)\b|\bbest (course|department|program)",
            re.IGNORECASE,
        ),
    ),
    (
        "comparison",
        re.compile(
            r"difference between|\bcompare\b|\bversus\b|\bvs\.?\b|which is (cheaper|better|more)",
            re.IGNORECASE,
        ),
    ),
    (
        "future",
        re.compile(
            r"\bin (20[3-9]\d)\b|\bwill be\b.{0,30}(20\d\d|next|future)|who will (be|become)"
            r"|next (chair|dean|vc|vice.?chancellor|year'?s?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "verification",
        re.compile(
            r",\s*(right|correct|isn'?t it|no)\s*\?$|\bis it true\b|\btrue that\b|\bi heard\b"
            r"|every student (gets?|receives?)|\bfor free\b",
            re.IGNORECASE,
        ),
    ),
    (
        "procedure",
        re.compile(r"\bhow (do|can|should|to) i\b|\bhow to\b|\bsteps? to\b", re.IGNORECASE),
    ),
)


def _normalize(message: str) -> str:
    text = re.sub(r"[^\w\s']", " ", message.lower())
    return re.sub(r"\s+", " ", text).strip()


def is_greeting(message: str) -> bool:
    return _normalize(message) in _GREETINGS


def detect_tags(message: str) -> frozenset[str]:
    return frozenset(name for name, pattern in _TAG_RULES if pattern.search(message))


def _is_gibberish(message: str) -> bool:
    if not re.search(r"[A-Za-z0-9]", message):
        return True
    words = re.findall(r"[A-Za-z]{4,}", message)
    return bool(words) and all(_KEYBOARD_RUN.search(word) for word in words)


def _is_pure_utility(message: str) -> bool:
    if _UNIVERSITY_TERMS.search(message):
        return False
    stripped = message.strip()
    inner = re.sub(r"^(what is|what's|calculate|compute)\s+", "", stripped, flags=re.IGNORECASE)
    return bool(_PURE_MATH.match(inner) and re.search(r"\d", inner)) or bool(
        _UTILITY.search(stripped)
    )


def _static(reason: str, reply: str) -> RouteDecision:
    return RouteDecision(intent=Intent.STATIC_REPLY, reason=reason, reply=reply)


def _apply_rules(message: str, has_history: bool) -> RouteDecision | None:
    normalized = _normalize(message)
    if normalized in _GREETINGS:
        return _static("greeting", GREETING_MESSAGE)
    if normalized in _THANKS:
        return _static("thanks", THANKS_MESSAGE)
    if _INJECTION.search(message):
        return _static("prompt_injection", INJECTION_MESSAGE)
    if _HARMFUL.search(message):
        return _static("harmful", HARMFUL_MESSAGE)
    if _CONFIDENTIAL.search(message):
        return _static("confidential", CONFIDENTIAL_MESSAGE)
    if _is_gibberish(message):
        return _static("gibberish", GIBBERISH_MESSAGE)
    if _is_pure_utility(message):
        return _static("utility", OUT_OF_DOMAIN_MESSAGE)
    if not has_history:
        for pattern, clarification in _AMBIGUOUS:
            if pattern.match(message.strip()):
                return _static("ambiguous", clarification)
    return None


def _parse_classification(raw: str) -> dict[str, object] | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clean(text: object) -> str:
    return str(text or "").replace("—", ", ").replace("--", ", ").strip()


class IntentRouter:
    @classmethod
    async def route(
        cls,
        message: str,
        chat_history: Sequence[ChatMessage] | None,
        history_messages: int,
        catalog: Sequence[CatalogEntry] = (),
    ) -> RouteDecision:
        """Return what to do with a message. Never raises; defaults to a KB search."""
        decision = _apply_rules(message, bool(chat_history))
        if decision is not None:
            return decision

        tags = detect_tags(message)
        try:
            raw = await complete_small(
                cls._build_system_prompt(catalog),
                cls._build_user_prompt(message, chat_history, history_messages),
            )
        except Exception as exc:
            logger.warning("intent_classification_failed", error=str(exc))
            return RouteDecision(Intent.KB_SEARCH, "classifier_error", tags=tags)

        parsed = _parse_classification(raw) if raw else None
        if parsed is None:
            return RouteDecision(Intent.KB_SEARCH, "classifier_unavailable", tags=tags)

        label = _clean(parsed.get("intent")).lower()
        if label == "out_of_domain" and "calculation" not in tags:
            return _static("out_of_domain", OUT_OF_DOMAIN_MESSAGE)
        if label == "gibberish":
            return _static("gibberish", GIBBERISH_MESSAGE)
        if label == "ambiguous":
            return _static("ambiguous", _clean(parsed.get("reply")) or CLARIFY_GENERIC_MESSAGE)

        if parsed.get("mixed") is True:
            tags |= {"mixed"}
        return RouteDecision(
            Intent.KB_SEARCH,
            "kb_question",
            query=_clean(parsed.get("query")) or None,
            tags=tags,
            documents=cls._valid_documents(parsed.get("documents"), catalog),
        )

    @staticmethod
    def _build_system_prompt(catalog: Sequence[CatalogEntry]) -> str:
        if not catalog:
            return ROUTER_SYSTEM_PROMPT
        listing = "\n".join(f"- {entry.source_path} | {entry.title}" for entry in catalog)
        return f"{ROUTER_SYSTEM_PROMPT}{ROUTER_DOCUMENT_INSTRUCTIONS}\n{listing}"

    @staticmethod
    def _valid_documents(raw: object, catalog: Sequence[CatalogEntry]) -> tuple[str, ...]:
        """Keep only paths that really exist, so a hallucinated name cannot hide the KB."""
        if not isinstance(raw, list):
            return ()
        known = {entry.source_path for entry in catalog}
        chosen = dict.fromkeys(str(item).strip() for item in raw)
        return tuple(path for path in chosen if path in known)[:3]

    @staticmethod
    def _build_user_prompt(
        message: str,
        chat_history: Sequence[ChatMessage] | None,
        history_messages: int,
    ) -> str:
        recent = list(chat_history or [])[-history_messages:]
        lines = [
            f"{'Student' if msg.role == 'user' else 'Assistant'}: {msg.content[:400]}"
            for msg in recent
        ]
        history = "\n".join(lines) if lines else "(none)"
        return f"Conversation:\n{history}\n\nLatest user message:\n{message.strip()}"
