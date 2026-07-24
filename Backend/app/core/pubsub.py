"""
Redis Pub/Sub — cross-process event broadcasting for SSE.

When a mutation happens in one uvicorn worker, it publishes an event to
a Redis channel. All other workers (and the same worker) receive the event
and stream it to connected SSE clients.

This is the missing link for cross-user real-time synchronization:
  Backend mutation → event_bus → Redis pub/sub → SSE endpoint → EventSource → SyncBus → UI

Resilience note: the listener uses a bounded ``get_message(timeout=...)`` read
loop with an active ping-based health check, NOT ``PubSub.listen()`` — the
latter blocks on an unbounded socket read with no way to detect a silently
half-open connection (verified against the installed redis-py: ``.listen()``
calls ``parse_response(block=True)`` with no timeout, so a dropped connection
that doesn't deliver a prompt FIN/RST leaves it hanging forever with no
exception ever raised to trigger reconnect). ``_subscribers`` (the SSE client
queues) is independent of the Redis connection lifecycle, so existing SSE
HTTP connections are never disrupted by a Redis-side reconnect.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog

from app.core.redis import (
    get_redis_pool,
    mark_redis_error,
    mark_redis_ok,
    redis_available,
)

log = structlog.get_logger(__name__)

# ── Channel name ───────────────────────────────────────────────────────────────

PUBSUB_CHANNEL = "hadha:sync:events"

# ── Subscriber management ─────────────────────────────────────────────────────

# Each SSE connection gets its own asyncio.Queue. When an event arrives on the
# Redis channel, it is pushed to every connected queue.

_subscribers: list[asyncio.Queue[str | None]] = []
_subscriber_lock = asyncio.Lock()
_redis_task: asyncio.Task[None] | None = None

# ── Listener health state ─────────────────────────────────────────────────────
# Read by get_pubsub_health() (surfaced at /health/metrics) and the Prometheus
# gauges/counter below. Written only by _listen_redis().

_pubsub_connected: bool = False
_pubsub_last_message_at: float | None = None  # time.monotonic() of last message/ping
_pubsub_reconnect_count: int = 0

# How long to wait for a message before proactively pinging to check the
# connection is still alive. Kept well under typical idle/NAT timeouts.
_GET_MESSAGE_TIMEOUT = 15.0
# Bound on the health-check ping itself — must be short since a dead
# connection should be detected quickly, not add its own long hang.
_PING_TIMEOUT = 5.0
_RECONNECT_BACKOFF_INITIAL = 1.0
_RECONNECT_BACKOFF_MAX = 30.0

# ── Prometheus metrics (optional import, same pattern as inventory/metrics.py) ─

try:
    from prometheus_client import Counter, Gauge

    # Explicit `Any` annotations: reassigned to _NoOpMetric instances below
    # when prometheus_client isn't installed — see inventory/metrics.py for
    # the same dual-mode pattern.
    sse_pubsub_connected: Any = Gauge(
        "sse_pubsub_connected",
        "Whether the SSE Redis pub/sub listener currently has a live connection (1) or not (0)",
    )
    sse_pubsub_reconnects_total: Any = Counter(
        "sse_pubsub_reconnects_total",
        "Number of times the SSE Redis pub/sub listener has had to reconnect",
    )
    sse_pubsub_last_message_timestamp: Any = Gauge(
        "sse_pubsub_last_message_timestamp",
        "Unix timestamp of the last message (or successful health-check ping) the SSE pub/sub listener observed",
    )
except ImportError:  # pragma: no cover - prometheus_client not installed

    class _NoOpMetric:
        def inc(self, *args: Any, **kwargs: Any) -> None:
            pass

        def set(self, *args: Any, **kwargs: Any) -> None:
            pass

    sse_pubsub_connected = _NoOpMetric()
    sse_pubsub_reconnects_total = _NoOpMetric()
    sse_pubsub_last_message_timestamp = _NoOpMetric()


def _mark_connected(connected: bool) -> None:
    global _pubsub_connected
    _pubsub_connected = connected
    sse_pubsub_connected.set(1 if connected else 0)


def _mark_activity() -> None:
    """Record that the connection is confirmed alive right now (a message
    arrived, or a health-check ping succeeded)."""
    global _pubsub_last_message_at
    _pubsub_last_message_at = time.monotonic()
    sse_pubsub_last_message_timestamp.set(time.time())


def get_pubsub_health() -> dict[str, Any]:
    """Listener health snapshot for /health/metrics and manual inspection."""
    return {
        "connected": _pubsub_connected,
        "reconnect_count": _pubsub_reconnect_count,
        "seconds_since_last_activity": (
            round(time.monotonic() - _pubsub_last_message_at, 1)
            if _pubsub_last_message_at is not None
            else None
        ),
        "subscriber_count": len(_subscribers),
    }


async def _listen_redis() -> None:
    """Background task that subscribes to Redis and distributes events.

    Runs a bounded get_message() loop (never an unbounded blocking read) so
    a silently-dead connection is detected via an active ping within
    _GET_MESSAGE_TIMEOUT + _PING_TIMEOUT seconds at most, instead of hanging
    forever. Reconnects with exponential backoff; existing SSE client queues
    in _subscribers are untouched across reconnects.
    """
    global _redis_task, _pubsub_reconnect_count

    backoff = _RECONNECT_BACKOFF_INITIAL

    while True:
        pubsub = None
        try:
            pool = get_redis_pool()
            pubsub = pool.pubsub()
            await pubsub.subscribe(PUBSUB_CHANNEL)
            _mark_connected(True)
            _mark_activity()
            mark_redis_ok()
            backoff = _RECONNECT_BACKOFF_INITIAL  # reset after a successful (re)connect
            log.info("redis_pubsub_connected", channel=PUBSUB_CHANNEL)

            while True:
                message = await pubsub.get_message(timeout=_GET_MESSAGE_TIMEOUT)

                if message is None:
                    # No message within the window — actively verify the
                    # connection is still alive rather than waiting
                    # indefinitely to find out. Raises on a dead socket.
                    await asyncio.wait_for(pubsub.ping(), timeout=_PING_TIMEOUT)
                    _mark_activity()
                    continue

                if message.get("type") != "message":
                    continue

                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                if not data:
                    continue

                _mark_activity()

                # Fan out to all connected SSE queues
                async with _subscriber_lock:
                    dead: list[asyncio.Queue[str | None]] = []
                    for q in _subscribers:
                        try:
                            q.put_nowait(data)
                        except asyncio.QueueFull:
                            dead.append(q)
                    for d in dead:
                        _subscribers.remove(d)

        except asyncio.CancelledError:
            _mark_connected(False)
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
            break
        except Exception as exc:
            _mark_connected(False)
            _pubsub_reconnect_count += 1
            sse_pubsub_reconnects_total.inc()
            log.error(
                "redis_pubsub_listener_error",
                error=str(exc),
                reconnect_count=_pubsub_reconnect_count,
                next_retry_in_s=backoff,
            )
            mark_redis_error()
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _RECONNECT_BACKOFF_MAX)


def start_pubsub_listener() -> None:
    """Start the Redis pub/sub listener background task."""
    global _redis_task
    if _redis_task is not None:
        return
    _redis_task = asyncio.create_task(_listen_redis())
    log.info("redis_pubsub_started", channel=PUBSUB_CHANNEL)


def stop_pubsub_listener() -> None:
    """Stop the Redis pub/sub listener."""
    global _redis_task
    if _redis_task is not None:
        _redis_task.cancel()
        _redis_task = None


# ── Publishing ─────────────────────────────────────────────────────────────────


async def publish_sync_event(
    event_type: str, payload: dict[str, Any] | None = None
) -> None:
    """
    Publish a synchronization event to Redis pub/sub.

    Called by mutation handlers and background workers after a state change.
    The event is received by all connected SSE clients and forwarded to the
    frontend SyncBus.
    """
    if not redis_available():
        return

    data = json.dumps({"event": event_type, "payload": payload or {}}, default=str)
    try:
        pool = get_redis_pool()
        await pool.publish(PUBSUB_CHANNEL, data)
    except Exception as exc:
        log.error("redis_publish_error", event_type=event_type, error=str(exc))
        mark_redis_error()


# ── SSE subscription ───────────────────────────────────────────────────────────


async def subscribe_sse() -> asyncio.Queue[str | None]:
    """
    Create a new SSE subscription queue.

    Returns a queue that will receive JSON-encoded events from Redis pub/sub.
    The caller should read from this queue in a loop and write to the SSE response.
    """
    q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)
    async with _subscriber_lock:
        _subscribers.append(q)

    # Ensure the Redis listener is running
    start_pubsub_listener()

    return q


async def unsubscribe_sse(q: asyncio.Queue[str | None]) -> None:
    """Remove an SSE subscription queue."""
    async with _subscriber_lock:
        if q in _subscribers:
            _subscribers.remove(q)
    # Put None to signal the SSE generator to stop
    try:
        q.put_nowait(None)
    except asyncio.QueueFull:
        pass
