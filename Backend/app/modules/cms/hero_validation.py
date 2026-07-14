"""
Hero Carousel – Server-side validation, normalization & legacy migration.

This module mirrors the frontend types (shared-types/src/cms.ts +
hero-mappings.ts) to provide server-side guarantees before persisting
hero carousel configs.  It deliberately re-validates the same rules the
frontend enforces so that any client (admin panel, script, API consumer)
is subject to the same constraints.

Design constraints:
    • No new tables, no migrations, no new APIs.
    • Reuses the existing JSONB passthrough – config is validated and
      normalised *before* ``db.commit()`` but the DB schema is unchanged.
    • Schema_version is injected into the config dict; old configs without
      it are treated as version 1 (legacy).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ─── Schema version ──────────────────────────────────────────────────────────
CURRENT_HERO_SCHEMA_VERSION = 2

# ─── Literal union types (mirror frontend HeroPaletteName, etc.) ─────────────

HeroPaletteName = Literal["navy", "gold", "white", "dark", "silver", "custom"]
HeroFontFamily = Literal["display", "serif", "sans"]
HeroFontSize = Literal["small", "medium", "large", "xl", "hero"]
HeroFontWeight = Literal["regular", "medium", "semibold", "bold"]
HeroDescriptionSize = Literal["small", "medium", "large"]
HeroLayoutPreset = Literal[
    "classic-left",
    "centered-luxury",
    "editorial",
    "minimal",
    "image-focused",
    "split",
]
HeroHeightPreset = Literal["compact", "medium", "large", "fullscreen"]
HeroButtonStyle = Literal["filled", "outline", "ghost", "text"]
HeroTransition = Literal["fade", "slide"]
HeroTransitionSpeed = Literal["fast", "normal", "slow"]
HeroGradientDirection = Literal["left", "right"]
HeroAlignment = Literal["left", "center", "right"]
HeroVertical = Literal["top", "center", "bottom"]
HeroContentWidth = Literal["narrow", "wide"]
HeroPadding = Literal["compact", "standard", "generous"]

_HEX_RE = re.compile(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")

# ─── Nested slide models ────────────────────────────────────────────────────


class HeroSlideMedia(BaseModel):
    desktop_image_url: str = ""
    tablet_image_url: str | None = None
    mobile_image_url: str | None = None
    image_bundle: Any = None
    video_url: str | None = None
    video_poster_url: str | None = None


class HeroSlideContent(BaseModel):
    eyebrow: str | None = None
    headline: str = ""
    subheading: str | None = None
    primary_btn_text: str | None = None
    primary_btn_url: str | None = None
    secondary_btn_text: str | None = None
    secondary_btn_url: str | None = None
    seo_alt: str | None = None

    @field_validator("headline")
    @classmethod
    def _strip_headline(cls, v: str) -> str:
        return v.strip()


class HeroSlideTypography(BaseModel):
    headline_font: HeroFontFamily | None = None
    headline_size: HeroFontSize | None = None
    headline_weight: HeroFontWeight | None = None
    description_size: HeroDescriptionSize | None = None
    text_shadow: bool | None = None


class HeroSlideColors(BaseModel):
    text: HeroPaletteName | None = None
    text_custom: str | None = None
    eyebrow: HeroPaletteName | None = None
    eyebrow_custom: str | None = None
    background: HeroPaletteName | None = None
    background_custom: str | None = None
    overlay_color: HeroPaletteName | None = None
    overlay_color_custom: str | None = None
    overlay_opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    gradient: bool | None = None
    gradient_direction: HeroGradientDirection | None = None

    @field_validator(
        "text_custom",
        "eyebrow_custom",
        "background_custom",
        "overlay_color_custom",
    )
    @classmethod
    def _validate_hex(cls, v: str | None) -> str | None:
        if v is not None and v.strip() and not _HEX_RE.match(v.strip()):
            raise ValueError(f"Invalid HEX color: {v!r}")
        return v.strip() if v else None


class HeroSlideLayoutAdvanced(BaseModel):
    alignment: HeroAlignment | None = None
    vertical: HeroVertical | None = None
    content_width: HeroContentWidth | None = None
    padding: HeroPadding | None = None


class HeroSlideLayout(BaseModel):
    preset: HeroLayoutPreset | None = None
    advanced: HeroSlideLayoutAdvanced | None = None


class HeroSlideButtons(BaseModel):
    primary_style: HeroButtonStyle | None = None
    primary_color: HeroPaletteName | None = None
    primary_color_custom: str | None = None
    secondary_style: HeroButtonStyle | None = None
    secondary_color: HeroPaletteName | None = None
    secondary_color_custom: str | None = None

    @field_validator("primary_color_custom", "secondary_color_custom")
    @classmethod
    def _validate_btn_hex(cls, v: str | None) -> str | None:
        if v is not None and v.strip() and not _HEX_RE.match(v.strip()):
            raise ValueError(f"Invalid HEX color: {v!r}")
        return v.strip() if v else None


class HeroSlideConfig(BaseModel):
    media: HeroSlideMedia = Field(default_factory=HeroSlideMedia)
    content: HeroSlideContent = Field(default_factory=HeroSlideContent)
    typography: HeroSlideTypography = Field(default_factory=HeroSlideTypography)
    colors: HeroSlideColors = Field(default_factory=HeroSlideColors)
    layout: HeroSlideLayout = Field(default_factory=HeroSlideLayout)
    buttons: HeroSlideButtons = Field(default_factory=HeroSlideButtons)


class HeroCarouselConfig(BaseModel):
    auto_rotate: bool = True
    rotation_speed: int = Field(default=6, ge=1, le=30)
    transition: HeroTransition | None = None
    transition_duration: HeroTransitionSpeed | None = None
    height: HeroHeightPreset | None = None
    pause_on_hover: bool | None = None
    schema_version: int = Field(default=CURRENT_HERO_SCHEMA_VERSION, ge=1)


# ─── Validation result types ────────────────────────────────────────────────


class HeroValidationError(BaseModel):
    type: Literal["error"] = "error"
    field: str
    message: str
    slide_index: int | None = None


class HeroValidationWarning(BaseModel):
    type: Literal["warning"] = "warning"
    field: str
    message: str
    slide_index: int | None = None


class HeroValidationResult(BaseModel):
    errors: list[HeroValidationError] = Field(default_factory=list)
    warnings: list[HeroValidationWarning] = Field(default_factory=list)


# ─── Legacy migration ───────────────────────────────────────────────────────


def _is_legacy_slide(config: dict[str, Any]) -> bool:
    """Flat keys like ``headline`` or ``desktop_image_url`` signal legacy."""
    return "headline" in config or "desktop_image_url" in config


def _is_legacy_section(config: dict[str, Any]) -> bool:
    """Missing ``transition`` or ``height`` at top-level signals legacy."""
    return "transition" not in config and "height" not in config


def _legacy_alignment_to_preset(alignment: str | None) -> HeroLayoutPreset:
    mapping: dict[str, HeroLayoutPreset] = {
        "center": "centered-luxury",
        "right": "split",
    }
    return mapping.get(alignment or "", "classic-left")


def migrate_legacy_slide(config: dict[str, Any]) -> dict[str, Any]:
    """Convert a flat/legacy slide config to the new grouped format."""
    if not _is_legacy_slide(config):
        return config

    return {
        "media": {
            "desktop_image_url": config.get("desktop_image_url", ""),
            "tablet_image_url": config.get("tablet_image_url") or None,
            "mobile_image_url": config.get("mobile_image_url") or None,
            "video_url": config.get("video_url") or None,
            "video_poster_url": config.get("video_poster_url") or None,
        },
        "content": {
            "eyebrow": config.get("eyebrow") or None,
            "headline": config.get("headline", ""),
            "subheading": config.get("subheading") or None,
            "primary_btn_text": config.get("primary_btn_text") or None,
            "primary_btn_url": config.get("primary_btn_url") or None,
            "secondary_btn_text": config.get("secondary_btn_text") or None,
            "secondary_btn_url": config.get("secondary_btn_url") or None,
            "seo_alt": config.get("seo_alt") or None,
        },
        "typography": {},
        "colors": {
            "overlay_opacity": config.get("overlay_opacity"),
        },
        "layout": {
            "preset": _legacy_alignment_to_preset(config.get("alignment")),
        },
        "buttons": {},
    }


def migrate_legacy_section(config: dict[str, Any]) -> dict[str, Any]:
    """Convert a legacy section-level config to the new grouped format."""
    if not _is_legacy_section(config):
        return config

    return {
        "auto_rotate": config.get("auto_rotate", True),
        "rotation_speed": config.get("rotation_speed", 6),
    }


# ─── Normalization ──────────────────────────────────────────────────────────


def _strip_or_none(v: str | None) -> str | None:
    if v is None:
        return None
    stripped = v.strip()
    return stripped or None


def normalize_slide(config: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single slide config in-place:
    • strip whitespace on strings
    • remove empty strings → None
    • coerce overlay_opacity into [0, 1]
    • ensure media.desktop_image_url is a non-empty string
    """
    media = config.get("media", {})
    content = config.get("content", {})
    colors = config.get("colors", {})

    # Media
    media["desktop_image_url"] = (media.get("desktop_image_url") or "").strip()
    media["tablet_image_url"] = _strip_or_none(media.get("tablet_image_url"))
    media["mobile_image_url"] = _strip_or_none(media.get("mobile_image_url"))
    media["video_url"] = _strip_or_none(media.get("video_url"))
    media["video_poster_url"] = _strip_or_none(media.get("video_poster_url"))

    # Content – strip all string fields
    for key in (
        "eyebrow",
        "headline",
        "subheading",
        "primary_btn_text",
        "primary_btn_url",
        "secondary_btn_text",
        "secondary_btn_url",
        "seo_alt",
    ):
        content[key] = (
            _strip_or_none(content.get(key))
            if key != "headline"
            else (content.get(key) or "").strip()
        )

    # Colors – coerce overlay_opacity
    if "overlay_opacity" in colors and colors["overlay_opacity"] is not None:
        try:
            opacity = float(colors["overlay_opacity"])
            colors["overlay_opacity"] = max(0.0, min(1.0, opacity))
        except (TypeError, ValueError):
            colors["overlay_opacity"] = 0.5

    # Colors – strip custom hex
    for key in (
        "text_custom",
        "eyebrow_custom",
        "background_custom",
        "overlay_color_custom",
    ):
        colors[key] = _strip_or_none(colors.get(key))

    # Buttons – strip custom hex
    buttons = config.get("buttons", {})
    for key in ("primary_color_custom", "secondary_color_custom"):
        buttons[key] = _strip_or_none(buttons.get(key))

    return config


