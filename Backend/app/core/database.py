import asyncio
import re
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

from app.core.config import settings

_pool_log = structlog.get_logger("db.pool")

# ── Single shared engine (all components) ─────────────────────────────────────
# One engine serves API requests, background workers, event listeners, cache
# warming, and health checks.  With pool_size=2 and max_overflow=1 the engine
# holds at most 3 persistent TCP connections per uvicorn worker process.
#
# Budget (2 workers): (2 + 1) × 2 = 6 persistent connections.
# Remaining: 15 − 6 = 9 headroom for Alembic, transient spikes, and
# occasional direct connections (psql, admin tools).
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

# Backwards-compatible alias — workers and event listeners that previously
# used the NullPool worker engine now share the single pool above.
AsyncWorkerSessionLocal = AsyncSessionLocal

# ── Pool monitoring ───────────────────────────────────────────────────────────
# Log a warning whenever the pool is one slot from exhaustion so that
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
# P0-2: the per-return `DISCARD ALL` was removed. It cost one round-trip plus
# asyncpg prepared-statement re-prepare on EVERY connection return, and the
# audit found no session-scoped state in the app that could leak: no `SET` /
# `SET LOCAL` GUCs, no `LISTEN`/`NOTIFY`, no temp tables. Transaction state is
# already cleaned by the session lifecycle (COMMIT on success, ROLLBACK on
# error in `get_db`) plus SQLAlchemy's own reset_on_return rollback, so a
# connection is always returned idle. asyncpg's per-connection prepared
# statement cache now survives across requests — that is the point of P0-2.


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""


# ── Worker concurrency limiter ────────────────────────────────────────────────
# Bounded concurrency for background tasks that open database sessions.
# Prevents bursts of asyncio.create_task() (e.g. media generation fast-path)
# from exhausting the pool.  Allows up to 2 concurrent worker sessions across
# the entire process — enough for parallelism without starving the API pool.
_worker_semaphore: asyncio.Semaphore | None = None


def get_worker_semaphore() -> asyncio.Semaphore:
    """Return (and lazily create) the shared worker concurrency semaphore."""
    global _worker_semaphore
    if _worker_semaphore is None:
        _worker_semaphore = asyncio.Semaphore(2)
    return _worker_semaphore


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request.

    Session lifecycle is managed manually (not via ``async with``) so that
    a corrupted session state cannot prevent cleanup.  The ``finally`` block
    always calls ``session.close()`` wrapped in a safety catch — if the
    session's internal state machine is broken (e.g. ``IllegalStateChangeError``
    from a concurrent ``_connection_for_bind``), the error is swallowed and
    the connection is invalidated rather than leaking back into the pool.

    ``COMMIT`` is only issued when the request actually wrote something
    (P1-1): ORM-tracked changes (``Session.new``/``dirty``/``deleted``) OR any
    raw Core DML (``INSERT``/``UPDATE``/``DELETE``/``MERGE``) detected by the
    ``after_cursor_execute`` listener. Read-only requests skip the COMMIT —
    ``session.close()`` then rolls back the (empty) transaction, which is
    semantically identical and avoids the write-path cost on the storefront.
    """
    _checkout_start_tls._checkout_start = _time.monotonic()  # type: ignore[attr-defined]
    _t_session = _time.perf_counter()
    session = AsyncSessionLocal()
    checkout_ms = (_time.perf_counter() - _t_session) * 1000
    try:
        yield session
        if _session_has_writes(session):
            _t_commit = _time.perf_counter()
            await session.commit()
            commit_ms = (_time.perf_counter() - _t_commit) * 1000
            from app.core.profiling import profiler

            profiler.record_db_commit(commit_ms)
            if checkout_ms > 10 or commit_ms > 10:
                from app.core.profiling import profiler as _p

                _p.record_db_session_lifecycle(checkout_ms, commit_ms)
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


def _session_has_writes(session: AsyncSession) -> bool:
    """Return True if the session executed any write this request.

    Checks ORM-tracked changes first (cheap, pure client state), then falls
    back to the ``hadha_write`` flag the cursor listener sets on the session's
    connection when any INSERT/UPDATE/DELETE/MERGE ran. The connection is only
    consulted if the session actually opened one (i.e. executed a query), so
    a request that never touched the DB stays a pure no-op.
    """
    sync = session.sync_session
    if sync.new or sync.dirty or sync.deleted:
        return True
    txn = sync.get_transaction()
    conn = getattr(txn, "connection", None) if txn is not None else None
    return bool(conn is not None and conn.info.get("hadha_write"))


# ── SQL query profiling ───────────────────────────────────────────────────────

# Matches statements that write to the database — DML (INSERT/UPDATE/DELETE/
# MERGE), DDL, and utility/PLpgSQL (DO/CALL/COPY/...). Used to decide whether a
# request's session needs a COMMIT (P1-1) without tracking every ORM object —
# Core executes of `text("UPDATE ...")` etc. are invisible to
# Session.dirty/new/deleted, so the flag is the only reliable signal for them.
# Searches the whole statement (not just the leading verb) so `WITH ... INSERT`
# and `DO $$ ... CREATE ...` are caught; rare false positives only cost a
# redundant COMMIT of an already-read-only transaction (a no-op), while a
# missed write would silently roll back real data.
_WRITE_STATEMENT_RE = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|"
    r"REVOKE|DO|CALL|COPY|VACUUM|REINDEX|CLUSTER|LOCK)\b",
    re.IGNORECASE,
)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_query(conn, cursor, statement, parameters, context, executemany):  # type: ignore[misc]
    conn.info.setdefault("query_start_time", []).append(_time.perf_counter())


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_query(conn, cursor, statement, parameters, context, executemany):  # type: ignore[misc]
    statement = str(statement)
    if _WRITE_STATEMENT_RE.search(statement):
        conn.info["hadha_write"] = True
    start_times = conn.info.get("query_start_time", [])
    if start_times:
        elapsed_ms = (_time.perf_counter() - start_times.pop()) * 1000
        from app.core.profiling import profiler

        profiler.record_query(
            elapsed_ms,
            statement[:500],
            slow_threshold_ms=settings.PERF_SLOW_SQL_THRESHOLD_MS,
        )
