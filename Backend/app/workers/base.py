from __future__ import annotations

import time

import structlog

from app.core.database import AsyncSessionLocal

log = structlog.get_logger(__name__)


async def run_with_session(fn):
    """Run a worker function inside a managed DB session with timing and error logging."""
    t0 = time.perf_counter()
    async with AsyncSessionLocal() as db:
        try:
            await fn(db)
            await db.commit()
        except Exception:
            duration_ms = round((time.perf_counter() - t0) * 1000)
            log.exception("worker_failed", worker=fn.__name__, duration_ms=duration_ms)
            await db.rollback()
