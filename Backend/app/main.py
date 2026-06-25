from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings, validate_required_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.redis import close_redis, get_redis_pool
from app.middleware.audit_middleware import AuditMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_required_settings(settings)
    configure_logging(debug=settings.APP_DEBUG, log_sql=settings.LOG_SQL)

    import structlog as _structlog

    _log = _structlog.get_logger("app.startup")

    # ── Verify Resend API key is live ─────────────────────────────────────────
    # We issue a GET /domains request (read-only, no email sent).  A 401 here
    # means every notification will fail silently at runtime — better to surface
    # it in the startup log immediately.  We do NOT abort on network failure
    # (Resend might be temporarily unreachable) but we DO abort on 401/403.
    try:
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=5.0) as _hc:
            _r = await _hc.get(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            )
        if _r.status_code == 401:
            raise SystemExit(
                "\n[Hadha.co] Resend API key is invalid (received 401 on startup probe).\n"
                "Fix RESEND_API_KEY in your .env — emails will not be sent.\n"
                "Generate a key at https://resend.com/api-keys\n"
            )
        if _r.status_code == 200:
            import json as _json

            _domains = _json.loads(_r.text).get("data", [])
            _verified = [d["name"] for d in _domains if d.get("status") == "verified"]
            _log.info("resend_connected", verified_domains=_verified)
        else:
            _log.warning("resend_probe_unexpected", status=_r.status_code)
    except SystemExit:
        raise
    except Exception as _exc:
        # Network unreachable etc. — warn but don't abort startup.
        _log.warning("resend_probe_failed", error=str(_exc))

    # Register domain event listeners
    from app.modules.notifications.service import (
        register_listeners as register_notification_listeners,
    )

    register_notification_listeners()

    # Start background job scheduler
    from app.workers.queue import build_queue

    queue = build_queue()
    queue.start()

    yield

    queue.shutdown()
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts_list,
        )

    # Middleware execution order (request in): CORS → Audit → Security → RequestID → RequestLogging → app
    # Starlette executes last-added first, so we add them in reverse execution order.
    app.add_middleware(
        RequestLoggingMiddleware
    )  # innermost: runs after RequestID has bound context
    app.add_middleware(
        RequestIDMiddleware
    )  # binds request_id, method, path to context vars
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    _mount_routers(app)

    return app


def _mount_routers(app: FastAPI) -> None:
    prefix = settings.API_V1_PREFIX

    from app.modules.addresses.router import router as addresses_router
    from app.modules.admin.router import router as admin_router
    from app.modules.analytics.router import router as analytics_router
    from app.modules.auth.router import router as auth_router
    from app.modules.cart.router import router as cart_router
    from app.modules.catalog.router import router as catalog_router
    from app.modules.categories.router import router as categories_router
    from app.modules.cms.router import router as cms_router
    from app.modules.collections.router import router as collections_router
    from app.modules.coupons.router import router as coupons_router
    from app.modules.dev_auth.router import router as dev_auth_router
    from app.modules.fraud.router import router as fraud_router
    from app.modules.fulfillment.router import router as fulfillment_router
    from app.modules.inventory.router import router as inventory_router
    from app.modules.invoices.router import router as invoices_router
    from app.modules.media.router import router as media_router
    from app.modules.notifications.router import router as notifications_router
    from app.modules.orders.router import router as orders_router
    from app.modules.payments.router import router as payments_router
    from app.modules.profiles.router import router as profiles_router
    from app.modules.returns.router import router as returns_router
    from app.modules.reviews.router import router as reviews_router
    from app.modules.search.router import router as search_router
    from app.modules.seo.router import router as seo_router
    from app.modules.settings.router import router as settings_router
    from app.modules.shipping.router import router as shipping_router
    from app.modules.support.router import router as support_router
    from app.modules.webhooks.router import router as webhooks_router
    from app.modules.wishlist.router import router as wishlist_router

    app.include_router(dev_auth_router, prefix=prefix, tags=["dev-auth"])
    app.include_router(auth_router, prefix=prefix, tags=["auth"])
    app.include_router(profiles_router, prefix=prefix, tags=["profiles"])
    app.include_router(categories_router, prefix=prefix, tags=["categories"])
    app.include_router(collections_router, prefix=prefix, tags=["collections"])
    app.include_router(catalog_router, prefix=prefix, tags=["catalog"])
    app.include_router(media_router, prefix=prefix, tags=["media"])
    app.include_router(search_router, prefix=prefix, tags=["search"])
    app.include_router(seo_router, prefix=prefix, tags=["seo"])
    app.include_router(inventory_router, prefix=prefix, tags=["inventory"])
    app.include_router(addresses_router, prefix=prefix, tags=["addresses"])
    app.include_router(wishlist_router, prefix=prefix, tags=["wishlist"])
    app.include_router(cart_router, prefix=prefix, tags=["cart"])
    app.include_router(coupons_router, prefix=prefix, tags=["coupons"])
    app.include_router(orders_router, prefix=prefix, tags=["orders"])
    app.include_router(fulfillment_router, prefix=prefix, tags=["fulfillment"])
    app.include_router(payments_router, prefix=prefix, tags=["payments"])
    app.include_router(invoices_router, prefix=prefix, tags=["invoices"])
    app.include_router(webhooks_router, prefix=prefix, tags=["webhooks"])
    app.include_router(shipping_router, prefix=prefix, tags=["shipping"])
    app.include_router(reviews_router, prefix=prefix, tags=["reviews"])
    app.include_router(cms_router, prefix=prefix, tags=["cms"])
    app.include_router(analytics_router, prefix=prefix, tags=["analytics"])
    app.include_router(returns_router, prefix=prefix, tags=["returns"])
    app.include_router(support_router, prefix=prefix, tags=["support"])
    app.include_router(notifications_router, prefix=prefix, tags=["notifications"])
    app.include_router(fraud_router, prefix=prefix, tags=["fraud"])
    app.include_router(settings_router, prefix=prefix, tags=["settings"])
    app.include_router(admin_router, prefix=prefix, tags=["admin"])

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/health/ready", tags=["ops"], include_in_schema=False)
    async def readiness():
        import json

        from fastapi import Response
        from sqlalchemy import text

        from app.core.database import AsyncSessionLocal, get_pool_status

        checks: dict = {}
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:
            checks["db"] = str(exc)

        try:
            redis = get_redis_pool()
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = str(exc)

        healthy = all(v == "ok" for v in checks.values())
        status_code = 200 if healthy else 503
        return Response(
            content=json.dumps(
                {
                    "status": "ready" if healthy else "degraded",
                    "checks": checks,
                    "pool": get_pool_status(),
                }
            ),
            status_code=status_code,
            media_type="application/json",
        )

    @app.get("/health/live", tags=["ops"], include_in_schema=False)
    async def liveness() -> dict:
        return {"status": "alive"}

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"name": settings.APP_NAME, "version": settings.APP_VERSION}


app = create_app()
