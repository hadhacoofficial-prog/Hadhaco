"""
Variant Generator — turns one shape-masked, per-breakpoint cropped image into
the concrete WebP (or, for the two logo presets' `print` variant, PNG) files
a CropPreset's output_variants describe.

WebP q85 is the single canonical format for photography-style variants
(architecture doc §8) — there is no per-preset format flag. The only
exception is `footer_logo`/`company_logo`'s `print` VariantSpec, which is
explicitly `format="png"` in the preset itself so PDF embedding
(fulfillment/service.py) gets a transparency-preserving raster.

No I/O lives here — this module returns bytes; storage.py owns the R2 put.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from app.modules.media.preset_registry import Breakpoint, VariantSpec

WEBP_QUALITY = 85


@dataclass(frozen=True)
class GeneratedVariant:
    variant_name: str
    breakpoint: Breakpoint
    dpr: int
    format: str
    width: int
    height: int
    content: bytes


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        src = image.convert("RGBA") if image.mode == "P" else image
        background.paste(src, mask=src.split()[3] if src.mode == "RGBA" else None)
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _resize(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """
    Resize *image* to fit within (target_width, target_height).

    If target_height is 0 (used by CONTAIN-mode presets like logos, whose
    output is proportional rather than a fixed box), the image is scaled to
    target_width preserving its own aspect ratio.
    """
    if target_height == 0:
        ratio = target_width / image.width
        size = (target_width, max(1, round(image.height * ratio)))
    else:
        size = (target_width, target_height)

    resized = image.copy()
    resized.thumbnail(size, Image.LANCZOS)  # type: ignore[attr-defined]
    return resized


def _encode(image: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "webp":
        image = _flatten_to_rgb(image) if image.mode not in ("RGB", "RGBA") else image
        image.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
    elif fmt == "png":
        image.save(buf, format="PNG")
    else:
        raise ValueError(f"Unsupported variant format: {fmt!r}")
    return buf.getvalue()


def generate_variant(
    cropped_image: Image.Image,
    spec: VariantSpec,
    breakpoint: Breakpoint,
    dpr: int,
) -> GeneratedVariant:
    """Generate a single (breakpoint, variant_name, dpr) artifact."""
    fmt = spec.format
    # WebP variants are photography-style and should never carry transparency
    # through to the final file even if the shape mask preserved it upstream
    # (e.g. a CONTAIN-mode review photo that happened to have an alpha
    # channel); PNG variants (currently only the logo `print` variant) keep it.
    source = _flatten_to_rgb(cropped_image) if fmt == "webp" else cropped_image
    resized = _resize(source, spec.width, spec.height)
    content = _encode(resized, fmt)
    return GeneratedVariant(
        variant_name=spec.name,
        breakpoint=breakpoint,
        dpr=dpr,
        format=fmt,
        width=resized.width,
        height=resized.height,
        content=content,
    )


def generate_variants_for_breakpoint(
    cropped_image: Image.Image,
    specs: list[VariantSpec],
    breakpoint: Breakpoint,
) -> list[GeneratedVariant]:
    """
    Generate every (variant_name x dpr) artifact defined for one breakpoint's
    already-cropped, shape-masked image.
    """
    results: list[GeneratedVariant] = []
    for spec in specs:
        for dpr in spec.dprs:
            dpr_spec = VariantSpec(
                name=spec.name,
                width=spec.width * dpr,
                height=spec.height * dpr,
                dprs=spec.dprs,
                format=spec.format,
            )
            results.append(generate_variant(cropped_image, dpr_spec, breakpoint, dpr))
    return results
