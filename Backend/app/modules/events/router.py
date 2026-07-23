"""
SSE (Server-Sent Events) endpoint for real-time frontend synchronization.

Frontend clients connect to GET /api/v1/events/stream and receive a stream
of domain events as they happen across the system.

Events are published to Redis pub/sub by:
  - API mutation handlers (inventory changes, order creation, etc.)
  - Background workers (reservation expiry, CMS publish, etc.)

The SSE stream keeps the frontend SyncBus in sync with backend state
without polling.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.pubsub import subscribe_sse, unsubscribe_sse

log = structlog.get_logger(__name__)

router = APIRouter()

# ── SSE keepalive interval ─────────────────────────────────────────────────────

KEEPALIVE_INTERVAL = 15  # seconds — prevents proxy/load-balancer timeouts


async def _event_generator(request: Request):
    """Yield SSE-formatted events from the Redis pub/sub subscription."""
    queue = await subscribe_sse()
    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for an event with a timeout for keepalive
                data = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL)
            except TimeoutError:
                # Send keepalive comment to keep the connection alive
                yield ": keepalive\n\n"
                continue

            # None signals shutdown
            if data is None:
                break

            # Format as SSE
            yield f"event: sync\ndata: {data}\n\n"

    except asyncio.CancelledError:
        pass
    finally:
        await unsubscribe_sse(queue)
        log.info("sse_client_disconnected")


@router.get("/events/stream")
async def sse_stream(request: Request):
    """
    SSE endpoint for real-time synchronization.

    Clients connect here and receive a stream of domain events:
      - inventory_changed
      - order_created
      - reservation_created
      - reservation_expired
      - product_updated
      - price_changed
      - collection_updated
      - cms_published

    Events are JSON-encoded: {"event": "<type>", "payload": {...}}
    """
    log.info(
        "sse_client_connected",
        client=request.client.host if request.client else "unknown",
    )

    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Access-Control-Allow-Origin": "*",
        },
    )
