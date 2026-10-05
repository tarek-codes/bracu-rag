import asyncio
import hashlib
import os
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger("retrieval.embeddings")
settings = get_settings()

_model_instance: Any = None


def _use_mock_model() -> bool:
    return (
        os.getenv("TESTING") == "1"
        or settings.ENVIRONMENT == "test"
        or not settings.GROQ_API_KEY
        or settings.GROQ_API_KEY.startswith("dummy_")
    )


def _get_mock_embedding(text: str, dim: int = 384) -> list[float]:
    """Generate a deterministic normalized vector for testing or offline mode."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [((h[i % len(h)] / 255.0) * 2.0 - 1.0) for i in range(dim)]
    norm = sum(x * x for x in raw) ** 0.5
    if norm == 0:
        return [0.0] * dim
    return [round(x / norm, 6) for x in raw]


class EmbeddingService:
    @classmethod
    def get_model(cls) -> object:
        global _model_instance
        if _use_mock_model():
            return None

        if _model_instance is None:
            logger.info("loading_embedding_model", model_name=settings.EMBEDDING_MODEL)
            try:
                if settings.HF_TOKEN:
                    os.environ["HF_TOKEN"] = settings.HF_TOKEN
                    os.environ["HUGGING_FACE_HUB_TOKEN"] = settings.HF_TOKEN

                import torch

                # Restrict PyTorch to physical CPU cores to eliminate SMT thrashing
                torch.set_num_threads(4)
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    settings.EMBEDDING_MODEL,
                    trust_remote_code=True,
                )
                model.max_seq_length = 1024
                _model_instance = model
                logger.info("embedding_model_loaded", model_name=settings.EMBEDDING_MODEL)
            except Exception as exc:
                logger.warning(
                    "embedding_model_load_fallback",
                    model_name=settings.EMBEDDING_MODEL,
                    error=str(exc),
                )
                _model_instance = "MOCK"
        return _model_instance

    @classmethod
    def _sync_embed_documents(cls, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = cls.get_model()
        if model is None or model == "MOCK":
            return [_get_mock_embedding(t, settings.EMBEDDING_DIM) for t in texts]

        try:
            import torch

            with torch.inference_mode():
                # batch_size=8 keeps attention matrices and KV cache inside CPU L2/L3 cache
                embeddings = model.encode(  # type: ignore[attr-defined]
                    texts,
                    batch_size=8,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            return [vec.tolist() for vec in embeddings]
        except Exception as exc:
            logger.error("embedding_generation_failed", error=str(exc))
            return [_get_mock_embedding(t, settings.EMBEDDING_DIM) for t in texts]

    @classmethod
    def _sync_embed_query(cls, query: str) -> list[float]:
        model = cls.get_model()
        if model is None or model == "MOCK":
            return _get_mock_embedding(query, settings.EMBEDDING_DIM)

        try:
            import torch

            with torch.inference_mode():
                embedding = model.encode(  # type: ignore[attr-defined]
                    query,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            return embedding.tolist()  # type: ignore[no-any-return]
        except Exception as exc:
            logger.error("query_embedding_failed", error=str(exc))
            return _get_mock_embedding(query, settings.EMBEDDING_DIM)

    @classmethod
    async def embed_documents(cls, texts: list[str]) -> list[list[float]]:
        """Asynchronously compute embeddings in a thread pool."""
        return await asyncio.to_thread(cls._sync_embed_documents, texts)

    @classmethod
    async def embed_query(cls, query: str) -> list[float]:
        """Asynchronously compute query embedding in a thread pool."""
        return await asyncio.to_thread(cls._sync_embed_query, query)
