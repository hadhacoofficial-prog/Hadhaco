"""
Variant generation orchestration — the one place that runs the full
crop_engine -> variant_generator -> storage pipeline and persists the
results as image_variants rows.

Called either synchronously in-request (small/legacy presets) or from the
background worker (`app.workers.media_generation`, the production path for
crop/upload/replace/regenerate) — see
docs/architecture/Universal_Responsive_Image_System_Design.md §8 and docs
audit CB-1. `upload_variant_artifact` is the one unit of work both callers
share, so parallelizing it here (Phase 1 of the CB-1 fix) is not thrown away
by the background-worker migration (Phase 2) — the worker calls the exact
same function.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from collections import defaultdict

from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.media import storage
from app.modules.media.crop_engine import CropBox, CropGeometryError, apply_geometry
from app.modules.media.models import Image
from app.modules.media.preset_registry import Breakpoint, CropPreset
from app.modules.media.repository import ImageRepository
from app.modules.media.schemas import BreakpointCropIn, CropBoxIn
from app.modules.media.variant_generator import (
    GeneratedVariant,
    generate_variants_for_breakpoint,
)

logger = logging.getLogger(__name__)

_repo = ImageRepository()


def parse_stored_crops(image: Image) -> dict[Breakpoint, BreakpointCropIn]:
    """Reconstructs each breakpoint's currently-saved crop geometry from
    `image.metadata_["crops"]` (written by universal_service._geometry_metadata)
    — the source of truth for "what does this image currently look like", as
    opposed to a freshly-computed centered default. Shared by
    UniversalImageService (crop/regenerate) and the media_generation worker,
    which both need to rebuild the same crops dict from a persisted image
    row rather than from request-scoped state."""
    crops_meta = image.metadata_.get("crops", {}) if image.metadata_ else {}
    return {
        Breakpoint(bp): BreakpointCropIn(
            box=CropBoxIn(**c["box"]),
            zoom=c["zoom"],
            pan=c["pan"],
            rotation=c["rotation"],
        )
        for bp, c in crops_meta.items()
    }


async def upload_variant_artifact(
    image: Image,
    preset: CropPreset,
    artifact: GeneratedVariant,
) -> dict:
    """
    Uploads one generated (breakpoint, variant_name, dpr) artifact to R2 and
    returns its `image_variants` row — status='ready' or 'failed', never
    raises. This is the single unit of work shared by
    `generate_variants_for_breakpoints`'s `asyncio.gather` fan-out and the
    background worker, so there is exactly one place that knows how to turn
    a `GeneratedVariant` into a persisted row.
    """
    key = storage.build_variant_key(
        module=preset.id,
        owner_type=image.owner_type,
        owner_id=image.owner_id,
        image_id=image.id,
        breakpoint=artifact.breakpoint.value,
        variant_name=artifact.variant_name,
        dpr=artifact.dpr,
        fmt=artifact.format,
    )
    try:
        await storage.put_variant(key, artifact.content, fmt=artifact.format)
        status, error_message = "ready", None
    except Exception as exc:  # noqa: BLE001 — recorded per-variant, not swallowed
        logger.error(
            "Variant upload failed image_id=%s breakpoint=%s variant=%s",
            image.id,
            artifact.breakpoint.value,
            artifact.variant_name,
            exc_info=True,
        )
        status, error_message = "failed", str(exc)

    return {
        "id": uuid.uuid4(),
        "breakpoint": artifact.breakpoint.value,
        "variant_name": artifact.variant_name,
        "dpr": artifact.dpr,
        "format": artifact.format,
        "url": storage.public_url(key),
        "width": artifact.width,
        "height": artifact.height,
        "size_bytes": len(artifact.content),
        "status": status,
        "error_message": error_message,
    }


async def generate_variants_for_breakpoints(
    db: AsyncSession,
    image: Image,
    preset: CropPreset,
    original_bytes: bytes,
    crops: dict[Breakpoint, BreakpointCropIn],
    breakpoints: list[Breakpoint],
) -> None:
    """
    Regenerate every output_variant for each breakpoint in *breakpoints*,
    always cropping from *original_bytes* (never a previously-derived
    variant). Per-variant failures are caught individually and recorded as
    status='failed' rows rather than aborting the whole batch (closes G12 —
    no bare except/pass, no silently-orphaned partial state).

    Cropping (CPU, fast) happens breakpoint-by-breakpoint first — a
    CropGeometryError aborts the whole call before any R2 upload starts, so
    a bad geometry payload never leaves a partial batch of variants written.
    Every resulting artifact across *every* breakpoint is then uploaded
    concurrently via `asyncio.gather` (bounded by storage._R2_CONCURRENCY),
    since sequential awaits here — one R2 round trip at a time — were the
    actual measured cause of 12-27s crop requests (docs audit CB-1), not
    the CPU-bound resize/encode work. DB writes stay sequential per
    breakpoint after the uploads land, since a single AsyncSession isn't
    safe to use concurrently.
    """
    per_breakpoint_artifacts: dict[Breakpoint, list[GeneratedVariant]] = {}
    for breakpoint in breakpoints:
        crop_in = crops.get(breakpoint)
        if crop_in is None:
            continue

        raw = PILImage.open(io.BytesIO(original_bytes))
        raw.load()
        box = CropBox(
            x=crop_in.box.x,
            y=crop_in.box.y,
            width=crop_in.box.width,
            height=crop_in.box.height,
        )
        try:
            cropped = apply_geometry(
                raw, box, rotation_degrees=crop_in.rotation, preset=preset
            )
        except CropGeometryError:
            # Hard geometry failure (strict_bounds preset, box doesn't fit) —
            # nothing to persist for any breakpoint; caller already
            # validated this before calling us for the strict case, so this
            # is a defensive re-raise rather than an expected path.
            raise

        per_breakpoint_artifacts[breakpoint] = generate_variants_for_breakpoint(
            cropped, preset.output_variants, breakpoint
        )

    rows = await asyncio.gather(
        *(
            upload_variant_artifact(image, preset, artifact)
            for artifacts in per_breakpoint_artifacts.values()
            for artifact in artifacts
        )
    )

    rows_by_breakpoint: dict[Breakpoint, list[dict]] = defaultdict(list)
    for row in rows:
        rows_by_breakpoint[Breakpoint(row["breakpoint"])].append(row)
    for breakpoint in per_breakpoint_artifacts:
        await _repo.replace_variants(
            db, image, breakpoint.value, rows_by_breakpoint.get(breakpoint, [])
        )

    # Re-check the image is still live before writing final status. Variant
    # generation for a large-artifact preset can take long enough that the
    # image gets soft-deleted out from under it mid-run; without this check
    # the status write below would silently resurrect a row the user just
    # removed.
    current = await _repo.get_image(db, image.id)
    if current is None:
        logger.warning(
            "generate_variants_for_breakpoints: image %s was deleted mid-run — "
            "discarding final status update",
            image.id,
        )
        return

    any_failed = any(v.status == "failed" for v in image.variants)
    # Bumping version here (not just when crop()/upload() first persist the
    # request) is what makes the `?v=` cache-buster on variant URLs
    # actually work end-to-end. Those endpoints return immediately, before
    # generation has produced any new bytes — a client that renders that
    # response's (already version-bumped) variant URL right away caches
    # *stale* content under that version. Without a second bump here, the
    # eventual "ready" response reuses that same URL and the browser just
    # serves its stale cached copy forever (docs audit CB-1 Phase 2 —
    # observed as "the new crop only shows up after a hard refresh").
    await _repo.update_fields(
        db,
        image,
        {"status": "failed" if any_failed else "ready", "version": current.version + 1},
    )
