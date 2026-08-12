"""Shared helpers for Celery task bodies.

Every task in this package is a thin sync entrypoint around the existing
async business logic in ``app/workers/*.py`` — that logic is untouched by
this migration (see Docs/CELERY_MIGRATION_PLAN.md §16). This module provides
the two things every task needs: a way to run an async function from
Celery's sync prefork worker, and uniform structured logging/timing so every
task reports task_id/task_name/queue/attempt/duration/outcome the same way
the old ``scheduler_job_duration_seconds`` metric did for every APScheduler
job, without each task module re-implementing it.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Coroutine
from contextlib import contextmanager
from typing import Any

import asyncpg
import redis.exceptions
import structlog

log = structlog.get_logger("celery.task")

# Infrastructure failures worth a Celery-level retry: DB/Redis unreachable or
# a connection dropped mid-call. Never includes business-logic exceptions —
# those are handled by each task's own DB-state-driven retry mechanism (plan
# §10); stacking Celery retries on top of that would create two disagreeing
# retry counters for the same failure.
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    asyncpg.exceptions.PostgresError,
    redis.exceptions.RedisError,
)


def is_transient(exc: Exception) -> bool:
    return isinstance(exc, TRANSIENT_ERRORS)


def backoff_seconds(attempt: int, *, base: float = 2.0, cap: float = 30.0) -> float:
    """Exponential backoff with full jitter, capped at *cap* seconds."""
    ceiling = min(cap, base * (2**attempt))
    return random.uniform(0, ceiling)


def run_async[T](coro_fn: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run an async function to completion from a sync Celery task body.

    Celery's prefork pool executes task functions synchronously; every task
    body here wraps its actual (async) work with this helper.

    Uses this process's single persistent event loop (app.celery_app.
    get_worker_loop), NOT asyncio.run() per call. asyncio.run() creates a new
    loop and destroys it when the coroutine returns — but app.core.database's
    engine (and its pooled asyncpg connections) is created once per process
    and reused across every task invocation in that process. asyncpg
    connections are bound to the event loop that opened them, so a second
    task's fresh asyncio.run() loop would try to reuse a connection still
    attached to the first task's already-destroyed loop. Confirmed against
    real worker logs this produced exactly:
        RuntimeError: Task ... got Future ... attached to a different loop
        asyncpg.exceptions.InterfaceError: cannot perform operation:
        another operation is in progress
    on the second+ tick of reservation_expiry/cms_publish/notification_retry
    in the same worker process. One loop per process, reused for the
    process's lifetime, is the fix — see app.celery_app's module docstring
    for the full explanation.
    """
    from app.celery_app import get_worker_loop

    return get_worker_loop().run_until_complete(coro_fn())


@contextmanager
def task_run_log(task: Any):
    """Structured start/duration/outcome logging for one task invocation.

    Logs task_id, task_name, queue (routing key), attempt (retries + 1),
    start, duration_ms, and outcome (success/failure, with exception on
    failure) — the fields item 20 of the migration brief requires for every
    Celery task, independent of what each task's own business logic logs.
    """
    request = task.request
    task_id = request.id
    task_name = task.name
    queue = getattr(request, "delivery_info", None) or {}
    routing_key = queue.get("routing_key") if isinstance(queue, dict) else None
    attempt = (request.retries or 0) + 1

    start = time.perf_counter()
    log.info(
        "task_started",
        task_id=task_id,
        task_name=task_name,
        queue=routing_key,
        attempt=attempt,
    )
    try:
        yield
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000)
        log.exception(
            "task_failed",
            task_id=task_id,
            task_name=task_name,
            queue=routing_key,
            attempt=attempt,
            duration_ms=duration_ms,
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - start) * 1000)
        log.info(
            "task_succeeded",
            task_id=task_id,
            task_name=task_name,
            queue=routing_key,
            attempt=attempt,
            duration_ms=duration_ms,
        )
