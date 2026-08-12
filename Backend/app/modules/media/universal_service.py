"""
UniversalImageService — the single orchestration layer for every image
module's upload/crop/replace/attach/reorder/delete/regenerate flow.

The legacy per-module MediaService (app.modules.media.service) was deleted
in the Phase 3 cutover — this is now the only image pipeline for products,
collections, categories, avatars, and reviews (CmsMediaService for CMS/hero/
banner assets is a deliberately separate, not-yet-migrated follow-up). See
docs/architecture/Universal_Responsive_Image_System_Design.md §10, §17.
"""

from __future__ import annotations

import io
import logging
import math
import time
import uuid
from datetime import UTC, datetime

import structlog
from PIL import Image as PILImage
from PIL import ImageOps
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cpu_executor import run_cpu_bound
from app.modules.media import background, storage
from app.modules.media.crop_engine import (
    CropBox,
    default_crop_box,
    validate_crop_request,
)
from app.modules.media.metrics import image_processing_duration_seconds
from app.modules.media.models import Image
from app.modules.media.preset_registry import (
    PRESET_REGISTRY,
    Breakpoint,
    CropPreset,
    get_preset,
)
from app.modules.media.repository import ImageRepository
from app.modules.media.schemas import (
    BreakpointCropIn,
    CropBoxIn,
    CropGeometryIn,
    FocusPointIn,
)
from app.modules.media.validation import (
    ImageValidationError,
    resolve_extension,
    sanitize_svg,
    validate_upload,
)

_repo = ImageRepository()
logger = logging.getLogger(__name__)
_perflog = structlog.get_logger("perf.media.service")


class UniversalImageServiceError(Exception):
    pass


def _probe_dimensions(file_bytes: bytes) -> tuple[int, int]:
    """Pure CPU decode (no validation) — dimensions only. Safe for
    run_cpu_bound: no I/O, no db, no await."""
    probe = PILImage.open(io.BytesIO(file_bytes))
    return probe.size


def _normalize_orientation(file_bytes: bytes) -> bytes:
    """Bakes in the EXIF Orientation tag (if any) and strips it, so every
    later consumer of these bytes — this module's own dimension probe, the
    crop/generate pipeline in background.py, and the browser's <img>
    naturalWidth/naturalHeight used by the crop editor — agree on which axis
    is width and which is height. Plain `Image.open(...).size` ignores EXIF
    orientation, but browsers auto-rotate for display; without normalizing
    up front, a portrait photo stored with a rotate-90 tag probes as
    landscape server-side while the client computes crop boxes against the
    portrait dimensions it actually renders, and PATCH .../crop rejects an
    otherwise-valid box as out of bounds. A no-op for images with no
    orientation tag, or that PIL can't decode at all — the latter is left
    for validate_upload's own decode to raise a proper ImageValidationError
    instead of surfacing an unhandled PIL exception here."""
    try:
        image = PILImage.open(io.BytesIO(file_bytes))
        if image.getexif().get(0x0112, 1) == 1:
            return file_bytes
    except Exception:
        return file_bytes

    transposed = ImageOps.exif_transpose(image)
    if transposed is None:
        return file_bytes

    buffer = io.BytesIO()
    fmt = image.format or "JPEG"
    save_kwargs = {"quality": 95} if fmt == "JPEG" else {}
    transposed.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


async def _normalize_orientation_off_loop(
    file_bytes: bytes, preset: CropPreset
) -> bytes:
    cpu_start = time.perf_counter()
    try:
        return await run_cpu_bound(lambda: _normalize_orientation(file_bytes))
    finally:
        image_processing_duration_seconds.labels(
            preset=preset.id, stage="normalize_orientation"
        ).observe(time.perf_counter() - cpu_start)


async def _validate_upload_off_loop(
    file_bytes: bytes, filename: str, content_type: str, preset: CropPreset
) -> None:
    """validate_upload does Image.open(...).verify() — a real decode, not
    just a header peek — so it belongs on the CPU executor same as the
    generation pipeline, not inline on the request coroutine."""
    cpu_start = time.perf_counter()
    try:
        await run_cpu_bound(
            lambda: validate_upload(file_bytes, filename, content_type, preset)
        )
    finally:
        image_processing_duration_seconds.labels(
            preset=preset.id, stage="validate"
        ).observe(time.perf_counter() - cpu_start)


async def _probe_dimensions_off_loop(
    file_bytes: bytes, preset: CropPreset
) -> tuple[int, int]:
    cpu_start = time.perf_counter()
    try:
        return await run_cpu_bound(lambda: _probe_dimensions(file_bytes))
    finally:
        image_processing_duration_seconds.labels(
            preset=preset.id, stage="probe"
        ).observe(time.perf_counter() - cpu_start)


