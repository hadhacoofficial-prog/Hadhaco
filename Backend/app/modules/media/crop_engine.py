"""
Universal Crop Engine — pure geometry/transform functions shared by every
image module. No I/O (no R2, no DB) lives here; callers (variant_generator.py,
service.py) own persistence.

See docs/architecture/Universal_Responsive_Image_System_Design.md §4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image

from app.modules.media.preset_registry import CropPreset, RotationMode, ShapeType


@dataclass(frozen=True)
class CropBox:
    x: float
    y: float
    width: float
    height: float


class CropGeometryError(ValueError):
    """Raised when a crop box doesn't fit the source image and the preset's
    storage_rules.strict_bounds requires a hard rejection rather than a clamp."""


def default_crop_box(
    image_width: int, image_height: int, aspect_ratio: float | None
) -> CropBox:
    """
    A centered crop box for *aspect_ratio* (None = the full image, used for
    free-form/CONTAIN-shaped presets) — the server-side counterpart of
    shared-media's cropMath.ts defaultCropBox, used to seed the default
    variants generated immediately on upload, before an admin manually crops.
    """
    if aspect_ratio is None:
        return CropBox(x=0, y=0, width=image_width, height=image_height)

    image_ratio = image_width / image_height
    if image_ratio > aspect_ratio:
        height = float(image_height)
        width = height * aspect_ratio
    else:
        width = float(image_width)
        height = width / aspect_ratio

    return CropBox(
        x=(image_width - width) / 2,
        y=(image_height - height) / 2,
        width=width,
        height=height,
    )


def rotate(image: Image.Image, degrees: float) -> Image.Image:
    """
    Rotate *image* by *degrees* (clockwise, matching react-easy-crop's CSS-
    style rotation prop), expanding the canvas so no content is clipped.
    A degrees value of 0 is a no-op (returns *image* unchanged).
    """
    if not degrees:
        return image
    return image.rotate(
        -degrees,
        expand=True,
        fillcolor=(255, 255, 255) if image.mode == "RGB" else (255, 255, 255, 0),
        resample=Image.BICUBIC,  # type: ignore[attr-defined]
    )


def validate_and_clamp_crop_box(
    box: CropBox, image_width: float, image_height: float, *, strict_bounds: bool
) -> CropBox:
    """
    Recompute *box* against the real pixel bounds of the (already rotated)
    source image.

    If the box fits, it is returned unchanged. If it doesn't:
    - strict_bounds=True  -> raise CropGeometryError (caller returns 422)
    - strict_bounds=False -> clamp to the image bounds and return the result
    """
    left = box.x
    top = box.y
    right = box.x + box.width
    bottom = box.y + box.height

    fits = left >= 0 and top >= 0 and right <= image_width and bottom <= image_height
    if fits:
        return box

    if strict_bounds:
        raise CropGeometryError(
            f"Crop box {box} exceeds source image bounds "
            f"({image_width}x{image_height})"
        )

    clamped_left = max(0.0, min(left, image_width))
    clamped_top = max(0.0, min(top, image_height))
    clamped_right = max(0.0, min(right, image_width))
    clamped_bottom = max(0.0, min(bottom, image_height))
    return CropBox(
        x=clamped_left,
        y=clamped_top,
        width=max(0.0, clamped_right - clamped_left),
        height=max(0.0, clamped_bottom - clamped_top),
    )


def _rotated_bounds(width: int, height: int, degrees: float) -> tuple[float, float]:
    """Analytic axis-aligned bounding box size after a `rotate(expand=True)`
    — mirrors PIL's own sizing for that operation without needing the
    actual pixel data, so callers can validate geometry using only stored
    width/height (see validate_crop_request)."""
    if not degrees:
        return float(width), float(height)
    rad = math.radians(degrees)
    return (
        abs(width * math.cos(rad)) + abs(height * math.sin(rad)),
        abs(width * math.sin(rad)) + abs(height * math.cos(rad)),
    )


def validate_crop_request(
    preset: CropPreset,
    original_width: int,
    original_height: int,
    box: CropBox,
    rotation_degrees: float,
) -> None:
    """
    Lightweight, request-time-safe validation of one breakpoint's crop
    geometry against the original's *stored* dimensions — no image bytes
    needed. Raises CropGeometryError for the same conditions
    `apply_geometry` would eventually hit when the background worker
    actually generates the variants (docs audit CB-1 Phase 2 moved that
    work off the request), so a bad crop request still gets an immediate
    422 (docs audit HP-3) instead of only failing minutes later in the
    worker with no request left to report it to. Only strict_bounds is
    enforced here; non-strict presets clamp silently in the worker, same
    as before this call existed.
    """
    if preset.rotation.allowed == RotationMode.NONE and rotation_degrees:
        raise CropGeometryError(f"Preset {preset.id!r} does not allow rotation")
    if not preset.storage_rules.strict_bounds:
        return
    rotated_width, rotated_height = _rotated_bounds(
        original_width, original_height, rotation_degrees
    )
    validate_and_clamp_crop_box(box, rotated_width, rotated_height, strict_bounds=True)


def crop_to_box(image: Image.Image, box: CropBox) -> Image.Image:
    """Crop *image* to *box*, in the image's own pixel coordinate space."""
    left = max(0, round(box.x))
    top = max(0, round(box.y))
    right = min(image.width, round(box.x + box.width))
    bottom = min(image.height, round(box.y + box.height))
    if right <= left or bottom <= top:
        return image
    return image.crop((left, top, right, bottom))


