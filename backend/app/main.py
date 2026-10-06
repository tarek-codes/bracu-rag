from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.users import router as users_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestLoggingMiddleware
from app.db.session import async_session_factory, engine
from app.models.document import IngestionJob
from app.services.retrieval.hybrid_search import HybridSearchService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Setup structured logging
    setup_logging()
    logger = get_logger("app.lifecycle")
    logger.info("application_starting", app_name=settings.APP_NAME, version=settings.APP_VERSION)

    # Recover any ingestion jobs stuck in processing from a prior server shutdown
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                update(IngestionJob)
                .where(IngestionJob.status == "processing")
                .values(
                    status="failed",
                    error_message="Aborted due to unexpected server restart",
                )
            )
            await db.commit()
            affected = getattr(result, "rowcount", 0)
            if affected > 0:
                logger.warning("recovered_dangling_ingestion_jobs", count=affected)
    except Exception as exc:
        logger.error("startup_job_recovery_failed", error=str(exc))

    # Load models and the vector index now so the first user question is not slow
    try:
        async with async_session_factory() as db:
            await HybridSearchService(db).warm_up()
        logger.info("retrieval_warmed_up")
    except Exception as exc:
        logger.warning("retrieval_warm_up_failed", error=str(exc))

    yield

    logger.info("application_shutting_down")
    await engine.dispose()
    logger.info("database_engine_disposed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Authenticated REST and Server-Sent Events API for the BRAC University Information "
        "Chatbot. Answers are grounded in the indexed BRAC University knowledge base. "
        "Use /docs for interactive Swagger documentation or /redoc for the reference view."
    ),
    summary="Grounded BRAC University information assistant API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "System",
            "description": "Health and service diagnostics.",
        },
        {
            "name": "Authentication",
            "description": "Account registration, cookie-based sessions, and current-user access.",
        },
        {
            "name": "Chat & RAG",
            "description": (
                "Conversation sessions and grounded knowledge-base answers. "
                "Chat answers are streamed as Server-Sent Events."
            ),
        },
        {
            "name": "Knowledge Base",
            "description": "Admin-only document ingestion, indexing, and job monitoring.",
        },
        {
            "name": "User Management",
            "description": "Admin-only user listing and role management.",
        },
    ],
    lifespan=lifespan,
)

# Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Request ID and Logging Middleware
app.add_middleware(RequestLoggingMiddleware)


# Root endpoint
@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs_url": "/docs",
        "health_url": "/health",
        "api_v1": "/api/v1",
    }


# Root-level health endpoint
app.include_router(health_router, prefix="", tags=["System"])

# API v1 routes
app.include_router(health_router, prefix="/api/v1", tags=["System"])
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
