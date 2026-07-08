from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.modules.media.preset_registry import Breakpoint, CropPreset


class PresetOut(BaseModel):
    """Public projection of a CropPreset — GET /admin/media/presets."""

    id: str
    label: str
    shape: str
    mask_svg: str | None
    aspect_ratio: dict[str, float | None]
    safe_area: dict[str, float]
    min_resolution: dict[str, dict[str, int]]
    max_zoom: float
    rotation: dict[str, Any]
    breakpoints: list[str]
    output_variants: list[dict[str, Any]]
    storage_rules: dict[str, Any]
    reference_ui: str

    @classmethod
    def from_preset(cls, preset: CropPreset) -> PresetOut:
        return cls(
            id=preset.id,
            label=preset.label,
            shape=preset.shape.value,
            mask_svg=preset.mask_svg,
            aspect_ratio={bp.value: ratio for bp, ratio in preset.aspect_ratio.items()},
            safe_area=preset.safe_area.model_dump(),
            min_resolution={
                bp.value: res.model_dump() for bp, res in preset.min_resolution.items()
            },
            max_zoom=preset.max_zoom,
            rotation=preset.rotation.model_dump(),
            breakpoints=[bp.value for bp in preset.breakpoints],
            output_variants=[v.model_dump() for v in preset.output_variants],
            storage_rules=preset.storage_rules.model_dump(),
            reference_ui=preset.reference_ui,
        )


class CropBoxIn(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class BreakpointCropIn(BaseModel):
    box: CropBoxIn
    zoom: float = Field(default=1.0, gt=0)
    pan: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    rotation: float = Field(default=0.0)


class FocusPointIn(BaseModel):
    x: float = Field(ge=0, le=1, default=0.5)
    y: float = Field(ge=0, le=1, default=0.5)


class CropGeometryIn(BaseModel):
    """Body for PATCH /admin/media/{image_id}/crop."""

    crops: dict[Breakpoint, BreakpointCropIn]
    focus_point: FocusPointIn = Field(default_factory=FocusPointIn)


class AttachIn(BaseModel):
    owner_type: str
    owner_id: uuid.UUID


class ReorderItem(BaseModel):
    image_id: uuid.UUID
    sort_order: int


class ReorderIn(BaseModel):
    owner_type: str
    owner_id: uuid.UUID
    items: list[ReorderItem]


class ImageVariantOut(BaseModel):
    id: uuid.UUID
    breakpoint: str
    variant_name: str
    dpr: int
    format: str
    url: str
    width: int
    height: int
    status: str
    error_message: str | None

    model_config = {"from_attributes": True}


class ImageOut(BaseModel):
    id: uuid.UUID
    module: str
    preset_id: str
    owner_type: str
    owner_id: uuid.UUID | None
    original_ext: str
    original_width: int
    original_height: int
    alt_text: str | None
    status: str
    version: int
    sort_order: int
    is_primary: bool
    metadata: dict[str, Any]
    variants: list[ImageVariantOut]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_image(cls, image: Any) -> ImageOut:
        """
        Build from an app.modules.media.models.Image ORM instance. Avoids
        Pydantic's from_attributes on the `metadata` field, whose ORM
        attribute is named `metadata_` (SQLAlchemy reserves `metadata` on
        declarative models) — explicit construction sidesteps alias/
        populate_by_name edge cases entirely.
        """
        return cls(
            id=image.id,
            module=image.module,
            preset_id=image.preset_id,
            owner_type=image.owner_type,
            owner_id=image.owner_id,
            original_ext=image.original_ext,
            original_width=image.original_width,
            original_height=image.original_height,
            alt_text=image.alt_text,
            status=image.status,
            version=image.version,
            sort_order=image.sort_order,
            is_primary=image.is_primary,
            metadata=image.metadata_,
            variants=[
                ImageVariantOut(
                    id=v.id,
                    breakpoint=v.breakpoint,
                    variant_name=v.variant_name,
                    dpr=v.dpr,
                    format=v.format,
                    url=f"{v.url}?v={image.version}",
                    width=v.width,
                    height=v.height,
                    status=v.status,
                    error_message=v.error_message,
                )
                for v in image.variants
            ],
            created_at=image.created_at,
            updated_at=image.updated_at,
        )
