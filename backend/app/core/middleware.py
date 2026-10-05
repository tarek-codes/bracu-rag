import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = structlog.get_logger("api.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                exc_info=True,
            )
            raise
        finally:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=latency_ms,
            )
