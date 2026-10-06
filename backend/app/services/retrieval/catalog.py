import time
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CACHE_TTL_SECONDS = 60.0
_cache: tuple[float, list["CatalogEntry"]] | None = None


@dataclass(frozen=True)
class CatalogEntry:
    document_id: uuid.UUID
    source_path: str
    title: str


async def get_document_catalog(db: AsyncSession) -> list[CatalogEntry]:
    """Short list of indexed documents, shown to the router so it can pick where to look."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]

    rows = await db.execute(
        text(
            "SELECT d.id, d.source_path, d.title FROM documents d "
            "WHERE EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = d.id) "
            "ORDER BY d.source_path"
        )
    )
    entries = [
        CatalogEntry(row.id, row.source_path or "", row.title or "")
        for row in rows
        if row.source_path
    ]
    _cache = (now, entries)
    return entries
