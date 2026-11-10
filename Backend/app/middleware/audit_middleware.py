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

from app.middleware.rate_limit import get_client_ip

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

        claimed_user_id = _extract_user_id(request)
        # The JWT is decoded WITHOUT signature verification here, so the `sub`
        # is only a claim. It is trustworthy as an actor identity only when the
        # request was actually authenticated and accepted (status < 400, and
        # the route's own dependencies verified the same token). Otherwise it is
        # recorded under a separate, clearly-untrusted key so a forged token
        # cannot frame another user in the audit trail.
        verified = response.status_code < 400
        user_id = claimed_user_id if verified else None
        unverified_claimed_user_id = None if verified else claimed_user_id

        # Same trust rules as rate limiting: forwarding headers are honoured only
        # from a trusted proxy peer; otherwise the socket peer address is used.
        client_ip = get_client_ip(request)

        log.info(
            "audit_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            ip=client_ip,
            user_id=user_id,
            unverified_claimed_user_id=unverified_claimed_user_id,
            user_agent=request.headers.get("User-Agent", ""),
        )

        return response