def normalize_section_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalise the section-level hero_carousel config."""
    config.setdefault("auto_rotate", True)
    config.setdefault("rotation_speed", 6)

    # Clamp rotation_speed
    try:
        config["rotation_speed"] = max(1, min(30, int(config["rotation_speed"])))
    except (TypeError, ValueError):
        config["rotation_speed"] = 6

    config.setdefault("transition", "fade")
    config.setdefault("transition_duration", "normal")
    config.setdefault("height", "large")
    config.setdefault("pause_on_hover", True)
    config["schema_version"] = CURRENT_HERO_SCHEMA_VERSION

    return config


# ─── Validation ─────────────────────────────────────────────────────────────


def validate_hero_slide(
    slide: dict[str, Any], index: int
) -> tuple[list[HeroValidationError], list[HeroValidationWarning]]:
    """Validate a single slide; return (errors, warnings)."""
    errors: list[HeroValidationError] = []
    warnings: list[HeroValidationWarning] = []

    content = slide.get("content", {})
    media = slide.get("media", {})
    colors = slide.get("colors", {})
    buttons = slide.get("buttons", {})

    # ── Errors (blocking) ────────────────────────────────────────────────
    headline = content.get("headline", "")
    if not headline or not headline.strip():
        errors.append(
            HeroValidationError(
                field="content.headline",
                message=f"Slide {index + 1}: Headline is required.",
                slide_index=index,
            )
        )

    has_image = bool((media.get("desktop_image_url") or "").strip())
    has_video = bool((media.get("video_url") or "").strip())
    if not has_image and not has_video:
        errors.append(
            HeroValidationError(
                field="media",
                message=f"Slide {index + 1}: An image or video is required.",
                slide_index=index,
            )
        )

    btn_text = content.get("primary_btn_text")
    btn_url = content.get("primary_btn_url")
    if btn_text and not btn_url:
        errors.append(
            HeroValidationError(
                field="content.primary_btn_url",
                message=(
                    f"Slide {index + 1}: Primary button URL is required "
                    "when button text is provided."
                ),
                slide_index=index,
            )
        )
    if btn_url and not btn_text:
        errors.append(
            HeroValidationError(
                field="content.primary_btn_text",
                message=(
                    f"Slide {index + 1}: Primary button text is required "
                    "when URL is provided."
                ),
                slide_index=index,
            )
        )

    sec_text = content.get("secondary_btn_text")
    sec_url = content.get("secondary_btn_url")
    if sec_text and not sec_url:
        errors.append(
            HeroValidationError(
                field="content.secondary_btn_url",
                message=(
                    f"Slide {index + 1}: Secondary button URL is required "
                    "when button text is provided."
                ),
                slide_index=index,
            )
        )

    # ── Warnings (non-blocking) ──────────────────────────────────────────
    if not content.get("seo_alt"):
        warnings.append(
            HeroValidationWarning(
                field="content.seo_alt",
                message=f"Slide {index + 1}: Missing SEO alt text.",
                slide_index=index,
            )
        )

    if media.get("desktop_image_url") and not media.get("mobile_image_url"):
        warnings.append(
            HeroValidationWarning(
                field="media.mobile_image_url",
                message=(
                    f"Slide {index + 1}: No mobile image set. "
                    "Desktop image will be used."
                ),
                slide_index=index,
            )
        )

    if media.get("video_url") and not media.get("video_poster_url"):
        warnings.append(
            HeroValidationWarning(
                field="media.video_poster_url",
                message=f"Slide {index + 1}: Video has no poster image.",
                slide_index=index,
            )
        )

    # Validate custom hex colors
    for field_name, label in (
        ("text_custom", "Text"),
        ("eyebrow_custom", "Eyebrow"),
        ("background_custom", "Background"),
        ("overlay_color_custom", "Overlay"),
    ):
        palette_key = field_name.replace("_custom", "")
        if colors.get(palette_key) == "custom":
            hex_val = colors.get(field_name)
            if not hex_val or not _HEX_RE.match(hex_val.strip()):
                errors.append(
                    HeroValidationError(
                        field=f"colors.{field_name}",
                        message=(
                            f"Slide {index + 1}: {label} color is set to "
                            "'custom' but no valid HEX color is provided."
                        ),
                        slide_index=index,
                    )
                )

    for field_name, label in (
        ("primary_color_custom", "Primary button"),
        ("secondary_color_custom", "Secondary button"),
    ):
        palette_key = field_name.replace("_custom", "")
        if buttons.get(palette_key) == "custom":
            hex_val = buttons.get(field_name)
            if not hex_val or not _HEX_RE.match(hex_val.strip()):
                errors.append(
                    HeroValidationError(
                        field=f"buttons.{field_name}",
                        message=(
                            f"Slide {index + 1}: {label} color is set to "
                            "'custom' but no valid HEX color is provided."
                        ),
                        slide_index=index,
                    )
                )

    # Overlay opacity range
    opacity = colors.get("overlay_opacity")
    if opacity is not None:
        try:
            v = float(opacity)
            if v < 0.0 or v > 1.0:
                errors.append(
                    HeroValidationError(
                        field="colors.overlay_opacity",
                        message=(
                            f"Slide {index + 1}: Overlay opacity must be "
                            f"between 0 and 1, got {v}."
                        ),
                        slide_index=index,
                    )
                )
        except (TypeError, ValueError):
            errors.append(
                HeroValidationError(
                    field="colors.overlay_opacity",
                    message=f"Slide {index + 1}: Invalid overlay opacity value.",
                    slide_index=index,
                )
            )

    return errors, warnings


def validate_hero_config(
    items: list[dict[str, Any]],
    section_config: dict[str, Any],
) -> HeroValidationResult:
    """Full validation of hero carousel config.

    Called by the service layer before persisting drafts or publishing.

    Parameters
    ----------
    items:
        List of slide configs (``cms_section_items.config`` JSONB dicts).
    section_config:
        The section-level config (``landing_sections.draft_config`` or
        ``config`` JSONB).

    Returns
    -------
    HeroValidationResult
        ``errors`` blocks publish; ``warnings`` are advisory.
    """
    errors: list[HeroValidationError] = []
    warnings: list[HeroValidationWarning] = []

    if not items:
        errors.append(
            HeroValidationError(
                field="slides", message="At least one slide is required."
            )
        )
        return HeroValidationResult(errors=errors, warnings=warnings)

    # Validate section-level config
    if section_config.get("rotation_speed") is not None:
        try:
            rs = int(section_config["rotation_speed"])
            if rs < 1 or rs > 30:
                errors.append(
                    HeroValidationError(
                        field="rotation_speed",
                        message=f"Rotation speed must be between 1 and 30 seconds, got {rs}.",
                    )
                )
        except (TypeError, ValueError):
            errors.append(
                HeroValidationError(
                    field="rotation_speed",
                    message="Invalid rotation speed value.",
                )
            )

    # Validate each slide
    primary_urls: list[str] = []
    for i, item in enumerate(items):
        slide_errors, slide_warnings = validate_hero_slide(item, i)
        errors.extend(slide_errors)
        warnings.extend(slide_warnings)

        btn_url = item.get("content", {}).get("primary_btn_url", "")
        if btn_url:
            primary_urls.append(btn_url)

    # Duplicate CTA URL check
    if len(primary_urls) > 1:
        seen: set[str] = set()
        for url in primary_urls:
            if url in seen:
                warnings.append(
                    HeroValidationWarning(
                        field="content.primary_btn_url",
                        message=f'Duplicate CTA URL detected: "{url}"',
                    )
                )
            seen.add(url)

    return HeroValidationResult(errors=errors, warnings=warnings)


# ─── Public entry point ─────────────────────────────────────────────────────


def prepare_hero_draft(
    section_config: dict[str, Any],
    slide_configs: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Migrate → normalise → validate a hero carousel draft.

    Returns ``(normalised_section_config, normalised_slide_configs)``.
    Raises ``ValueError`` if validation errors are found.
    """
    section_config = migrate_legacy_section(section_config)
    section_config = normalize_section_config(section_config)

    normalised_slides: list[dict[str, Any]] = []
    for slide in slide_configs:
        slide = migrate_legacy_slide(slide)
        slide = normalize_slide(slide)
        normalised_slides.append(slide)

    result = validate_hero_config(normalised_slides, section_config)
    if result.errors:
        error_messages = [e.message for e in result.errors]
        raise ValueError(
            "Hero carousel validation failed: " + "; ".join(error_messages)
        )

    return section_config, normalised_slides
