"""
Background variant-generation worker — the production path for every
image mutation (crop/upload/replace/regenerate). `universal_service.py`'s
`_enqueue_generation` persists the "pending" status + which breakpoints
need regenerating and returns immediately; this module does the actual
crop -> encode -> R2-upload work (via `background.generate_variants_for_breakpoints`,
Phase 1's parallel-upload pipeline — reused unchanged, not reimplemented)
off the request (docs audit CB-1 Phase 2).

Two things race to process a given image, and `ImageRepository.try_claim_pending`'s
atomic UPDATE ... WHERE status='pending' ... RETURNING is what makes that
race safe:

1. `app.tasks.media.generate_variants` is dispatched as a Celery task right
   when the image is queued (from `universal_service._enqueue_generation`)
   — the fast path, usually finishing in roughly one generation's worth of
   R2 time, just off the request. It calls `process_one()` below directly.
2. `run()` is the periodic Celery Beat task (`app.tasks.media.sweep_pending`,
   mirroring reservation_expiry.py's pattern): it first reclaims any image
   stuck in 'processing' longer than STALE_AFTER_SECONDS (a worker process
   died mid-run) back to 'pending', then processes whatever's pending. This
   is also the *only* path that runs generation in a multi-process
   deployment, since the worker process that dispatched the fast-path task
   isn't guaranteed to be the one that picks it up.

Each image is processed in its own DB session/transaction so one image's
failure can't roll back another's successful generation in the same batch.
"""

from __future__ import annotations

import uuid

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.modules.media import background, storage
from app.modules.media.preset_registry import Breakpoint, get_preset
from app.modules.media.repository import ImageRepository

log = structlog.get_logger(__name__)

_repo = ImageRepository()

# DNS blips (OSError/socket.gaierror is a subclass) and Postgres-side
# connection rejections (e.g. Supabase's EMAXCONNSESSION pooler cap) are
# expected to happen occasionally and self-resolve on the next 5s tick —
# log them as a quiet warning, not a full stack trace, so real bugs still
# stand out in this worker's logs.
_TRANSIENT_DB_ERRORS = (OSError, asyncpg.exceptions.PostgresError)

MAX_ATTEMPTS = 3
# A worker process crashing/redeploying mid-generation leaves an image
# stuck in 'processing' forever with no `enqueue()` task left to finish
# it — anything older than this is assumed abandoned and requeued.
STALE_AFTER_SECONDS = 120
POLL_BATCH_LIMIT = 20


async def run() -> None:
    """Periodic entry point — registered in app/celery_app.py's Beat schedule
    as `media.sweep_pending`.

    Reclaim and pending-discovery share one AsyncSession/transaction (one
    UPDATE, one SELECT, one COMMIT) instead of two separate sessions each
    with their own commit/rollback lifecycle — each session checkout was
    previously paying for its own connect + transaction-boundary round
    trips even though nothing here needs them isolated: `list_pending_images`
    is a plain read with no locking implications, and the only invariant
    that matters — no image is ever claimed twice — is enforced downstream
    by `try_claim_pending`'s own atomic `UPDATE ... WHERE status='pending'`
    in `process_one()`, not by session boundaries here.

    If the transaction fails after the UPDATE succeeds but before COMMIT,
    that reclaim rolls back too — this is not a correctness loss: a
    still-'processing'-with-stale-updated_at row is exactly what
    `reclaim_stale_processing`'s own WHERE clause is built to catch, so an
    aborted attempt is simply reclaimed again on the next tick (same
    self-healing property the retry logic already relies on elsewhere).
    """
    pending_ids: list[uuid.UUID] = []
    async with AsyncSessionLocal() as db:
        try:
            reclaimed = await _repo.reclaim_stale_processing(
                db, stale_after_seconds=STALE_AFTER_SECONDS
            )
            pending = await _repo.list_pending_images(db, limit=POLL_BATCH_LIMIT)
            pending_ids = [image.id for image in pending]
            await db.commit()
            if reclaimed:
                log.warning("media_generation_reclaimed_stale", count=reclaimed)
        except _TRANSIENT_DB_ERRORS as exc:
            await db.rollback()
            log.warning("media_generation_db_unavailable", error=str(exc))
            return
        except Exception:
            await db.rollback()
            log.exception("media_generation_reclaim_failed")
            return

    for image_id in pending_ids:
        await process_one(image_id)


async def process_one(image_id: uuid.UUID) -> None:
    """
    Claims *image_id* (no-op if something else already claimed/finished
    it), generates every breakpoint recorded in
    `metadata_["generation"]["pending_breakpoints"]`, and commits. On
    failure, either retries (resets to 'pending' for the next poll) or
    gives up after MAX_ATTEMPTS, recording the error.
    """
    async with AsyncSessionLocal() as db:
        try:
            image = await _repo.try_claim_pending(db, image_id)
            if image is None:
                await db.commit()
                return
            # Durably record the claim + attempt count *before* attempting the
            # risky work below — if generation fails and this transaction rolls
            # back, the claim (and this attempt's count) must still stand, or
            # the retry-limit check below would never see it and retry forever.
            await db.commit()
        except _TRANSIENT_DB_ERRORS as exc:
            await db.rollback()
            log.warning(
                "media_generation_db_unavailable",
                image_id=str(image_id),
                error=str(exc),
            )
            return

        try:
            preset = get_preset(image.preset_id)
            original_bytes = await storage.get_object_bytes(image.original_key)
            crops = background.parse_stored_crops(image)
            pending_breakpoints = (image.metadata_.get("generation") or {}).get(
                "pending_breakpoints"
            )
            breakpoints = (
                [Breakpoint(bp) for bp in pending_breakpoints]
                if pending_breakpoints
                else preset.breakpoints
            )
            await background.generate_variants_for_breakpoints(
                db, image, preset, original_bytes, crops, breakpoints
            )
            await db.commit()
            log.info(
                "media_generation_completed",
                image_id=str(image_id),
                breakpoints=[bp.value for bp in breakpoints],
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 — routed to retry/failure below, not swallowed
            await db.rollback()
            log.exception("media_generation_job_failed", image_id=str(image_id))
            await _handle_failure(db, image_id, exc)


async def _handle_failure(
    db: AsyncSession, image_id: uuid.UUID, exc: Exception
) -> None:
    """
    Re-fetches *image_id* (the prior transaction rolled back, so this
    session's identity map is expired — the refetch sees the last
    *committed* state, i.e. status='processing' with this attempt already
    counted) and either retries or gives up.
    """
    image = await _repo.get_image(db, image_id)
    if image is None:
        return
    attempts = (image.metadata_.get("generation") or {}).get("attempts", 1)
    if attempts >= MAX_ATTEMPTS:
        await _repo.mark_generation_failed(db, image, str(exc))
        log.error(
            "media_generation_exhausted_retries",
            image_id=str(image_id),
            attempts=attempts,
        )
    else:
        await _repo.update_fields(db, image, {"status": "pending"})
        log.warning(
            "media_generation_will_retry",
            image_id=str(image_id),
            attempts=attempts,
        )
    await db.commit()
