import uuid
from typing import Any

import pytest

from app.services.vectorstore import chroma_store
from app.services.vectorstore.chroma_store import ChromaChunk, ChromaStore


class FakeCollection:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        for i, row_id in enumerate(ids):
            self.rows[row_id] = {"doc": documents[i], "meta": metadatas[i], "vec": embeddings[i]}

    def delete(self, ids: list[str] | None = None, where: dict[str, str] | None = None) -> None:
        for row_id in ids or []:
            self.rows.pop(row_id, None)
        if where:
            for row_id in [
                k for k, v in self.rows.items() if v["meta"]["document_id"] == where["document_id"]
            ]:
                del self.rows[row_id]


def _chunk(document_id: uuid.UUID, index: int) -> ChromaChunk:
    return ChromaChunk(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        content=f"chunk {index}",
        embedding=[0.1, 0.2],
        title=None,
        source_path="pages/a.md",
        page=None,
        chunk_index=index,
    )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeCollection:
    collection = FakeCollection()
    monkeypatch.setattr(chroma_store, "_collection", collection)
    monkeypatch.setattr(ChromaStore, "enabled", staticmethod(lambda: True))
    return collection


@pytest.mark.asyncio
async def test_upsert_and_delete_chunks(fake: FakeCollection) -> None:
    doc = uuid.uuid4()
    chunks = [_chunk(doc, 0), _chunk(doc, 1)]
    assert await ChromaStore.upsert_chunks(chunks) is True
    assert len(fake.rows) == 2
    row = fake.rows[str(chunks[0].chunk_id)]
    assert row["meta"] == {"document_id": str(doc), "source_path": "pages/a.md", "chunk_index": 0}

    assert await ChromaStore.delete_chunks([chunks[0].chunk_id]) is True
    assert list(fake.rows) == [str(chunks[1].chunk_id)]


@pytest.mark.asyncio
async def test_delete_document_removes_only_its_chunks(fake: FakeCollection) -> None:
    keep, drop = uuid.uuid4(), uuid.uuid4()
    await ChromaStore.upsert_chunks([_chunk(keep, 0), _chunk(drop, 0), _chunk(drop, 1)])
    await ChromaStore.delete_document(drop)
    assert len(fake.rows) == 1
    assert next(iter(fake.rows.values()))["meta"]["document_id"] == str(keep)


@pytest.mark.asyncio
async def test_chroma_failure_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def upsert(self, **_: Any) -> None:
            raise RuntimeError("cloud unreachable")

    monkeypatch.setattr(chroma_store, "_collection", Broken())
    monkeypatch.setattr(ChromaStore, "enabled", staticmethod(lambda: True))
    assert await ChromaStore.upsert_chunks([_chunk(uuid.uuid4(), 0)]) is False


@pytest.mark.asyncio
async def test_disabled_store_does_nothing() -> None:
    assert ChromaStore.enabled() is False
    assert await ChromaStore.upsert_chunks([_chunk(uuid.uuid4(), 0)]) is False
