"""
Request logging middleware.

Replaces uvicorn's access log with a single structured log entry per request:

    request_complete  method=GET  path=/api/v1/products  status=200  duration_ms=82  ip=1.2.3.4

The entry is emitted AFTER the response is returned so it always carries the
final HTTP status code and the full wall-clock duration.

Fields automatically present on every line (injected by upstream middleware):
  - request_id   (RequestIDMiddleware)
  - user_id      (get_current_user dependency, if the endpoint is authenticated)
  - user_email   (get_current_user dependency, if the endpoint is authenticated)
  - ip           (bound here)

Slow requests (>= SLOW_MS) emit an additional WARNING with a "slow_request" event
so they're easy to grep for without filtering by duration.

Health-check paths are intentionally skipped — they fire every few seconds from
load balancers and would dominate the log stream.
"""

from __future__ import annotations

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

log = structlog.get_logger(__name__)

# Paths that should never appear in the access log.
_SKIP_PATHS = frozenset(
    {
        "/health",
        "/health/ready",
        "/health/live",
        "/",
        "/favicon.ico",
    }
)

# Requests that take longer than this get an extra WARNING line.
_SLOW_MS = 500


def _client_ip(request: Request) -> str:
    # Prefer X-Real-IP (set by Nginx via $remote_addr — not spoofable).
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    # Fall back to X-Forwarded-For — take the rightmost entry (closest to
    # the internet), which is the true client IP set by Nginx.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return getattr(request.client, "host", "unknown")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured per-request access log.

    Runs INSIDE RequestIDMiddleware so the request_id is already bound to
    contextvars when this middleware fires.  Auth dependencies run inside
    call_next, so user_id / user_email land in contextvars before the log
    line is emitted.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        from app.core.profiling import profiler

        profiler.begin_request()

        ip = _client_ip(request)
        # Bind IP early so every log line inside the handler also carries it.
        structlog.contextvars.bind_contextvars(ip=ip)

        t0 = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)

        # Normalise path: strip query string and collapse path-parameter
        # segments so that /products/42 and /products/7 track as one bucket.
        _normalised = request.url.path
        profiler.end_request(path=_normalised, duration_ms=duration_ms)

        status = response.status_code
        fields: dict = {
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": duration_ms,
            "ip": ip,
        }

        # Slow-request warning fires regardless of status code so it's searchable
        # independently of the main access log entry.
        if duration_ms >= _SLOW_MS:
            log.warning("slow_request", **fields)

        if status >= 500:
            log.error("request_failed", **fields)
        elif status >= 400:
            log.warning("request_error", **fields)
        else:
            log.info("request_complete", **fields)

        return response
