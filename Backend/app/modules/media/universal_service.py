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
import uuid
from datetime import UTC, datetime

from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.media import background, storage
from app.modules.media.crop_engine import (
    CropBox,
    default_crop_box,
    validate_crop_request,
)
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


class UniversalImageServiceError(Exception):
    pass


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
        preset = get_preset(preset_id)
        try:
            validate_upload(file_bytes, filename, content_type, preset)
        except ImageValidationError as exc:
            raise UniversalImageServiceError(str(exc)) from exc

        is_svg = content_type == "image/svg+xml"
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
            probe = PILImage.open(io.BytesIO(file_bytes))
            width, height = probe.size

        original_key = storage.build_original_key(
            preset.id, owner_type, owner_id, image_id, ext
        )
        await storage.put_original(original_key, file_bytes, ext=ext)

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

        if is_svg:
            # SVG is already vector/scalable — there's nothing to crop or
            # raster-resize, and no SVG rasterizer is installed (forcing one
            # through PIL crashes; see docs audit CB-3). Every declared
            # variant slot just points at the original SVG object.
            image = await self._finalize_svg(db, image, preset)
        elif not skip_initial_generation:
            # Callers that know they'll immediately follow this upload with
            # a crop() call (the editor's upload-then-crop flow) pass
            # skip_initial_generation=True so the default centered crop
            # never gets encoded+uploaded just to be thrown away a moment
            # later by the real geometry (docs audit HP-5).
            image = await self._enqueue_generation(db, image, preset.breakpoints)
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
        preset = get_preset(image.preset_id)

        if image.mime_type == "image/svg+xml":
            # No raster crop is possible (or meaningful) on a vector
            # original — a crop request against an SVG is a no-op that just
            # re-confirms every variant slot still points at the original.
            return await self._finalize_svg(db, image, preset)

        stored_crops = background.parse_stored_crops(image)
        if not stored_crops:
            # Defensive fallback only — upload() always seeds metadata_.crops,
            # so a live image should never actually reach this branch.
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

        # Validate geometry synchronously, before persisting or enqueueing —
        # generation itself now runs in the background (docs audit CB-1
        # Phase 2), so this is the only remaining place a genuinely invalid
        # crop request (disallowed rotation, out-of-bounds box on a
        # strict_bounds preset) can still surface as an immediate 422
        # (docs audit HP-3) instead of only failing minutes later in a
        # worker with no request left to report it to. Uses the original's
        # already-stored dimensions — no R2 fetch needed for this check.
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

        if changed_breakpoints:
            image = await self._enqueue_generation(db, image, changed_breakpoints)
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
        try:
            validate_upload(file_bytes, filename, content_type, preset)
        except ImageValidationError as exc:
            raise UniversalImageServiceError(str(exc)) from exc

        is_svg = content_type == "image/svg+xml"
        if is_svg:
            try:
                file_bytes = sanitize_svg(file_bytes)
            except ImageValidationError as exc:
                raise UniversalImageServiceError(str(exc)) from exc
            width, height = 0, 0
        else:
            probe = PILImage.open(io.BytesIO(file_bytes))
            width, height = probe.size

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

        `app.workers.media_generation.enqueue()` fires an
        `asyncio.create_task` fast path for near-immediate processing in
        the common case; the periodic `media_generation` worker job is the
        crash-recovery/retry net (and the only path at all in a
        multi-process deployment, where the process that received this
        request may not be the one still running once R2 generation
        finishes).
        """
        from app.workers import media_generation

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
        media_generation.enqueue(image.id)
        return image
