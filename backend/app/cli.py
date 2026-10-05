import asyncio
import os
from datetime import UTC, datetime

import click
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import async_session_factory, engine
from app.models.document import IngestionJob
from app.models.user import User, UserRole
from app.services.ingestion.pipeline import IngestionPipeline, IngestionStats


@click.group()
def cli() -> None:
    """BRAC University RAG CLI Administration Tools."""
    pass


async def _create_admin(email: str, password: str, full_name: str | None) -> None:
    async with async_session_factory() as session:
        normalized_email = email.lower().strip()
        result = await session.execute(select(User).where(User.email == normalized_email))
        existing = result.scalar_one_or_none()

        if existing:
            if existing.role != UserRole.ADMIN.value:
                existing.role = UserRole.ADMIN.value
                await session.commit()
                click.echo(f"Updated existing user '{normalized_email}' to role 'admin'.")
            else:
                click.echo(f"User '{normalized_email}' already exists and is an admin.")
            return

        admin_user = User(
            email=normalized_email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()
        click.echo(f"Admin user '{normalized_email}' created successfully.")

    await engine.dispose()


@cli.command("create-admin")
@click.option("--email", prompt=True, help="Admin user email address")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Admin user password",
)
@click.option("--full-name", default="System Administrator", help="Admin user full name")
def create_admin_command(email: str, password: str, full_name: str) -> None:
    """Create an administrator account."""
    asyncio.run(_create_admin(email, password, full_name))


async def _ingest_folder(target_dir: str) -> None:
    settings = get_settings()
    directory = target_dir or settings.KB_SOURCE_DIR

    if not directory or not os.path.isdir(directory):
        click.echo(f"Error: Directory '{directory}' does not exist or is not a directory.")
        return

    click.echo(f"Starting bulk ingestion from: {directory}")

    async with async_session_factory() as db:
        job = IngestionJob(
            source_type="bulk",
            status="processing",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        stats = IngestionStats()
        pipeline = IngestionPipeline(db)

        files_to_process = []
        for root, _, files in os.walk(directory):
            for file_name in sorted(files):
                ext = os.path.splitext(file_name)[1].lower()
                if ext in (".md", ".pdf", ".txt", ".docx"):
                    full_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(full_path, directory)
                    files_to_process.append((full_path, rel_path))

        click.echo(f"Found {len(files_to_process)} document(s) to inspect.")

        for i, (full_path, rel_path) in enumerate(files_to_process):
            try:
                click.echo(f"[{i + 1}/{len(files_to_process)}] Processing: {rel_path}")
                with open(full_path, "rb") as f:
                    content_bytes = f.read()
                await pipeline.ingest_file(
                    file_path=rel_path,
                    content_bytes=content_bytes,
                    source_type="bulk",
                    stats=stats,
                )
            except Exception as exc:
                await db.rollback()
                click.echo(f"Failed to ingest '{rel_path}': {exc}")
                stats.files_failed += 1

        job.status = "done"
        job.stats = stats.to_dict()
        job.updated_at = datetime.now(UTC)
        await db.commit()

    click.echo("\n================ Ingestion Summary ================")
    click.echo(f"Files Skipped (Unchanged): {stats.files_skipped}")
    click.echo(f"Files Added:              {stats.files_added}")
    click.echo(f"Files Updated:            {stats.files_updated}")
    click.echo(f"Files Failed:             {stats.files_failed}")
    click.echo("---------------------------------------------------")
    click.echo(f"Chunks Added:             {stats.chunks_added}")
    click.echo(f"Chunks Removed:           {stats.chunks_removed}")
    click.echo(f"Chunks Reused:            {stats.chunks_reused}")
    click.echo("===================================================\n")

    await engine.dispose()


@cli.command("ingest-folder")
@click.option(
    "--dir",
    "target_dir",
    default=None,
    help="Target directory containing knowledge documents (defaults to KB_SOURCE_DIR).",
)
def ingest_folder_command(target_dir: str | None) -> None:
    """Bulk import documents from KB_SOURCE_DIR."""
    asyncio.run(_ingest_folder(target_dir or ""))


if __name__ == "__main__":
    cli()
