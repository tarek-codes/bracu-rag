import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.health import HealthResponse

logger = structlog.get_logger("api.health")
settings = get_settings()

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description="Returns the operational status of the API service and its database connectivity.",
    responses={
        200: {
            "description": "System is healthy or running with degraded optional components.",
            "model": HealthResponse,
        }
    },
)
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    db_status = "connected"
    overall_status = "ok"
    details = {}

    try:
        result = await db.execute(text("SELECT 1;"))
        if result.scalar() != 1:
            db_status = "unresponsive"
            overall_status = "degraded"
    except Exception as exc:
        logger.warning("database_health_check_failed", error=str(exc))
        db_status = "disconnected"
        overall_status = "degraded"
        details["database_error"] = str(exc)

    return HealthResponse(
        status=overall_status,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        database=db_status,
        details=details if details else None,
    )