def _crops_equal(a: BreakpointCropIn, b: BreakpointCropIn | None) -> bool:
    """True if *a* and *b* describe the same crop geometry.

    Floats round-trip through JSON/Pydantic, so exact equality is unsafe —
    compare with a tolerance instead of `==`.
    """
    if b is None:
        return False
    fields = (
        (a.box.x, b.box.x),
        (a.box.y, b.box.y),
        (a.box.width, b.box.width),
        (a.box.height, b.box.height),
        (a.zoom, b.zoom),
        (a.pan.get("x", 0.0), b.pan.get("x", 0.0)),
        (a.pan.get("y", 0.0), b.pan.get("y", 0.0)),
        (a.rotation, b.rotation),
    )
    return all(math.isclose(x, y, abs_tol=1e-6) for x, y in fields)


def _default_crops_for_preset(
    preset: CropPreset, image_width: int, image_height: int
) -> dict[Breakpoint, BreakpointCropIn]:
    crops: dict[Breakpoint, BreakpointCropIn] = {}
    for bp in preset.breakpoints:
        aspect = preset.aspect_ratio.get(bp)
        box = default_crop_box(image_width, image_height, aspect)
        crops[bp] = BreakpointCropIn(
            box=CropBoxIn(x=box.x, y=box.y, width=box.width, height=box.height),
            zoom=1.0,
            pan={"x": 0.0, "y": 0.0},
            rotation=0.0,
        )
    return crops


def _geometry_metadata(
    preset: CropPreset,
    original_width: int,
    original_height: int,
    crops: dict[Breakpoint, BreakpointCropIn],
    focus_point: FocusPointIn,
) -> dict:
    return {
        "preset_id": preset.id,
        "shape": preset.shape.value,
        "focus_point": focus_point.model_dump(),
        "safe_area": preset.safe_area.model_dump(),
        "original_dimensions": {"width": original_width, "height": original_height},
        "crops": {
            bp.value: {
                "aspect_ratio": preset.aspect_ratio.get(bp),
                "box": crop.box.model_dump(),
                "zoom": crop.zoom,
                "pan": crop.pan,
                "rotation": crop.rotation,
            }
            for bp, crop in crops.items()
        },
    }


