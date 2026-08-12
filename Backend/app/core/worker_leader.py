"""Redis leader election for single-runner background work.

``uvicorn --workers N`` starts N processes and every one of them runs the
FastAPI lifespan. Tasks such as the APScheduler queue (reservation expiry,
media generation, notification retry, ...) and the notification-rules seed
must run exactly once per cluster — if they run in every worker the sweeps
hammer a remote DB N times as often and jobs built on a plain SELECT
(``notification_retry``) can double-fire (duplicate emails/WhatsApp).

Design:

* A Redis ``SET NX`` lock elects a single leader; only it starts those
  tasks. The lock value is a per-process random token.
* The leader heartbeat-refreshes its own lock via a Lua compare-and-set, so
  a stale leader can never extend a lock another process has since acquired.
* Followers poll for leadership (``start_reacquire_loop``): if the leader
  crashes, uvicorn respawns the worker within the lock TTL, the replacement
  wins the next poll, and the queue starts without a full cluster restart.
* Degradation is fail-open at startup: if Redis is unavailable (or the
  acquire call fails) the process assumes leadership rather than stalling
  startup — identical to the cache warmer's ``warm_skip_all`` fallback, so
  a Redis outage never disables the queue.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from typing import Any, cast

import structlog

from app.core.redis import get_redis_pool, redis_available

log = structlog.get_logger(__name__)


async def _eval_script(script: str, *args: str) -> None:
    """Run a compare-and-set Lua script against the leader lock.

    The redis.asyncio stubs type ``eval`` as returning
    ``Awaitable[str] | str`` and demand str args, so it is called through
    ``cast(Any, ...)`` — the runtime call is unchanged; only the typing is
    normalized. The return value is deliberately discarded.
    """
    await cast(Any, get_redis_pool().eval)(script, 1, *args)


_LEADER_LOCK_KEY = "hadha:workers:leader"
# Short TTL + frequent refresh: a crashed leader's lock must expire quickly
# so a replacement worker can take over (reservation expiry frees stock and
# media generation recovers pending images, both on short cadences).
_LEADER_TTL_SECONDS = 30
_REFRESH_INTERVAL_SECONDS = 10
# Followers poll for leadership on this cadence. It must be comfortably
# shorter than _LEADER_TTL_SECONDS so a crashed leader is replaced within
# ~2 poll cycles, while staying long enough to be cheap.
_REACQUIRE_INTERVAL_SECONDS = 15

# Lua compare-and-set scripts — refresh and release only apply when the key
# still holds this process's token. A leader whose lock expired and was
# re-acquired by another worker can no longer touch it.
_REFRESH_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class WorkerLeader:
    """Cluster-wide single-leader election for startup background tasks."""

    def __init__(self) -> None:
        self._lock_key = _LEADER_LOCK_KEY
        self._ttl = _LEADER_TTL_SECONDS
        self._refresh_interval = _REFRESH_INTERVAL_SECONDS
        self._reacquire_interval = _REACQUIRE_INTERVAL_SECONDS
        self._token = secrets.token_hex(16)
        self._refresh_task: asyncio.Task[Any] | None = None
        self._reacquire_task: asyncio.Task[Any] | None = None
        self._on_elected: Callable[[], None] | None = None
        self._held = False

    async def try_acquire(self) -> bool:
        """Become leader if nobody holds the lock.

        Returns True when this process should run single-runner background
        work. Falls back to True (run the work) when Redis is unavailable or
        the acquire call errors, so startup never stalls.
        """
        if not redis_available():
            log.warning("worker_leader_fallback", reason="redis_unavailable")
            return True
        try:
            acquired = await asyncio.wait_for(
                get_redis_pool().set(
                    self._lock_key, self._token, nx=True, ex=self._ttl
                ),
                timeout=0.5,
            )
        except Exception as exc:
            log.warning("worker_leader_error", error=str(exc))
            return True  # best-effort — run the work rather than stall startup
        if not acquired:
            log.info("worker_leader_skip", reason="another_worker_is_leader")
            return False
        self._held = True
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        log.info("worker_leader_acquired")
        return True

    def start_reacquire_loop(self, on_elected: Callable[[], None]) -> None:
        """Poll for leadership so a crashed leader is replaced.

        Called only by followers (the initial acquire failed). Every
        _REACQUIRE_INTERVAL_SECONDS, retry acquiring; the first process to
        win calls *on_elected* (which starts the queue) and stops polling.
        """
        self._on_elected = on_elected
        if self._held or self._reacquire_task is not None:
            return
        self._reacquire_task = asyncio.create_task(self._reacquire_loop())

    async def _reacquire_loop(self) -> None:
        while True:
            await asyncio.sleep(self._reacquire_interval)
            if self._held:
                return
            if not redis_available():
                continue
            try:
                acquired = await asyncio.wait_for(
                    get_redis_pool().set(
                        self._lock_key, self._token, nx=True, ex=self._ttl
                    ),
                    timeout=0.5,
                )
            except Exception as exc:
                log.warning("worker_leader_reacquire_error", error=str(exc))
                continue
            if acquired:
                self._held = True
                self._refresh_task = asyncio.create_task(self._refresh_loop())
                if self._on_elected is not None:
                    self._on_elected()
                log.info("worker_leader_elected_after_crash")
                return

    async def _refresh_loop(self) -> None:
        """Keep the lock alive for the lifetime of the leader process."""
        while True:
            await asyncio.sleep(self._refresh_interval)
            try:
                await _eval_script(
                    _REFRESH_SCRIPT,
                    self._lock_key,
                    self._token,
                    str(self._ttl),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("worker_leader_refresh_error", error=str(exc))

    async def release(self) -> None:
        """Cancel background loops and release the lock if we own it."""
        for task in (self._refresh_task, self._reacquire_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._refresh_task = None
        self._reacquire_task = None
        if self._held:
            try:
                await _eval_script(_RELEASE_SCRIPT, self._lock_key, self._token)
            except Exception as exc:
                log.warning("worker_leader_release_error", error=str(exc))
            self._held = False
            log.info("worker_leader_released")
