import uuid

import pytest

from app.services.retrieval.hybrid_search import RetrievedChunk
from app.services.retrieval.reranker import RerankerService, _sigmoid


def test_sigmoid() -> None:
    assert _sigmoid(0.0) == 0.5
    assert _sigmoid(100.0) == 1.0
    assert round(_sigmoid(-100.0), 4) == 0.0


@pytest.mark.asyncio
async def test_reranker_mock_fallback() -> None:
    chunk1 = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Doc 1",
        content="First relevant content",
        rrf_score=0.03,
    )
    chunk2 = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Doc 2",
        content="Second less relevant content",
        rrf_score=0.01,
    )

    ranked = await RerankerService.rerank("relevant content", [chunk1, chunk2], top_n=2)
    assert len(ranked) == 2
    # chunk1 has higher RRF score, so normalized score should be higher
    assert ranked[0][0].title == "Doc 1"
    assert ranked[0][1] >= ranked[1][1]
