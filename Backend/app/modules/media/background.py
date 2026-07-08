"""
Variant generation orchestration — the one place that runs the full
crop_engine -> variant_generator -> storage pipeline and persists the
results as image_variants rows.

Called synchronously (small presets) or via FastAPI BackgroundTasks (large,
multi-artifact presets like hero/promo_banner) — see router.py. Either way
it operates on a self-contained set of arguments, not request-bound state,
so it works the same in both call modes.

See docs/architecture/Universal_Responsive_Image_System_Design.md §8.
"""

from __future__ import annotations

import io
import logging
import uuid

from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.media import storage
from app.modules.media.crop_engine import CropBox, CropGeometryError, apply_geometry
from app.modules.media.models import Image
from app.modules.media.preset_registry import Breakpoint, CropPreset
from app.modules.media.repository import ImageRepository
from app.modules.media.schemas import BreakpointCropIn
from app.modules.media.variant_generator import generate_variants_for_breakpoint

logger = logging.getLogger(__name__)

_repo = ImageRepository()


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
    """
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
            # nothing to persist for this breakpoint; caller already
            # validated this before calling us for the strict case, so this
            # is a defensive re-raise rather than an expected path.
            raise

        generated = generate_variants_for_breakpoint(
            cropped, preset.output_variants, breakpoint
        )

        variant_rows: list[dict] = []
        for artifact in generated:
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
                storage.put_variant(key, artifact.content, fmt=artifact.format)
                status, error_message = "ready", None
            except (
                Exception
            ) as exc:  # noqa: BLE001 — recorded per-variant, not swallowed
                logger.error(
                    "Variant upload failed image_id=%s breakpoint=%s variant=%s",
                    image.id,
                    artifact.breakpoint.value,
                    artifact.variant_name,
                    exc_info=True,
                )
                status, error_message = "failed", str(exc)

            variant_rows.append(
                {
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
            )

        await _repo.replace_variants(db, image, breakpoint.value, variant_rows)

    # Re-check the image is still live before writing final status. Variant
    # generation for one breakpoint can take long enough (large-artifact
    # presets, background-task path) that the image gets soft-deleted out
    # from under it mid-run; without this check the status write below would
    # silently resurrect a row the user just removed.
    current = await _repo.get_image(db, image.id)
    if current is None:
        logger.warning(
            "generate_variants_for_breakpoints: image %s was deleted mid-run — "
            "discarding final status update",
            image.id,
        )
        return

    any_failed = any(v.status == "failed" for v in image.variants)
    await _repo.update_fields(
        db, image, {"status": "failed" if any_failed else "ready"}
    )


async def generate_variants_task(
    image_id: uuid.UUID,
    preset: CropPreset,
    crops: dict[Breakpoint, BreakpointCropIn],
    breakpoints: list[Breakpoint],
) -> None:
    """Background-task entry point — opens its own worker session and refetches
    everything it needs from image_id, since the request's session is gone
    by the time this runs (used for hero/banner-scale, 6+ artifact presets)."""
    from app.core.database import AsyncWorkerSessionLocal

    async with AsyncWorkerSessionLocal() as db:
        image = await _repo.get_image(db, image_id)
        if image is None:
            # Expected outcome of a legitimate race, not a bug: the image was
            # soft-deleted (or never committed by an upload that itself
            # failed) before this deferred task got to run. Nothing to
            # generate variants for — log for visibility, not as an error
            # that pages anyone.
            logger.warning(
                "generate_variants_task: image %s not found (likely deleted "
                "before background generation ran)",
                image_id,
            )
            return
        original_bytes = storage.get_object_bytes(image.original_key)
        await generate_variants_for_breakpoints(
            db, image, preset, original_bytes, crops, breakpoints
        )
