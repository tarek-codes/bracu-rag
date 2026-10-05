import os
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.document import IngestionJob
from app.services.ingestion.pipeline import IngestionPipeline, IngestionStats

logger = structlog.get_logger("tasks.ingestion")


async def run_file_ingestion_task(
    job_id: uuid.UUID,
    file_path: str,
    content_bytes: bytes,
    title: str | None = None,
    source_type: str = "upload",
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            logger.error("job_not_found", job_id=str(job_id))
            return

        job.status = "processing"
        job.updated_at = datetime.now(UTC)
        await db.commit()

        stats = IngestionStats()
        pipeline = IngestionPipeline(db)

        try:
            await pipeline.ingest_file(
                file_path=file_path,
                content_bytes=content_bytes,
                title=title,
                source_type=source_type,
                stats=stats,
            )
            job.status = "done"
            job.stats = stats.to_dict()
            job.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info("job_completed_success", job_id=str(job_id), stats=stats.to_dict())
        except Exception as exc:
            logger.error("job_failed", job_id=str(job_id), error=str(exc), exc_info=True)
            job.status = "failed"
            job.error_message = str(exc)
            job.stats = stats.to_dict()
            job.updated_at = datetime.now(UTC)
            await db.commit()


async def run_url_ingestion_task(
    job_id: uuid.UUID,
    url: str,
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return

        job.status = "processing"
        job.updated_at = datetime.now(UTC)
        await db.commit()

        stats = IngestionStats()
        pipeline = IngestionPipeline(db)

        try:
            await pipeline.ingest_url(url=url, stats=stats)
            job.status = "done"
            job.stats = stats.to_dict()
            job.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info("url_job_completed", job_id=str(job_id), stats=stats.to_dict())
        except Exception as exc:
            logger.error("url_job_failed", job_id=str(job_id), error=str(exc), exc_info=True)
            job.status = "failed"
            job.error_message = str(exc)
            job.stats = stats.to_dict()
            job.updated_at = datetime.now(UTC)
            await db.commit()


async def run_bulk_directory_ingest(
    job_id: uuid.UUID,
    directory_path: str,
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return

        job.status = "processing"
        job.updated_at = datetime.now(UTC)
        await db.commit()

        stats = IngestionStats()
        pipeline = IngestionPipeline(db)

        try:
            if not os.path.exists(directory_path):
                raise ValueError(f"Directory does not exist: {directory_path}")

            for root, _, files in os.walk(directory_path):
                for file_name in files:
                    ext = os.path.splitext(file_name)[1].lower()
                    if ext in (".md", ".pdf", ".txt", ".docx"):
                        full_path = os.path.join(root, file_name)
                        rel_path = os.path.relpath(full_path, directory_path)
                        try:
                            with open(full_path, "rb") as f:
                                file_bytes = f.read()
                            await pipeline.ingest_file(
                                file_path=rel_path,
                                content_bytes=file_bytes,
                                source_type="bulk",
                                stats=stats,
                            )
                        except Exception as e:
                            logger.warning("bulk_file_failed", file=rel_path, error=str(e))
                            stats.files_failed += 1

            job.status = "done"
            job.stats = stats.to_dict()
            job.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info("bulk_ingestion_complete", stats=stats.to_dict())
        except Exception as exc:
            logger.error("bulk_ingestion_failed", error=str(exc), exc_info=True)
            job.status = "failed"
            job.error_message = str(exc)
            job.stats = stats.to_dict()
            job.updated_at = datetime.now(UTC)
            await db.commit()
