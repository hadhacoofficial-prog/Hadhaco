from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

_pool_log = structlog.get_logger("db.pool")

# ── Request-scoped engine (persistent pool) ───────────────────────────────────
# Each uvicorn worker process holds pool_size idle connections.
# pool_size × worker_count must stay well under the Supabase session-mode
# client cap (15 on the default Supabase plan).
# With 2 workers: (3 + 1) × 2 = 8 connections for the API, leaving 7 free for
# Alembic migrations, health checks, admin tools, and the worker engine below.
# Event listeners (notifications, shipping) use AsyncWorkerSessionLocal (NullPool)
# so they never draw from this budget.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    # Recycle connections idle longer than 30 minutes so the Supabase session
    # pooler doesn't silently drop them on its side first.
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    # Pre-ping catches dead connections before they reach a request handler.
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ── Worker engine (NullPool — no persistent connections) ──────────────────────
# Background workers and async event listeners use this engine so they never hold
# idle Supabase session-mode slots between invocations.
# NullPool creates a fresh TCP connection on each session open and disposes it
# immediately on close.  A worker that runs once per minute therefore occupies
# a session-mode slot for ~0.1–0.5 s rather than holding it indefinitely.
_worker_engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    pool_pre_ping=True,
    echo=False,
)

AsyncWorkerSessionLocal = async_sessionmaker(
    bind=_worker_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ── Pool monitoring ───────────────────────────────────────────────────────────
# Log a warning whenever the request pool is one slot from exhaustion so that
# operators can detect pressure before EMAXCONNSESSION errors appear in prod.
_POOL_CAPACITY = settings.DATABASE_POOL_SIZE + settings.DATABASE_MAX_OVERFLOW


@event.listens_for(engine.sync_engine, "checkout")
def _on_pool_checkout(dbapi_conn, conn_rec, conn_proxy) -> None:  # type: ignore[misc]
    pool = engine.pool
    checked_out = pool.checkedout()  # type: ignore[attr-defined]
    if checked_out >= _POOL_CAPACITY - 1:
        _pool_log.warning(
            "pool_near_capacity",
            checked_out=checked_out,
            capacity=_POOL_CAPACITY,
            overflow=pool.overflow(),  # type: ignore[attr-defined]
        )


def get_pool_status() -> dict[str, int]:
    """Return current pool utilisation — suitable for the /health/ready endpoint."""
    pool = engine.pool
    return {
        "size": pool.size(),  # type: ignore[attr-defined]
        "checked_out": pool.checkedout(),  # type: ignore[attr-defined]
        "overflow": pool.overflow(),  # type: ignore[attr-defined]
        "capacity": _POOL_CAPACITY,
    }


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request.

    The `async with AsyncSessionLocal()` context manager guarantees that
    session.close() is called on exit, returning the connection to the pool.
    The explicit commit/rollback inside the try/except controls the transaction;
    the finally clause is intentionally omitted — it would call close() twice.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
