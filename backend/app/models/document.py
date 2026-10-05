import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="file",
    )
    source_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        index=True,
    )
    file_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    meta_info: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    chunk_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    meta_info: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    embedding: Mapped[Any | None] = mapped_column(
        Vector(384),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationship
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="bulk",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )
    stats: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class EmbeddingConfig(Base):
    __tablename__ = "embedding_configs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    dimension: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1024,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