def apply_shape_mask(
    image: Image.Image, shape: ShapeType, mask_svg: str | None = None
) -> Image.Image:
    """
    Apply *shape*'s mask to *image*.

    CIRCLE/ROUNDED_RECT/CUSTOM_MASK add an alpha channel carrying the mask.
    RECTANGLE/SQUARE/CONTAIN/COVER apply no geometric mask — the source's
    own mode (and any existing alpha, e.g. a logo PNG with a transparent
    background) is preserved as-is. Whether that alpha survives into a given
    output *variant* is a per-variant encoding decision (variant_generator.py
    flattens onto white for WebP photography variants but keeps alpha for
    PNG variants), not a shape decision.
    """
    if shape in (
        ShapeType.RECTANGLE,
        ShapeType.SQUARE,
        ShapeType.CONTAIN,
        ShapeType.COVER,
    ):
        if image.mode == "P":
            return image.convert("RGBA" if "transparency" in image.info else "RGB")
        if image.mode not in ("RGB", "RGBA"):
            return image.convert("RGB")
        return image

    if shape == ShapeType.CIRCLE:
        return _apply_ellipse_mask(image)

    if shape == ShapeType.ROUNDED_RECT:
        return _apply_rounded_rect_mask(image, radius_ratio=0.08)

    if shape == ShapeType.CUSTOM_MASK:
        raise NotImplementedError(
            "CUSTOM_MASK shapes require mask_svg rendering, not yet implemented"
        )

    raise ValueError(f"Unknown shape: {shape}")  # pragma: no cover


def _apply_ellipse_mask(image: Image.Image) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, image.width, image.height), fill=255)

    rgba = image.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def _apply_rounded_rect_mask(image: Image.Image, *, radius_ratio: float) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    from PIL import ImageDraw

    radius = round(min(image.width, image.height) * radius_ratio)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, image.width, image.height), radius=radius, fill=255)

    rgba = image.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def apply_geometry(
    image: Image.Image,
    box: CropBox,
    *,
    rotation_degrees: float,
    preset: CropPreset,
) -> Image.Image:
    """
    Full per-breakpoint transform pipeline stages 2-4 of the architecture
    doc's §4 crop engine: rotate -> validate/clamp -> shape mask -> crop.

    *image* must be the untouched original (or a copy of it) — callers are
    responsible for never passing an already-derived variant here.
    """
    if preset.rotation.allowed == RotationMode.NONE and rotation_degrees:
        raise CropGeometryError(f"Preset {preset.id!r} does not allow rotation")

    rotated = rotate(image, rotation_degrees)
    validated_box = validate_and_clamp_crop_box(
        box,
        rotated.width,
        rotated.height,
        strict_bounds=preset.storage_rules.strict_bounds,
    )
    cropped = crop_to_box(rotated, validated_box)
    return apply_shape_mask(cropped, preset.shape, preset.mask_svg)
