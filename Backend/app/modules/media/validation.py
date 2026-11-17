"""
Single validation policy for every image upload, driven entirely by the
uploading preset's storage_rules/min_resolution — no per-module validation
logic anywhere else (closes Audit G3: three previously-inconsistent
validation regimes across MediaService/CmsMediaService/reviews).

See docs/architecture/Universal_Responsive_Image_System_Design.md §5, §6.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

import defusedxml.ElementTree as SafeET
from defusedxml import DefusedXmlException
from PIL import Image

from app.modules.media.preset_registry import Breakpoint, CropPreset

# Hard ceiling on decoded pixels (width x height). A tiny, highly compressible
# PNG/WebP can declare tens of thousands of pixels per side and expand to
# gigabytes in RAM when decoded; reject on the header before any decode. Also
# applied process-wide so Pillow's own decompression-bomb guard trips at this
# limit (it raises at 2x MAX_IMAGE_PIXELS) rather than at its much higher default.
MAX_IMAGE_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ImageValidationError(ValueError):
    """``str(exc)`` is the detailed message staff see in the admin;
    ``customer_message`` says the same in plain words for shoppers."""

    def __init__(self, message: str, *, customer_message: str) -> None:
        super().__init__(message)
        self.customer_message = customer_message


_UNREADABLE_PHOTO = (
    "We couldn't read this photo. Please choose a JPG, PNG or WebP image."
)


_TYPE_NAMES = {"jpeg": "JPG", "png": "PNG", "webp": "WebP", "svg": "SVG"}


def _readable_types(mime_types: list[str]) -> str:
    """["image/jpeg", "image/png", "image/webp"] -> "JPG, PNG or WebP"."""
    names = [
        _TYPE_NAMES.get(sub, sub.upper())
        for sub in (m.split("/")[-1].split("+")[0] for m in mime_types)
    ]
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} or {names[-1]}"


# Elements/attributes an uploaded SVG could use to run script in whatever
# origin it's later served from (the R2 public domain) — stripped before the
# file is ever written to storage. Presentation elements (rect/path/use/...)
# are untouched. See docs audit MP-8.
_SVG_DANGEROUS_TAGS = {"script", "foreignObject", "iframe", "embed", "object"}
_SVG_DANGEROUS_URI_SCHEMES = ("javascript:", "data:text/html", "vbscript:")
_SVG_HREF_ATTRS = {"href", "{http://www.w3.org/1999/xlink}href"}


def sanitize_svg(file_bytes: bytes) -> bytes:
    """Parse with defusedxml (guards against XXE/entity-expansion on
    untrusted input), strip script-capable elements/attributes, and
    re-serialize. Raises ImageValidationError if the file isn't parseable
    XML at all."""
    try:
        root = SafeET.fromstring(file_bytes)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ImageValidationError(
            f"File is not a valid SVG: {exc}",
            customer_message="We couldn't read this SVG file. Please choose another.",
        ) from exc

    parent_map = {child: parent for parent in root.iter() for child in parent}
    for el in list(root.iter()):
        local_tag = el.tag.rsplit("}", 1)[-1]
        if local_tag in _SVG_DANGEROUS_TAGS:
            parent = parent_map.get(el)
            if parent is not None:
                parent.remove(el)
            continue
        for attr, value in list(el.attrib.items()):
            local_attr = attr.rsplit("}", 1)[-1]
            if local_attr.lower().startswith("on"):
                del el.attrib[attr]
            elif attr in _SVG_HREF_ATTRS and value.strip().lower().startswith(
                _SVG_DANGEROUS_URI_SCHEMES
            ):
                del el.attrib[attr]

    # Re-serialize with the stdlib module — safe here because we're writing
    # bytes we just parsed and cleaned ourselves, not parsing untrusted
    # input (the XXE risk defusedxml guards against is parse-time only).
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def assert_pixel_budget(file_bytes: bytes) -> None:
    """Header-only check: raises ImageValidationError if the image would decode
    to more than MAX_IMAGE_PIXELS pixels. Does not decode pixel data."""
    try:
        with Image.open(io.BytesIO(file_bytes)) as probe:
            width, height = probe.size
    except Exception as exc:  # unreadable / decompression bomb header
        raise ImageValidationError(
            f"File is not a valid image: {exc}", customer_message=_UNREADABLE_PHOTO
        ) from exc
    if width * height > MAX_IMAGE_PIXELS:
        raise ImageValidationError(
            f"Image is {width}x{height} ({width * height / 1e6:.0f} MP), "
            f"exceeds the {MAX_IMAGE_PIXELS // 1_000_000} MP limit",
            customer_message=(
                "This photo's resolution is too high. Please choose a smaller one."
            ),
        )


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
            f"for {preset.label}",
            customer_message=(
                f"This photo is larger than {rules.max_file_mb} MB. "
                "Please choose a smaller one."
            ),
        )

    if content_type not in rules.allowed_mime:
        raise ImageValidationError(
            f"File type {content_type!r} is not allowed for {preset.label}; "
            f"allowed types: {', '.join(rules.allowed_mime)}",
            customer_message=(
                "This file type isn't supported. Please choose a "
                f"{_readable_types(rules.allowed_mime)} image."
            ),
        )

    if content_type == "image/svg+xml":
        # SVGs have no raster dimensions to validate against min_resolution.
        return

    assert_pixel_budget(file_bytes)

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
    except Exception as exc:
        raise ImageValidationError(
            f"File is not a valid image: {exc}", customer_message=_UNREADABLE_PHOTO
        ) from exc

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
            f"{smallest_min[0]}x{smallest_min[1]} required for {preset.label}",
            customer_message=(
                "This photo is too small. Please choose one at least "
                f"{smallest_min[0]}x{smallest_min[1]} pixels."
            ),
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
    "sanitize_svg",
    "Breakpoint",
]
