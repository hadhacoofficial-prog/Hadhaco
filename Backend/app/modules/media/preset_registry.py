"""
Crop Preset Registry — single source of truth for every image module's
crop/shape/resolution/variant behavior.

See docs/architecture/Universal_Responsive_Image_System_Design.md §5-§6.
Adding a new module = adding one entry to PRESET_REGISTRY; no new crop code.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ShapeType(StrEnum):
    RECTANGLE = "rectangle"
    SQUARE = "square"
    CIRCLE = "circle"
    ROUNDED_RECT = "rounded_rect"
    CONTAIN = "contain"
    COVER = "cover"
    CUSTOM_MASK = "custom_mask"


class Breakpoint(StrEnum):
    DESKTOP = "desktop"
    TABLET = "tablet"
    MOBILE = "mobile"
    ALL = "all"


class RotationMode(StrEnum):
    NONE = "none"
    STEP_90 = "90_step"
    FREE = "free"


class Resolution(BaseModel):
    width: int
    height: int


class SafeArea(BaseModel):
    """Percentages (0-100) of the crop box reserved for overlay content."""

    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    left: float = 0.0


class RotationPolicy(BaseModel):
    allowed: RotationMode = RotationMode.NONE
    min_degrees: float = -180.0
    max_degrees: float = 180.0
    step_degrees: float = 1.0


class VariantSpec(BaseModel):
    name: str
    width: int
    height: int
    dprs: list[int] = Field(default_factory=lambda: [1])
    format: str = "webp"


class StorageRules(BaseModel):
    folder: str
    max_file_mb: int
    allowed_mime: list[str]
    strict_bounds: bool = False


class CropPreset(BaseModel):
    id: str
    label: str
    shape: ShapeType
    mask_svg: str | None = None
    aspect_ratio: dict[Breakpoint, float | None]
    safe_area: SafeArea = Field(default_factory=SafeArea)
    min_resolution: dict[Breakpoint, Resolution]
    max_zoom: float
    rotation: RotationPolicy = Field(default_factory=RotationPolicy)
    breakpoints: list[Breakpoint]
    output_variants: list[VariantSpec]
    storage_rules: StorageRules
    reference_ui: str


def _res(w: int, h: int) -> Resolution:
    return Resolution(width=w, height=h)


def _jpeg_png_webp(folder: str, max_mb: int, *, strict: bool = False) -> StorageRules:
    return StorageRules(
        folder=folder,
        max_file_mb=max_mb,
        allowed_mime=["image/jpeg", "image/png", "image/webp"],
        strict_bounds=strict,
    )


def _variants_1x2x(name: str, width: int, height: int) -> VariantSpec:
    return VariantSpec(name=name, width=width, height=height, dprs=[1, 2])


PRESET_REGISTRY: dict[str, CropPreset] = {
    "product": CropPreset(
        id="product",
        label="Product",
        shape=ShapeType.SQUARE,
        aspect_ratio={
            Breakpoint.DESKTOP: 1.0,
            Breakpoint.TABLET: 1.0,
            Breakpoint.MOBILE: 1.0,
        },
        min_resolution={
            Breakpoint.DESKTOP: _res(800, 800),
            Breakpoint.TABLET: _res(800, 800),
            Breakpoint.MOBILE: _res(800, 800),
        },
        max_zoom=5.0,
        rotation=RotationPolicy(allowed=RotationMode.FREE, step_degrees=1.0),
        breakpoints=[Breakpoint.DESKTOP, Breakpoint.TABLET, Breakpoint.MOBILE],
        output_variants=[
            _variants_1x2x("thumbnail", 200, 200),
            _variants_1x2x("medium", 600, 600),
            _variants_1x2x("large", 1200, 1200),
        ],
        storage_rules=_jpeg_png_webp("products/", 10, strict=True),
        reference_ui="product-card",
    ),
    "collection": CropPreset(
        id="collection",
        label="Collection",
        shape=ShapeType.SQUARE,
        aspect_ratio={Breakpoint.DESKTOP: 1.0, Breakpoint.MOBILE: 1.0},
        safe_area=SafeArea(bottom=20.0),
        min_resolution={
            Breakpoint.DESKTOP: _res(1200, 1200),
            Breakpoint.MOBILE: _res(600, 600),
        },
        max_zoom=4.0,
        breakpoints=[Breakpoint.DESKTOP, Breakpoint.MOBILE],
        output_variants=[
            VariantSpec(name="thumbnail", width=200, height=200),
            VariantSpec(name="medium", width=600, height=600),
            VariantSpec(name="large", width=1200, height=1200),
        ],
        storage_rules=_jpeg_png_webp("collections/", 10),
        reference_ui="collection-tile",
    ),
    "category": CropPreset(
        id="category",
        label="Category",
        shape=ShapeType.SQUARE,
        aspect_ratio={Breakpoint.DESKTOP: 1.0, Breakpoint.MOBILE: 1.0},
        safe_area=SafeArea(bottom=20.0),
        min_resolution={
            Breakpoint.DESKTOP: _res(1200, 1200),
            Breakpoint.MOBILE: _res(600, 600),
        },
        max_zoom=4.0,
        breakpoints=[Breakpoint.DESKTOP, Breakpoint.MOBILE],
        output_variants=[
            VariantSpec(name="thumbnail", width=200, height=200),
            VariantSpec(name="medium", width=600, height=600),
            VariantSpec(name="large", width=1200, height=1200),
        ],
        storage_rules=_jpeg_png_webp("categories/", 10),
        reference_ui="category-tile",
    ),
    # Split into two single-breakpoint presets rather than one combined
    # desktop+mobile preset — the CMS Hero Carousel editor uploads and crops
    # the desktop and mobile hero images as two entirely independent images
    # (often different source photos), each with its own upload button and
    # its own single-frame crop, not one image cropped two ways.
    "hero_desktop": CropPreset(
        id="hero_desktop",
        label="Hero — Desktop",
        shape=ShapeType.RECTANGLE,
        aspect_ratio={Breakpoint.DESKTOP: 1920 / 700},
        safe_area=SafeArea(left=45.0),
        min_resolution={Breakpoint.DESKTOP: _res(1920, 700)},
        max_zoom=3.0,
        breakpoints=[Breakpoint.DESKTOP],
        output_variants=[_variants_1x2x("hero-desktop", 1920, 700)],
        storage_rules=_jpeg_png_webp("hero/", 15, strict=True),
        reference_ui="hero-full-bleed",
    ),
    "hero_mobile": CropPreset(
        id="hero_mobile",
        label="Hero — Mobile",
        shape=ShapeType.RECTANGLE,
        aspect_ratio={Breakpoint.MOBILE: 390 / 600},
        min_resolution={Breakpoint.MOBILE: _res(390, 600)},
        max_zoom=3.0,
        breakpoints=[Breakpoint.MOBILE],
        output_variants=[_variants_1x2x("hero-mobile", 390, 600)],
        storage_rules=_jpeg_png_webp("hero/", 15, strict=True),
        reference_ui="hero-full-bleed",
    ),
    "promo_banner": CropPreset(
        id="promo_banner",
        label="Promo Banner",
        shape=ShapeType.RECTANGLE,
        aspect_ratio={Breakpoint.DESKTOP: 1920 / 720, Breakpoint.MOBILE: 750 / 1000},
        safe_area=SafeArea(right=40.0, bottom=25.0),
        min_resolution={
            Breakpoint.DESKTOP: _res(1920, 720),
            Breakpoint.MOBILE: _res(750, 1000),
        },
        max_zoom=3.0,
        breakpoints=[Breakpoint.DESKTOP, Breakpoint.MOBILE],
        output_variants=[
            _variants_1x2x("banner", 1920, 720),
        ],
        storage_rules=_jpeg_png_webp("banners/", 15),
        reference_ui="promo-banner",
    ),
    "gender_section": CropPreset(
        id="gender_section",
        label="Gender Section",
        shape=ShapeType.CIRCLE,
        aspect_ratio={Breakpoint.DESKTOP: 1.0, Breakpoint.MOBILE: 1.0},
        min_resolution={
            Breakpoint.DESKTOP: _res(600, 600),
            Breakpoint.MOBILE: _res(400, 400),
        },
        max_zoom=4.0,
        breakpoints=[Breakpoint.DESKTOP, Breakpoint.MOBILE],
        output_variants=[
            VariantSpec(name="thumb", width=200, height=200),
            VariantSpec(name="medium", width=500, height=500),
        ],
        storage_rules=_jpeg_png_webp("gender-section/", 8),
        reference_ui="gender-circle",
    ),
    "testimonial_avatar": CropPreset(
        id="testimonial_avatar",
        label="Testimonial Avatar",
        shape=ShapeType.CIRCLE,
        aspect_ratio={Breakpoint.ALL: 1.0},
        min_resolution={Breakpoint.ALL: _res(300, 300)},
        max_zoom=5.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[VariantSpec(name="avatar", width=200, height=200)],
        storage_rules=_jpeg_png_webp("testimonials/", 5),
        reference_ui="testimonial-avatar",
    ),
    "instagram_tile": CropPreset(
        id="instagram_tile",
        label="Instagram Gallery",
        shape=ShapeType.SQUARE,
        aspect_ratio={Breakpoint.DESKTOP: 1.0, Breakpoint.MOBILE: 1.0},
        min_resolution={
            Breakpoint.DESKTOP: _res(500, 500),
            Breakpoint.MOBILE: _res(500, 500),
        },
        max_zoom=3.0,
        breakpoints=[Breakpoint.DESKTOP, Breakpoint.MOBILE],
        output_variants=[
            VariantSpec(name="thumb", width=250, height=250),
            VariantSpec(name="medium", width=500, height=500),
        ],
        storage_rules=_jpeg_png_webp("instagram/", 10),
        reference_ui="instagram-tile",
    ),
    "footer_logo": CropPreset(
        id="footer_logo",
        label="Footer Logo",
        shape=ShapeType.CONTAIN,
        aspect_ratio={Breakpoint.ALL: None},
        safe_area=SafeArea(top=10.0, right=10.0, bottom=10.0, left=10.0),
        min_resolution={Breakpoint.ALL: _res(300, 100)},
        max_zoom=1.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[
            VariantSpec(name="web", width=400, height=0, format="webp"),
            VariantSpec(name="print", width=1200, height=0, format="png"),
        ],
        storage_rules=StorageRules(
            folder="branding/",
            max_file_mb=5,
            allowed_mime=["image/png", "image/svg+xml", "image/webp"],
        ),
        reference_ui="footer-logo",
    ),
    "company_logo": CropPreset(
        id="company_logo",
        label="Company Logo",
        shape=ShapeType.CONTAIN,
        aspect_ratio={Breakpoint.ALL: None},
        safe_area=SafeArea(top=10.0, right=10.0, bottom=10.0, left=10.0),
        min_resolution={Breakpoint.ALL: _res(300, 100)},
        max_zoom=1.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[
            VariantSpec(name="web", width=400, height=0, format="webp"),
            VariantSpec(name="print", width=1200, height=0, format="png"),
        ],
        storage_rules=StorageRules(
            folder="branding/",
            max_file_mb=5,
            allowed_mime=["image/png", "image/svg+xml", "image/webp"],
        ),
        reference_ui="company-logo",
    ),
    "seo_og": CropPreset(
        id="seo_og",
        label="SEO / OpenGraph Image",
        shape=ShapeType.RECTANGLE,
        aspect_ratio={Breakpoint.ALL: 1200 / 630},
        safe_area=SafeArea(top=8.0, right=8.0, bottom=8.0, left=8.0),
        min_resolution={Breakpoint.ALL: _res(1200, 630)},
        max_zoom=3.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[VariantSpec(name="og", width=1200, height=630)],
        storage_rules=_jpeg_png_webp("seo/", 5),
        reference_ui="seo-og",
    ),
    "avatar": CropPreset(
        id="avatar",
        label="Avatar",
        shape=ShapeType.CIRCLE,
        aspect_ratio={Breakpoint.ALL: 1.0},
        min_resolution={Breakpoint.ALL: _res(200, 200)},
        max_zoom=5.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[
            VariantSpec(name="avatar", width=400, height=400),
            VariantSpec(name="avatar-sm", width=100, height=100),
        ],
        storage_rules=_jpeg_png_webp("avatars/", 5),
        reference_ui="avatar",
    ),
    "review_photo": CropPreset(
        id="review_photo",
        label="Review Photo",
        shape=ShapeType.CONTAIN,
        aspect_ratio={Breakpoint.ALL: None},
        min_resolution={Breakpoint.ALL: _res(400, 300)},
        max_zoom=1.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[
            VariantSpec(name="thumb", width=150, height=150),
            VariantSpec(name="medium", width=600, height=450),
        ],
        storage_rules=_jpeg_png_webp("reviews/", 8),
        reference_ui="review-photo",
    ),
    "team_member": CropPreset(
        id="team_member",
        label="Team Member",
        shape=ShapeType.CIRCLE,
        aspect_ratio={Breakpoint.ALL: 1.0},
        min_resolution={Breakpoint.ALL: _res(400, 400)},
        max_zoom=4.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[VariantSpec(name="portrait", width=400, height=400)],
        storage_rules=_jpeg_png_webp("team/", 8),
        reference_ui="team-member",
    ),
    "blog_cover": CropPreset(
        id="blog_cover",
        label="Blog Cover",
        shape=ShapeType.RECTANGLE,
        aspect_ratio={Breakpoint.DESKTOP: 1600 / 900, Breakpoint.MOBILE: 750 / 900},
        min_resolution={
            Breakpoint.DESKTOP: _res(1600, 900),
            Breakpoint.MOBILE: _res(750, 900),
        },
        max_zoom=3.0,
        breakpoints=[Breakpoint.DESKTOP, Breakpoint.MOBILE],
        output_variants=[_variants_1x2x("cover", 1600, 900)],
        storage_rules=_jpeg_png_webp("blog/", 12),
        reference_ui="blog-cover",
    ),
    "blog_inline": CropPreset(
        id="blog_inline",
        label="Blog Inline Image",
        shape=ShapeType.CONTAIN,
        aspect_ratio={Breakpoint.ALL: None},
        min_resolution={Breakpoint.ALL: _res(400, 300)},
        max_zoom=1.0,
        breakpoints=[Breakpoint.ALL],
        output_variants=[VariantSpec(name="inline", width=1200, height=0)],
        storage_rules=_jpeg_png_webp("blog/", 12),
        reference_ui="blog-inline",
    ),
}


def get_preset(preset_id: str) -> CropPreset:
    try:
        return PRESET_REGISTRY[preset_id]
    except KeyError as exc:
        raise ValueError(f"Unknown crop preset: {preset_id!r}") from exc