class UniversalImageService:
    def list_presets(self) -> list[CropPreset]:
        return list(PRESET_REGISTRY.values())

    def get_preset(self, preset_id: str) -> CropPreset:
        return get_preset(preset_id)

    async def upload(
        self,
        db: AsyncSession,
        *,
        preset_id: str,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        owner_type: str,
        owner_id: uuid.UUID | None,
        uploaded_by: uuid.UUID | None,
        skip_initial_generation: bool = False,
    ) -> Image:
        _t0 = time.perf_counter()
        _phases: list[tuple[str, float]] = []

        def _mark(label: str) -> None:
            _phases.append((label, (time.perf_counter() - _t0) * 1000))

        preset = get_preset(preset_id)
        is_svg = content_type == "image/svg+xml"
        if not is_svg:
            file_bytes = await _normalize_orientation_off_loop(file_bytes, preset)
            _mark("normalize_orientation")

        try:
            await _validate_upload_off_loop(file_bytes, filename, content_type, preset)
        except ImageValidationError as exc:
            raise UniversalImageServiceError(str(exc)) from exc
        _mark("validate")

        if is_svg:
            try:
                file_bytes = sanitize_svg(file_bytes)
            except ImageValidationError as exc:
                raise UniversalImageServiceError(str(exc)) from exc

        ext = resolve_extension(filename, content_type)
        image_id = uuid.uuid4()

        if is_svg:
            width, height = 0, 0
        else:
            width, height = await _probe_dimensions_off_loop(file_bytes, preset)
        _mark("probe_dims")

        original_key = storage.build_original_key(
            preset.id, owner_type, owner_id, image_id, ext
        )
        await storage.put_original(original_key, file_bytes, ext=ext)
        _mark("r2_put_original")

        focus_point = FocusPointIn()
        crops = _default_crops_for_preset(preset, width or 1, height or 1)

        image = await _repo.create_image(
            db,
            id=image_id,
            module=preset.id,
            preset_id=preset.id,
            owner_type=owner_type,
            owner_id=owner_id,
            original_key=original_key,
            original_ext=ext,
            original_width=width,
            original_height=height,
            original_size_bytes=len(file_bytes),
            mime_type=content_type,
            uploaded_by=uploaded_by,
            status="pending",
            metadata_=_geometry_metadata(preset, width, height, crops, focus_point),
        )
        _mark("db_create_image")

        if is_svg:
            image = await self._finalize_svg(db, image, preset)
            _mark("finalize_svg")
        elif not skip_initial_generation:
            image = await self._enqueue_generation(db, image, preset.breakpoints)
            _mark("enqueue_generation")

        _mark("done")
        _perflog.info(
            "upload_service_phases",
            preset_id=preset_id,
            image_id=str(image_id),
            phases=_phases,
        )
        return image

    async def _finalize_svg(
        self, db: AsyncSession, image: Image, preset: CropPreset
    ) -> Image:
        original_url = storage.public_url(image.original_key)
        for bp in preset.breakpoints:
            variant_rows = [
                {
                    "id": uuid.uuid4(),
                    "breakpoint": bp.value,
                    "variant_name": spec.name,
                    "dpr": dpr,
                    "format": "svg",
                    "url": original_url,
                    "width": spec.width,
                    "height": spec.height,
                    "size_bytes": image.original_size_bytes,
                    "status": "ready",
                    "error_message": None,
                }
                for spec in preset.output_variants
                for dpr in spec.dprs
            ]
            await _repo.replace_variants(db, image, bp.value, variant_rows)
        return await _repo.update_fields(db, image, {"status": "ready"})

    async def crop(
        self,
        db: AsyncSession,
        *,
        image: Image,
        payload: CropGeometryIn,
    ) -> Image:
        _t0 = time.perf_counter()
        _phases: list[tuple[str, float]] = []

        def _mark(label: str) -> None:
            _phases.append((label, (time.perf_counter() - _t0) * 1000))

        preset = get_preset(image.preset_id)

        if image.mime_type == "image/svg+xml":
            return await self._finalize_svg(db, image, preset)

        stored_crops = background.parse_stored_crops(image)
        if not stored_crops:
            stored_crops = _default_crops_for_preset(
                preset, image.original_width or 1, image.original_height or 1
            )
        merged_crops = {**stored_crops, **payload.crops}

        ready_breakpoints = {
            v.breakpoint for v in image.variants if v.status == "ready"
        }
        changed_breakpoints = [
            bp
            for bp, geom in payload.crops.items()
            if bp.value not in ready_breakpoints
            or not _crops_equal(geom, stored_crops.get(bp))
        ]
        _mark("compute_diff")

        for bp in changed_breakpoints:
            crop_in = merged_crops[bp]
            validate_crop_request(
                preset,
                image.original_width,
                image.original_height,
                CropBox(
                    x=crop_in.box.x,
                    y=crop_in.box.y,
                    width=crop_in.box.width,
                    height=crop_in.box.height,
                ),
                crop_in.rotation,
            )
        _mark("validate_geometry")

        image = await _repo.update_metadata(
            db,
            image,
            _geometry_metadata(
                preset,
                image.original_width,
                image.original_height,
                merged_crops,
                payload.focus_point,
            ),
        )
        _mark("db_update_metadata")

        if changed_breakpoints:
            image = await self._enqueue_generation(db, image, changed_breakpoints)
            _mark("enqueue_generation")

        _mark("done")
        _perflog.info(
            "crop_service_phases",
            image_id=str(image.id),
            changed_bps=[bp.value for bp in changed_breakpoints],
            phases=_phases,
        )
        return image

    async def replace(
        self,
        db: AsyncSession,
        *,
        image: Image,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> Image:
        preset = get_preset(image.preset_id)
        is_svg = content_type == "image/svg+xml"
        if not is_svg:
            file_bytes = await _normalize_orientation_off_loop(file_bytes, preset)

        try:
            await _validate_upload_off_loop(file_bytes, filename, content_type, preset)
        except ImageValidationError as exc:
            raise UniversalImageServiceError(str(exc)) from exc

        if is_svg:
            try:
                file_bytes = sanitize_svg(file_bytes)
            except ImageValidationError as exc:
                raise UniversalImageServiceError(str(exc)) from exc
            width, height = 0, 0
        else:
            width, height = await _probe_dimensions_off_loop(file_bytes, preset)

        await storage.put_original(
            image.original_key, file_bytes, ext=image.original_ext
        )
        await _repo.delete_all_variants(db, image)

        focus_point = FocusPointIn()
        crops = _default_crops_for_preset(preset, width or 1, height or 1)
        image = await _repo.update_fields(
            db,
            image,
            {
                "original_width": width,
                "original_height": height,
                "original_size_bytes": len(file_bytes),
                "mime_type": content_type,
                "status": "pending",
                "version": image.version + 1,
                "metadata_": _geometry_metadata(
                    preset, width, height, crops, focus_point
                ),
            },
        )

        if is_svg:
            image = await self._finalize_svg(db, image, preset)
        else:
            image = await self._enqueue_generation(db, image, preset.breakpoints)
        return image

    async def attach(
        self, db: AsyncSession, *, image: Image, owner_type: str, owner_id: uuid.UUID
    ) -> Image:
        return await _repo.update_fields(
            db, image, {"owner_type": owner_type, "owner_id": owner_id}
        )

    async def update_alt_text(
        self, db: AsyncSession, *, image: Image, alt_text: str | None
    ) -> Image:
        return await _repo.update_fields(
            db, image, {"alt_text": alt_text.strip() if alt_text else None}
        )

    async def reorder(
        self, db: AsyncSession, items: list[tuple[uuid.UUID, int]]
    ) -> None:
        await _repo.reorder(db, items)

    async def set_primary(self, db: AsyncSession, *, image: Image) -> Image:
        if image.owner_id is None:
            raise UniversalImageServiceError(
                "Cannot set an unattached image as primary — attach it to an owner first"
            )
        image_id = image.id
        await _repo.set_primary(db, image.owner_type, image.owner_id, image_id)
        refreshed = await _repo.get_image(db, image_id)
        assert refreshed is not None
        return refreshed

    async def delete(self, db: AsyncSession, *, image: Image) -> None:
        key_prefix = image.original_key.rsplit("/", 1)[0] + "/"
        purged = await storage.delete_image_folder(image.id, key_prefix)
        if not purged:
            # The DB row still gets soft-deleted below (the admin-facing
            # delete must not appear to fail just because R2 cleanup did),
            # but leaving this silent means the R2 objects are orphaned
            # with no record anywhere. `delete_image_folder` already logs
            # the underlying error; this makes the *consequence* — an
            # orphan that needs manual/lifecycle-rule cleanup — findable by
            # searching logs for image_id (docs audit HP-7/MF-8).
            logger.warning(
                "delete: R2 folder purge incomplete for image %s (prefix %s) — "
                "objects orphaned, soft-deleting DB row anyway",
                image.id,
                key_prefix,
            )
        await _repo.soft_delete(db, image)

    async def regenerate(self, db: AsyncSession, *, image: Image) -> Image:
        preset = get_preset(image.preset_id)
        if image.mime_type == "image/svg+xml":
            return await self._finalize_svg(db, image, preset)
        return await self._enqueue_generation(db, image, preset.breakpoints)

    async def _enqueue_generation(
        self, db: AsyncSession, image: Image, breakpoints: list[Breakpoint]
    ) -> Image:
        """
        Marks *image* pending for *breakpoints* and hands the actual
        crop/encode/R2-upload work to the background worker instead of
        awaiting it in-request — this call (and therefore the HTTP
        response) returns as soon as the "pending" status + which
        breakpoints need regenerating are persisted, not after however long
        the real generation takes (docs audit CB-1 Phase 2; Phase 1's
        `background.generate_variants_for_breakpoints` parallel-upload fix
        is unchanged and is exactly what the worker calls).

        `app.tasks.media.generate_variants` is dispatched as a Celery task
        for near-immediate processing in the common case; the periodic
        `media.sweep_pending` Beat task is the crash-recovery/retry net (and
        the only path at all in a multi-process deployment, where the
        process that received this request may not be the one still running
        once R2 generation finishes). Dispatch is fire-and-forget — the two
        can race on the same image exactly as before (module docstring of
        app.workers.media_generation), and `try_claim_pending`'s atomic
        claim is what makes that race safe regardless of which one wins.
        """
        from app.tasks.media import generate_variants

        _t0 = time.perf_counter()

        generation = dict(image.metadata_.get("generation") or {})
        generation["pending_breakpoints"] = [bp.value for bp in breakpoints]
        generation["queued_at"] = datetime.now(UTC).isoformat()
        image = await _repo.update_fields(
            db,
            image,
            {
                "status": "pending",
                "metadata_": {**image.metadata_, "generation": generation},
            },
        )
        _mark_db = (time.perf_counter() - _t0) * 1000

        generate_variants.delay(str(image.id))
        _mark_enqueue = (time.perf_counter() - _t0) * 1000 - _mark_db

        _perflog.debug(
            "enqueue_generation",
            image_id=str(image.id),
            breakpoints=[bp.value for bp in breakpoints],
            update_fields_ms=round(_mark_db, 2),
            enqueue_ms=round(_mark_enqueue, 2),
        )
        return image
