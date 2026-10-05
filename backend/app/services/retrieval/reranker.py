import asyncio
import math
import os
import re
from typing import Any

import structlog

from app.core.config import get_settings
from app.services.retrieval.hybrid_search import RetrievedChunk

logger = structlog.get_logger("retrieval.reranker")
settings = get_settings()

_reranker_instance: Any = None


def _use_mock_model() -> bool:
    return (
        os.getenv("TESTING") == "1"
        or settings.ENVIRONMENT == "test"
        or settings.ENVIRONMENT == "development"
        or not settings.GROQ_API_KEY
        or settings.GROQ_API_KEY.startswith("dummy_")
    )


def _sigmoid(logit: float) -> float:
    """Map unbounded logits to 0.0 - 1.0 probability."""
    try:
        return 1.0 / (1.0 + math.exp(-logit))
    except OverflowError:
        return 0.0 if logit < 0 else 1.0


class RerankerService:
    @classmethod
    def get_model(cls) -> object:
        global _reranker_instance
        if _use_mock_model():
            return None

        if _reranker_instance is None:
            logger.info("loading_reranker_model", model_name=settings.RERANKER_MODEL)
            try:
                if settings.HF_TOKEN:
                    os.environ["HF_TOKEN"] = settings.HF_TOKEN
                    os.environ["HUGGING_FACE_HUB_TOKEN"] = settings.HF_TOKEN

                import torch

                torch.set_num_threads(4)
                from sentence_transformers import CrossEncoder

                model = CrossEncoder(
                    settings.RERANKER_MODEL,
                    trust_remote_code=True,
                    max_length=1024,
                )
                _reranker_instance = model
                logger.info("reranker_model_loaded", model_name=settings.RERANKER_MODEL)
            except Exception as exc:
                logger.warning(
                    "primary_reranker_failed_trying_fallback",
                    primary=settings.RERANKER_MODEL,
                    error=str(exc),
                )
                try:
                    from sentence_transformers import CrossEncoder

                    model = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=1024)
                    _reranker_instance = model
                    logger.info("fallback_reranker_loaded", model_name="BAAI/bge-reranker-v2-m3")
                except Exception as exc2:
                    logger.error("all_rerankers_failed_using_mock", error=str(exc2))
                    _reranker_instance = "MOCK"

        return _reranker_instance

    @classmethod
    def _sync_rerank(
        cls,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int,
    ) -> list[tuple[RetrievedChunk, float]]:
        if not candidates:
            return []

        model = cls.get_model()

        # If testing or mock mode, rank using RRF score
        if model is None or model == "MOCK":
            max_rrf_score = max((c.rrf_score for c in candidates), default=0.0)
            ranked = []
            query_terms = {
                term.lower() for term in re.findall(r"[A-Za-z0-9]+", query) if len(term) > 2
            }
            for c in candidates:
                # In offline mode RRF contains lexical ranking only. Normalize it
                # relative to the best lexical match so thresholding remains useful.
                norm_score = c.rrf_score / max_rrf_score if max_rrf_score else 0.0
                content_terms = {term.lower() for term in re.findall(r"[A-Za-z0-9]+", c.content)}
                lexical_score = (
                    len(query_terms & content_terms) / len(query_terms) if query_terms else 0.0
                )
                combined_score = (0.75 * lexical_score) + (0.25 * norm_score)
                ranked.append((c, round(combined_score, 4)))
            ranked.sort(key=lambda x: x[1], reverse=True)
            return ranked[:top_n]

        try:
            pairs = [(query, c.content) for c in candidates]
            import torch

            with torch.inference_mode():
                # CrossEncoder.predict
                logits = model.predict(pairs, batch_size=8)  # type: ignore[attr-defined]

            ranked_results: list[tuple[RetrievedChunk, float]] = []
            for chunk, logit in zip(candidates, logits, strict=True):
                score = _sigmoid(float(logit))
                ranked_results.append((chunk, round(score, 4)))

            ranked_results.sort(key=lambda x: x[1], reverse=True)
            return ranked_results[:top_n]
        except Exception as exc:
            logger.error("reranker_prediction_failed", error=str(exc))
            # Fallback to RRF ordering
            return [(c, round(min(c.rrf_score * 30.0, 1.0), 4)) for c in candidates[:top_n]]

    @classmethod
    async def rerank(
        cls,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[tuple[RetrievedChunk, float]]:
        """Asynchronously rerank candidate chunks in a thread pool."""
        limit = top_n or settings.RERANK_TOP_N
        return await asyncio.to_thread(cls._sync_rerank, query, candidates, limit)
