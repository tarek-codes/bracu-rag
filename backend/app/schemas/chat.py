import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CitationItem(BaseModel):
    title: str
    source_path: str = ""
    page: int | None = None
    section: str | None = None
    snippet: str = ""
    score: float = 0.0


class ChatMessageCreate(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User question or message",
        examples=["What is the CSE tuition fee per credit?"],
    )


class ChatStreamRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User question or message",
        examples=["What is the CSE tuition fee per credit?"],
    )
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Optional existing session ID. A new session is created when omitted.",
    )


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    citations: list[dict[str, Any]] | None = None
    feedback: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageFeedbackCreate(BaseModel):
    rating: int = Field(..., ge=-1, le=1, description="1 for helpful, -1 for unhelpful")
    comment: str | None = Field(default=None, max_length=1000, description="Optional user comment")


class ChatSessionCreate(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=255,
        description="Optional title for the conversation",
        examples=["Admissions questions"],
    )


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatSessionDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = []

    model_config = {"from_attributes": True}
