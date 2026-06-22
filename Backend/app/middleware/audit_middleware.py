"""
Automatic audit logging middleware for admin routes.

Logs every mutating request (POST/PATCH/PUT/DELETE) on /admin/* paths
to structured logs. The audit_logs table write happens in the audit
service module — this middleware only captures the context.
"""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


log = structlog.get_logger(__name__)

_MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
_ADMIN_PREFIX = "/api/v1/admin"


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Intercepts admin mutating requests, logs them after completion.
    Does NOT block the request — pure observation.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            request.method not in _MUTATING_METHODS
            or not request.url.path.startswith(_ADMIN_PREFIX)
        ):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        log.info(
            "admin_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            ip=request.headers.get("X-Forwarded-For", getattr(request.client, "host", "unknown")),
            user_agent=request.headers.get("User-Agent", ""),
        )

        return response
