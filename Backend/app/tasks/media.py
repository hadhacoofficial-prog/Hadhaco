"""Celery entrypoints for image variant generation.

Two tasks, mirroring the two paths that already existed under APScheduler
(see app/workers/media_generation.py's module docstring):

* ``media.sweep_pending`` — Beat-triggered every 5s. The crash-recovery net:
  reclaims images stuck in 'processing' (a worker died mid-run) and
  processes whatever is pending. Still the *only* path that's guaranteed to
  run in a multi-process deployment.
* ``media.generate_variants`` — HTTP-triggered. Replaces the former
  ``asyncio.create_task`` fast path fired from
  ``universal_service._enqueue_generation`` (plan §2/§4). Dispatched with
  ``.delay(str(image_id))`` right after the "pending" DB state commits, so
  the HTTP response does not wait on generation, but the work is now a
  durable Celery task instead of an in-process task that's lost if the API
  process is killed mid-run (the periodic sweep already covered that
  correctness gap by re-processing on the next tick — this removes the
  wasted duplicate R2 round-trip that recovery required, per plan §2).
"""

from __future__ import annotations

import uuid

from app.celery_app import celery_app
from app.tasks._common import backoff_seconds, is_transient, run_async, task_run_log
from app.workers import media_generation


@celery_app.task(
    name="media.sweep_pending",
    bind=True,
    max_retries=3,
    time_limit=120,
    soft_time_limit=90,
)
def sweep_pending(self) -> None:
    with task_run_log(self):
        try:
            run_async(media_generation.run)
        except Exception as exc:
            if is_transient(exc):
                raise self.retry(
                    exc=exc, countdown=backoff_seconds(self.request.retries)
                ) from exc
            raise


@celery_app.task(
    name="media.generate_variants",
    bind=True,
    max_retries=2,
    time_limit=120,
    soft_time_limit=90,
)
def generate_variants(self, image_id: str) -> None:
    """*image_id* is passed as ``str`` (JSON-serializable); process_one()
    parses it back to a UUID, matching the type `ImageRepository` expects.

    Celery's own 2 retries only cover failures *before* process_one's own
    DB-tracked MAX_ATTEMPTS mechanism takes over (e.g. the DB pool being
    exhausted when opening the session) — a claim race with the periodic
    sweep, or a genuine generation failure, is handled entirely inside
    process_one/_handle_failure exactly as before, and is a safe no-op or
    retry-via-next-sweep-tick either way (try_claim_pending's atomic claim,
    plan §11).
    """
    with task_run_log(self):
        try:
            run_async(lambda: media_generation.process_one(uuid.UUID(image_id)))
        except Exception as exc:
            if is_transient(exc):
                raise self.retry(
                    exc=exc, countdown=backoff_seconds(self.request.retries)
                ) from exc
            raise
