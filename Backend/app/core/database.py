import threading
import time as _time
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
#
# pool_pre_ping is deliberately OFF.  Supabase's session-mode PgBouncer can
# leave connections in an intermediate transaction state after reassigning them.
# asyncpg's pool_pre_ping tries to start a new transaction (BEGIN) to verify
# liveness, which fails with "cannot use Connection.transaction() in a manually
# started transaction".  Without pre_ping, a stale connection simply fails on
# the first real query and gets discarded — which is both safer and faster
# (no extra round-trip per checkout).
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    # Recycle connections idle longer than 30 minutes so the Supabase session
    # pooler doesn't silently drop them on its side first.
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=False,
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


_checkout_start_tls = threading.local()


@event.listens_for(engine.sync_engine, "checkout")
def _on_pool_checkout(dbapi_conn, conn_rec, conn_proxy) -> None:  # type: ignore[misc]
    pool = engine.pool
    checked_out = pool.checkedout()  # type: ignore[attr-defined]

    # Measure actual wait time from when the session requested a connection.
    now = _time.monotonic()
    wait_ms = 0.0
    prev = getattr(_checkout_start_tls, "_checkout_start", None)
    if prev is not None:
        wait_ms = max(0.0, (now - prev) * 1000)

    if checked_out >= _POOL_CAPACITY - 1:
        _pool_log.warning(
            "pool_near_capacity",
            checked_out=checked_out,
            capacity=_POOL_CAPACITY,
            overflow=pool.overflow(),  # type: ignore[attr-defined]
        )
    # Record pool utilisation for profiling
    from app.core.profiling import profiler

    profiler.record_pool_checkout(wait_ms, checked_out, _POOL_CAPACITY)


def get_pool_status() -> dict[str, int]:
    """Return current pool utilisation — suitable for the /health/ready endpoint."""
    pool = engine.pool
    return {
        "size": pool.size(),  # type: ignore[attr-defined]
        "checked_out": pool.checkedout(),  # type: ignore[attr-defined]
        "overflow": pool.overflow(),  # type: ignore[attr-defined]
        "capacity": _POOL_CAPACITY,
    }


# ── Connection reset on return to pool ────────────────────────────────────────
# When a connection is returned to the pool, discard any leftover server-side
# state (prepared statements, temp tables, SET variables).  This prevents
# cross-request contamination through Supabase's session-mode PgBouncer, which
# may reassign the underlying TCP connection to a different client session.
@event.listens_for(engine.sync_engine, "reset")
def _on_connection_reset(dbapi_conn, connection_record) -> None:  # type: ignore[misc]
    """Issue DISCARD ALL when a connection is returned to the pool."""
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("DISCARD ALL")
        cursor.close()
    except Exception:
        # If DISCARD ALL fails (connection already dead), invalidate it
        # so the pool doesn't hand it to the next request.
        connection_record.invalidate()


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request.

    Session lifecycle is managed manually (not via ``async with``) so that
    a corrupted session state cannot prevent cleanup.  The ``finally`` block
    always calls ``session.close()`` wrapped in a safety catch — if the
    session's internal state machine is broken (e.g. ``IllegalStateChangeError``
    from a concurrent ``_connection_for_bind``), the error is swallowed and
    the connection is invalidated rather than leaking back into the pool.
    """
    _checkout_start_tls._checkout_start = _time.monotonic()  # type: ignore[attr-defined]
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            await session.close()
        except Exception:
            # Session close can fail when the session is in a corrupted state
            # (e.g. ``IllegalStateChangeError``).  Log and move on — the
            # connection will be garbage-collected by the pool.
            _pool_log.warning(
                "session_close_failed",
                exc_info=True,
            )


# ── SQL query profiling ───────────────────────────────────────────────────────


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_query(conn, cursor, statement, parameters, context, executemany):  # type: ignore[misc]
    conn.info.setdefault("query_start_time", []).append(_time.perf_counter())


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_query(conn, cursor, statement, parameters, context, executemany):  # type: ignore[misc]
    start_times = conn.info.get("query_start_time", [])
    if start_times:
        elapsed_ms = (_time.perf_counter() - start_times.pop()) * 1000
        from app.core.profiling import profiler

        profiler.record_query(elapsed_ms, str(statement)[:500])
