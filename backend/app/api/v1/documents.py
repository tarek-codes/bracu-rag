import os
import uuid

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import require_admin
from app.db.session import async_session_factory, get_db
from app.models.document import Document, DocumentChunk, IngestionJob
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.document import (
    BulkDocumentDeleteRequest,
    BulkDocumentDeleteResponse,
    ChunkResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    IngestionJobResponse,
    UrlIngestRequest,
)
from app.services.retrieval.embeddings import EmbeddingService
from app.services.vectorstore.chroma_store import ChromaStore
from app.tasks.ingestion import (
    run_file_ingestion_task,
    run_url_ingestion_task,
)

logger = structlog.get_logger("api.documents")

router = APIRouter(prefix="/documents", tags=["Knowledge Base"])


ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".docx"}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post(
    "/upload",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Document for Ingestion (Admin Only)",
    description="Accepts a document file (.pdf, .md, .txt, .docx) and processes it as an asynchronous background job.",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> IngestionJobResponse:
    filename = file.filename or "uploaded_file"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB",
        )

    job = IngestionJob(
        source_type="file",
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(
        run_file_ingestion_task,
        job_id=job.id,
        file_path=filename,
        content_bytes=content_bytes,
        source_type="upload",
    )

    logger.info("upload_job_queued", job_id=str(job.id), filename=filename)
    return IngestionJobResponse.model_validate(job)


@router.post(
    "/url",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest Web Page URL (Admin Only)",
    description="Queues a validated public URL to be scraped, extracted, and indexed as a background task.",
)
async def ingest_url_endpoint(
    payload: UrlIngestRequest,
    background_tasks: BackgroundTasks,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> IngestionJobResponse:
    job = IngestionJob(
        source_type="url",
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(
        run_url_ingestion_task,
        job_id=job.id,
        url=payload.url,
    )

    logger.info("url_ingest_job_queued", job_id=str(job.id), url=payload.url)
    return IngestionJobResponse.model_validate(job)


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Ingested Documents (Admin Only)",
    description="Retrieves a paginated list of indexed knowledge base documents.",
)
async def list_documents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, description="Search by title or path"),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    count_query = select(func.count(Document.id))
    query = (
        select(
            Document,
            func.count(DocumentChunk.id).label("chunks_count"),
        )
        .outerjoin(DocumentChunk, Document.id == DocumentChunk.document_id)
        .group_by(Document.id)
        .order_by(Document.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )

    if search:
        pattern = f"%{search.strip()}%"
        query = query.where((Document.title.ilike(pattern)) | (Document.source_path.ilike(pattern)))
        count_query = count_query.where(
            (Document.title.ilike(pattern)) | (Document.source_path.ilike(pattern))
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    results = await db.execute(query)
    rows = results.all()

    doc_responses: list[DocumentResponse] = []
    for doc, c_count in rows:
        d = DocumentResponse(
            id=doc.id,
            title=doc.title,
            source=doc.source,
            source_path=doc.source_path,
            file_size=doc.file_size,
            mime_type=doc.mime_type,
            chunks_count=c_count,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        doc_responses.append(d)

    return DocumentListResponse(documents=doc_responses, total=total)


@router.delete(
    "/bulk",
    response_model=BulkDocumentDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk Delete Documents (Admin Only)",
    description="Permanently deletes selected documents and their associated vector chunks.",
)
async def bulk_delete_documents(
    payload: BulkDocumentDeleteRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BulkDocumentDeleteResponse:
    result = await db.execute(select(Document).where(Document.id.in_(set(payload.ids))))
    documents = result.scalars().all()
    deleted_ids = [document.id for document in documents]
    for document in documents:
        await db.delete(document)
    await db.commit()
    for deleted_id in deleted_ids:
        await ChromaStore.delete_document(deleted_id)

    logger.info(
        "documents_bulk_deleted",
        deleted_count=len(documents),
        deleted_by=str(admin_user.id),
    )
    return BulkDocumentDeleteResponse(deleted_count=len(documents))


@router.get(
    "/jobs",
    response_model=list[IngestionJobResponse],
    status_code=status.HTTP_200_OK,
    summary="List Recent Ingestion Jobs (Admin Only)",
    description="Returns the latest ingestion jobs for status tracking.",
)
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[IngestionJobResponse]:
    result = await db.execute(
        select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)
    )
    jobs = result.scalars().all()
    return [IngestionJobResponse.model_validate(j) for j in jobs]


@router.get(
    "/jobs/{job_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ingestion Job Status (Admin Only)",
    description="Fetches current status, metrics, and logs for an asynchronous ingestion job.",
)
async def get_job_status(
    job_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> IngestionJobResponse:
    result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return IngestionJobResponse.model_validate(job)


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Details (Admin Only)",
    description="Returns detailed document metadata along with all constituent chunks.",
)
async def get_document(
    document_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetailResponse:
    result = await db.execute(
        select(Document).options(selectinload(Document.chunks)).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks_data = [
        ChunkResponse(
            id=c.id,
            chunk_index=c.chunk_index,
            title=c.title,
            page=c.page,
            content=c.content,
            chunk_hash=c.chunk_hash,
        )
        for c in doc.chunks
    ]

    return DocumentDetailResponse(
        id=doc.id,
        title=doc.title,
        source=doc.source,
        source_path=doc.source_path,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        chunks_count=len(chunks_data),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        content="\n\n".join(
            chunk.content for chunk in sorted(doc.chunks, key=lambda item: item.chunk_index)
        ),
        chunks=chunks_data,
    )


@router.delete(
    "/{document_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Document (Admin Only)",
    description="Permanently removes a document and deletes all associated vector chunks.",
)
async def delete_document(
    document_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await db.delete(doc)
    await db.commit()
    await ChromaStore.delete_document(document_id)
    logger.info("document_deleted", document_id=str(document_id))
    return MessageResponse(message=f"Document '{doc.title}' deleted successfully")


@router.post(
    "/{document_id}/reindex",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reindex Document (Admin Only)",
    description="Queues a reindexing job for the specified document.",
)
async def reindex_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> IngestionJobResponse:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    job = IngestionJob(
        source_type=doc.source or "reindex",
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if doc.source_path and (
        doc.source_path.startswith("http://") or doc.source_path.startswith("https://")
    ):
        background_tasks.add_task(
            run_url_ingestion_task,
            job_id=job.id,
            url=doc.source_path,
        )
    elif doc.source_path and os.path.isfile(doc.source_path):
        with open(doc.source_path, "rb") as f:
            content_bytes = f.read()
        background_tasks.add_task(
            run_file_ingestion_task,
            job_id=job.id,
            file_path=doc.source_path,
            content_bytes=content_bytes,
            title=doc.title,
            source_type=doc.source or "file",
        )
    else:

        async def _reindex_chunks_task(job_id: uuid.UUID, doc_id: uuid.UUID) -> None:
            async with async_session_factory() as s:
                j = await s.get(IngestionJob, job_id)
                if not j:
                    return
                j.status = "processing"
                await s.commit()
                chunks_res = await s.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
                )
                chunks = chunks_res.scalars().all()
                if chunks:
                    texts = [c.content for c in chunks]
                    embeddings = await EmbeddingService.embed_documents(texts)
                    for c, emb in zip(chunks, embeddings, strict=True):
                        c.embedding = emb
                    await s.commit()
                j.status = "done"
                j.stats = {"chunks_reindexed": len(chunks)}
                await s.commit()

        background_tasks.add_task(_reindex_chunks_task, job_id=job.id, doc_id=doc.id)

    logger.info("reindex_job_queued", job_id=str(job.id), document_id=str(document_id))
    return IngestionJobResponse.model_validate(job)
