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
import uuid

from fastapi import BackgroundTasks
from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.media import background, storage
from app.modules.media.crop_engine import default_crop_box
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
    validate_upload,
)

# Presets whose total (breakpoint x variant x dpr) artifact count is large
# enough that generating them inline would noticeably delay the HTTP
# response — offloaded to a FastAPI BackgroundTasks callback instead
# (architecture doc §8). Everything else generates synchronously in-request.
_BACKGROUND_ARTIFACT_THRESHOLD = 6

_repo = ImageRepository()


class UniversalImageServiceError(Exception):
    pass


def _artifact_count(preset: CropPreset, breakpoints: list[Breakpoint]) -> int:
    return sum(len(v.dprs) for v in preset.output_variants) * len(breakpoints)


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
        background_tasks: BackgroundTasks,
    ) -> Image:
        preset = get_preset(preset_id)
        try:
            validate_upload(file_bytes, filename, content_type, preset)
        except ImageValidationError as exc:
            raise UniversalImageServiceError(str(exc)) from exc

        ext = resolve_extension(filename, content_type)
        image_id = uuid.uuid4()

        if content_type == "image/svg+xml":
            width, height = 0, 0
        else:
            probe = PILImage.open(io.BytesIO(file_bytes))
            width, height = probe.size

        original_key = storage.build_original_key(
            preset.id, owner_type, owner_id, image_id, ext
        )
        storage.put_original(original_key, file_bytes, ext=ext)

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

        await self._generate(
            db, image, preset, file_bytes, crops, preset.breakpoints, background_tasks
        )
        return image

    async def crop(
        self,
        db: AsyncSession,
        *,
        image: Image,
        payload: CropGeometryIn,
        background_tasks: BackgroundTasks,
    ) -> Image:
        preset = get_preset(image.preset_id)
        original_bytes = storage.get_object_bytes(image.original_key)

        existing_crops = _default_crops_for_preset(
            preset, image.original_width or 1, image.original_height or 1
        )
        merged_crops = {**existing_crops, **payload.crops}

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

        changed_breakpoints = list(payload.crops.keys())
        await self._generate(
            db,
            image,
            preset,
            original_bytes,
            merged_crops,
            changed_breakpoints,
            background_tasks,
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
        background_tasks: BackgroundTasks,
    ) -> Image:
        preset = get_preset(image.preset_id)
        try:
            validate_upload(file_bytes, filename, content_type, preset)
        except ImageValidationError as exc:
            raise UniversalImageServiceError(str(exc)) from exc

        probe = PILImage.open(io.BytesIO(file_bytes))
        width, height = probe.size

        storage.put_original(image.original_key, file_bytes, ext=image.original_ext)
        await _repo.delete_all_variants(db, image)

        focus_point = FocusPointIn()
        crops = _default_crops_for_preset(preset, width, height)
        image = await _repo.update_fields(
            db,
            image,
            {
                "original_width": width,
                "original_height": height,
                "original_size_bytes": len(file_bytes),
                "status": "pending",
                "version": image.version + 1,
                "metadata_": _geometry_metadata(
                    preset, width, height, crops, focus_point
                ),
            },
        )

        await self._generate(
            db, image, preset, file_bytes, crops, preset.breakpoints, background_tasks
        )
        return image

    async def attach(
        self, db: AsyncSession, *, image: Image, owner_type: str, owner_id: uuid.UUID
    ) -> Image:
        return await _repo.update_fields(
            db, image, {"owner_type": owner_type, "owner_id": owner_id}
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
        await _repo.set_primary(db, image.owner_type, image.owner_id, image.id)
        refreshed = await _repo.get_image(db, image.id)
        assert refreshed is not None
        return refreshed

    async def delete(self, db: AsyncSession, *, image: Image) -> None:
        key_prefix = image.original_key.rsplit("/", 1)[0] + "/"
        storage.delete_image_folder(image.id, key_prefix)
        await _repo.soft_delete(db, image)

    async def regenerate(
        self, db: AsyncSession, *, image: Image, background_tasks: BackgroundTasks
    ) -> Image:
        preset = get_preset(image.preset_id)
        original_bytes = storage.get_object_bytes(image.original_key)
        crops_meta = image.metadata_.get("crops", {})
        crops = {
            Breakpoint(bp): BreakpointCropIn(
                box=CropBoxIn(**c["box"]),
                zoom=c["zoom"],
                pan=c["pan"],
                rotation=c["rotation"],
            )
            for bp, c in crops_meta.items()
        }
        await self._generate(
            db,
            image,
            preset,
            original_bytes,
            crops,
            preset.breakpoints,
            background_tasks,
        )
        return image

    async def _generate(
        self,
        db: AsyncSession,
        image: Image,
        preset: CropPreset,
        original_bytes: bytes,
        crops: dict[Breakpoint, BreakpointCropIn],
        breakpoints: list[Breakpoint],
        background_tasks: BackgroundTasks,
    ) -> None:
        if _artifact_count(preset, breakpoints) >= _BACKGROUND_ARTIFACT_THRESHOLD:
            background_tasks.add_task(
                background.generate_variants_task, image.id, preset, crops, breakpoints
            )
        else:
            await background.generate_variants_for_breakpoints(
                db, image, preset, original_bytes, crops, breakpoints
            )
