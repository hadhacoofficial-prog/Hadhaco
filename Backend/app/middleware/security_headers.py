from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every response.

    CSP for the API is intentionally permissive — the real CSP lives on the
    Nginx reverse proxy in front of the storefront / admin SPAs.
    This middleware provides defence-in-depth for direct-to-API traffic.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # ── HSTS ──────────────────────────────────────────────────────────────
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        # ── Clickjacking ─────────────────────────────────────────────────────
        response.headers["X-Frame-Options"] = "DENY"

        # ── MIME sniffing ─────────────────────────────────────────────────────
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ── Referrer ──────────────────────────────────────────────────────────
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ── Feature policy ────────────────────────────────────────────────────
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=(), web-share=()"
        )

        # ── Cross-Origin Isolation ────────────────────────────────────────────
        # COOP/CORP are intentionally omitted.  They are incompatible with
        # Razorpay's popup-based checkout flow, which opens cross-origin
        # iframes (api.razorpay.com) and popup windows (checkout.razorpay.com).
        #
        # Razorpay popup compatibility:
        #   - COOP: "same-origin" causes the popup to be unopener, breaking
        #     the post-payment redirect callback to the merchant site.
        #   - CORP: "same-origin" blocks cross-origin resource loading inside
        #     Razorpay iframes that embed merchant-hosted assets.
        #
        # When these can be safely re-enabled:
        #   - Razorpay migrates to a same-origin or redirect-based checkout
        #     (no popup/iframes).  Monitor Razorpay changelog for this.
        #   - Alternatively, if Razorpay adopts CSP-compatible cross-origin
        #     policies (COEP + CORP with proper CORP headers on their side).
        #
        # Response to re-enable: uncomment the two headers below AND add
        # COEP: "require-corp" with appropriate embedder policies.

        # ── Content Security Policy ───────────────────────────────────────────
        # The API itself returns JSON, so a restrictive CSP is fine.  The real
        # CSP for the SPA lives in Nginx — this is defence-in-depth.
        #
        # Policy rationale:
        #   default-src 'self'  — only allow same-origin by default
        #   base-uri 'self'     — prevent <base href> injection (injection vector)
        #   form-action 'self'  — prevent form hijacking to external URLs
        #   frame-ancestors 'none' — prevent clickjacking (replaces X-Frame-Options)
        csp_directives = [
            "default-src 'self'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        if settings.is_development:
            # Allow Swagger UI CDN assets in development only
            csp_directives.append(
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
            )
            csp_directives.append(
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
            )
            csp_directives.append("img-src 'self' data: https://fastapi.tiangolo.com")
            csp_directives.append("connect-src 'self' https://cdn.jsdelivr.net")
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # ── Remove server identity ────────────────────────────────────────────
        for _hdr in ("Server", "X-Powered-By"):
            if _hdr in response.headers:
                del response.headers[_hdr]

        return response
