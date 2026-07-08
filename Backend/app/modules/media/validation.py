"""
Single validation policy for every image upload, driven entirely by the
uploading preset's storage_rules/min_resolution — no per-module validation
logic anywhere else (closes Audit G3: three previously-inconsistent
validation regimes across MediaService/CmsMediaService/reviews).

See docs/architecture/Universal_Responsive_Image_System_Design.md §5, §6.
"""

from __future__ import annotations

import io

from PIL import Image

from app.modules.media.preset_registry import Breakpoint, CropPreset


class ImageValidationError(ValueError):
    pass


def validate_upload(
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    preset: CropPreset,
) -> None:
    """
    Validate a freshly-uploaded file against *preset*'s storage_rules and
    minimum resolution requirements. Raises ImageValidationError with a
    human-readable message on any failure; returns None on success.
    """
    rules = preset.storage_rules

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > rules.max_file_mb:
        raise ImageValidationError(
            f"File is {size_mb:.1f} MB, exceeds the {rules.max_file_mb} MB limit "
            f"for {preset.label}"
        )

    if content_type not in rules.allowed_mime:
        raise ImageValidationError(
            f"File type {content_type!r} is not allowed for {preset.label}; "
            f"allowed types: {', '.join(rules.allowed_mime)}"
        )

    if content_type == "image/svg+xml":
        # SVGs have no raster dimensions to validate against min_resolution.
        return

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
    except Exception as exc:
        raise ImageValidationError(f"File is not a valid image: {exc}") from exc

    # Re-open after verify() (which leaves the file object unusable for
    # further operations) to read dimensions.
    img = Image.open(io.BytesIO(file_bytes))
    width, height = img.size

    smallest_min = _smallest_min_resolution(preset)
    if smallest_min is not None and (
        width < smallest_min[0] or height < smallest_min[1]
    ):
        raise ImageValidationError(
            f"Image is {width}x{height}, below the minimum "
            f"{smallest_min[0]}x{smallest_min[1]} required for {preset.label}"
        )


def _smallest_min_resolution(preset: CropPreset) -> tuple[int, int] | None:
    """
    The smallest (width, height) floor across all of a preset's breakpoints
    — used as the upload-time gate (a stricter per-breakpoint check happens
    again inside crop_engine at crop time, once the actual crop box for each
    breakpoint is known).
    """
    resolutions = preset.min_resolution.values()
    if not resolutions:
        return None
    return (
        min(r.width for r in resolutions),
        min(r.height for r in resolutions),
    )


def resolve_extension(original_filename: str, content_type: str) -> str:
    if "." in original_filename:
        return original_filename.rsplit(".", 1)[-1].lower()
    _CONTENT_TYPE_EXT = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/svg+xml": "svg",
        "image/gif": "gif",
    }
    return _CONTENT_TYPE_EXT.get(content_type, "jpg")


__all__ = [
    "ImageValidationError",
    "validate_upload",
    "resolve_extension",
    "Breakpoint",
]
