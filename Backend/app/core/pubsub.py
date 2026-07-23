"""
Redis Pub/Sub — cross-process event broadcasting for SSE.

When a mutation happens in one uvicorn worker, it publishes an event to
a Redis channel. All other workers (and the same worker) receive the event
and stream it to connected SSE clients.

This is the missing link for cross-user real-time synchronization:
  Backend mutation → event_bus → Redis pub/sub → SSE endpoint → EventSource → SyncBus → UI
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.core.redis import get_redis_pool, mark_redis_error, redis_available

log = structlog.get_logger(__name__)

# ── Channel name ───────────────────────────────────────────────────────────────

PUBSUB_CHANNEL = "hadha:sync:events"

# ── Subscriber management ─────────────────────────────────────────────────────

# Each SSE connection gets its own asyncio.Queue. When an event arrives on the
# Redis channel, it is pushed to every connected queue.

_subscribers: list[asyncio.Queue[str | None]] = []
_subscriber_lock = asyncio.Lock()
_redis_task: asyncio.Task[None] | None = None


async def _listen_redis() -> None:
    """Background task that subscribes to Redis and distributes events."""
    global _redis_task

    while True:
        try:
            pool = get_redis_pool()
            pubsub = pool.pubsub()
            await pubsub.subscribe(PUBSUB_CHANNEL)

            async for message in pubsub.listen():
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue

                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                if not data:
                    continue

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
            break
        except Exception as exc:
            log.error("redis_pubsub_listener_error", error=str(exc))
            mark_redis_error()
            await asyncio.sleep(5)  # Back off before reconnecting


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
