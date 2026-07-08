"""Tests for app.modules.media.variant_generator."""

from PIL import Image

from app.modules.media.preset_registry import Breakpoint, VariantSpec
from app.modules.media.variant_generator import (
    generate_variant,
    generate_variants_for_breakpoint,
)


class TestGenerateVariant:
    def test_produces_webp_bytes_at_requested_size(self):
        img = Image.new("RGB", (1000, 1000), (10, 20, 30))
        spec = VariantSpec(name="thumbnail", width=200, height=200)
        result = generate_variant(img, spec, Breakpoint.ALL, dpr=1)
        assert result.format == "webp"
        assert result.width == 200
        assert result.height == 200
        assert result.content[:4] == b"RIFF"  # WebP container signature

    def test_flattens_alpha_for_webp(self):
        img = Image.new("RGBA", (200, 200), (255, 0, 0, 128))
        spec = VariantSpec(name="medium", width=100, height=100)
        result = generate_variant(img, spec, Breakpoint.ALL, dpr=1)
        # decode back and confirm no alpha channel leaked through
        from io import BytesIO

        decoded = Image.open(BytesIO(result.content))
        assert decoded.mode != "RGBA"

    def test_png_format_preserves_alpha(self):
        img = Image.new("RGBA", (200, 200), (255, 0, 0, 128))
        spec = VariantSpec(name="print", width=100, height=0, format="png")
        result = generate_variant(img, spec, Breakpoint.ALL, dpr=1)
        assert result.format == "png"
        from io import BytesIO

        decoded = Image.open(BytesIO(result.content))
        assert decoded.mode == "RGBA"

    def test_contain_mode_zero_height_preserves_aspect(self):
        img = Image.new("RGBA", (400, 200), (0, 0, 0, 255))
        spec = VariantSpec(name="web", width=200, height=0, format="png")
        result = generate_variant(img, spec, Breakpoint.ALL, dpr=1)
        assert result.width == 200
        assert result.height == 100


class TestGenerateVariantsForBreakpoint:
    def test_generates_one_artifact_per_spec_and_dpr(self):
        img = Image.new("RGB", (2000, 2000), (10, 20, 30))
        specs = [
            VariantSpec(name="thumbnail", width=200, height=200, dprs=[1]),
            VariantSpec(name="large", width=1200, height=1200, dprs=[1, 2]),
        ]
        results = generate_variants_for_breakpoint(img, specs, Breakpoint.DESKTOP)
        assert len(results) == 3
        names_dprs = {(r.variant_name, r.dpr) for r in results}
        assert names_dprs == {("thumbnail", 1), ("large", 1), ("large", 2)}

    def test_2x_dpr_doubles_pixel_dimensions(self):
        img = Image.new("RGB", (3000, 3000), (10, 20, 30))
        specs = [VariantSpec(name="large", width=1200, height=1200, dprs=[1, 2])]
        results = generate_variants_for_breakpoint(img, specs, Breakpoint.DESKTOP)
        by_dpr = {r.dpr: r for r in results}
        assert by_dpr[1].width == 1200
        assert by_dpr[2].width == 2400
