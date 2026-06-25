from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every response.
    CSP is intentionally permissive for the API — tighten on the frontend.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Strict Transport Security (only enforce in production)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=()"
        )
        if settings.is_production:
            csp = "default-src 'self'; frame-ancestors 'none';"
        else:
            # Allow Swagger UI CDN assets in development
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "connect-src 'self' https://cdn.jsdelivr.net; "
                "frame-ancestors 'none';"
            )
        response.headers["Content-Security-Policy"] = csp

        # Remove server identity
        for _hdr in ("Server", "X-Powered-By"):
            if _hdr in response.headers:
                del response.headers[_hdr]

        return response
