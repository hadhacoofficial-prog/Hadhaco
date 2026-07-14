"""
Automatic audit logging middleware for admin routes.

Logs every mutating request (POST/PATCH/PUT/DELETE) on /admin/* paths
to structured logs. The audit_logs table write happens in the audit
service module — this middleware only captures the context.
"""

import time

import jwt
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

log = structlog.get_logger(__name__)

_MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
_ADMIN_PREFIX = "/api/v1/admin"
_AUTH_PREFIX = "/api/v1/auth"
_DEV_AUTH_PREFIX = "/api/v1/dev"


def _extract_user_id(request: Request) -> str | None:
    """Best-effort extraction of the user ID from the Authorization header.

    Returns None when the token is missing, malformed, or cannot be decoded.
    This is deliberately lenient — the middleware is observational only and
    must never block a request.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        payload = jwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=["HS256", "ES256"],
        )
        return payload.get("sub")
    except (jwt.DecodeError, jwt.InvalidTokenError):
        return None


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Intercepts admin mutating requests, logs them after completion.
    Does NOT block the request — pure observation.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        is_mutating = request.method in _MUTATING_METHODS
        is_admin_path = request.url.path.startswith(_ADMIN_PREFIX)
        is_auth_path = request.url.path.startswith((_AUTH_PREFIX, _DEV_AUTH_PREFIX))

        if not is_mutating or not (is_admin_path or is_auth_path):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        user_id = _extract_user_id(request)
        # Prefer X-Real-IP (set by Nginx via $remote_addr — not spoofable).
        client_ip = request.headers.get("X-Real-IP", "").strip()
        if not client_ip:
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                parts = [p.strip() for p in forwarded.split(",") if p.strip()]
                client_ip = parts[-1] if parts else "unknown"
            else:
                client_ip = getattr(request.client, "host", "unknown")

        log.info(
            "audit_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            ip=client_ip,
            user_id=user_id,
            user_agent=request.headers.get("User-Agent", ""),
        )

        return response
