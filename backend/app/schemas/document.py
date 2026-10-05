import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Document ID")
    title: str = Field(..., description="Document Title")
    source: str = Field(..., description="Source Type (file, url, upload)")
    source_path: str | None = Field(default=None, description="Original Path or URL")
    file_size: int | None = Field(default=None, description="Size in bytes")
    mime_type: str | None = Field(default=None, description="MIME type")
    chunks_count: int = Field(default=0, description="Total chunks indexed")
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Last updated timestamp")


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse] = Field(..., description="List of documents")
    total: int = Field(..., description="Total count of documents")


class BulkDocumentDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Document IDs to permanently delete",
    )


class BulkDocumentDeleteResponse(BaseModel):
    deleted_count: int = Field(..., description="Number of documents permanently deleted")


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Chunk ID")
    chunk_index: int = Field(..., description="Chunk index")
    title: str | None = Field(default=None, description="Section heading")
    page: int | None = Field(default=None, description="Page number")
    content: str = Field(..., description="Excerpt content")
    chunk_hash: str = Field(..., description="Content hash")


class DocumentDetailResponse(DocumentResponse):
    content: str = Field(..., description="Reconstructed indexed document content")
    chunks: list[ChunkResponse] = Field(default=[], description="Document chunks")


class UrlIngestRequest(BaseModel):
    url: str = Field(
        ...,
        description="Public HTTP or HTTPS web page URL to ingest",
        examples=["https://www.bracu.ac.bd/admissions/faqs-admissions"],
    )


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Job ID")
    source_type: str = Field(..., description="Source type (bulk, file, url)")
    status: str = Field(..., description="Job status: pending, processing, done, failed")
    stats: dict[str, Any] | None = Field(default=None, description="Processing statistics")
    error_message: str | None = Field(default=None, description="Failure reason if applicable")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Job update timestamp")
