"""Tests for the Universal Crop Engine (app.modules.media.crop_engine)."""

import pytest
from PIL import Image

from app.modules.media.crop_engine import (
    CropBox,
    CropGeometryError,
    apply_geometry,
    apply_shape_mask,
    crop_to_box,
    default_crop_box,
    rotate,
    validate_and_clamp_crop_box,
)
from app.modules.media.preset_registry import PRESET_REGISTRY, ShapeType


class TestRotate:
    def test_zero_degrees_is_noop(self):
        img = Image.new("RGB", (100, 50), (255, 0, 0))
        result = rotate(img, 0)
        assert result is img

    def test_rotation_expands_canvas(self):
        img = Image.new("RGB", (100, 50), (255, 0, 0))
        result = rotate(img, 90)
        assert result.width == 50
        assert result.height == 100


class TestValidateAndClampCropBox:
    def test_box_within_bounds_is_unchanged(self):
        box = CropBox(x=10, y=10, width=50, height=50)
        result = validate_and_clamp_crop_box(box, 100, 100, strict_bounds=False)
        assert result == box

    def test_out_of_bounds_raises_when_strict(self):
        box = CropBox(x=-10, y=0, width=50, height=50)
        with pytest.raises(CropGeometryError):
            validate_and_clamp_crop_box(box, 100, 100, strict_bounds=True)

    def test_out_of_bounds_clamps_when_not_strict(self):
        box = CropBox(x=-10, y=-10, width=50, height=50)
        result = validate_and_clamp_crop_box(box, 100, 100, strict_bounds=False)
        assert result.x == 0
        assert result.y == 0
        assert result.width == 40
        assert result.height == 40

    def test_box_exceeding_right_bottom_edge_clamps(self):
        box = CropBox(x=80, y=80, width=50, height=50)
        result = validate_and_clamp_crop_box(box, 100, 100, strict_bounds=False)
        assert result.width == 20
        assert result.height == 20


class TestCropToBox:
    def test_crops_to_expected_region(self):
        img = Image.new("RGB", (100, 100), (0, 255, 0))
        box = CropBox(x=10, y=10, width=30, height=40)
        result = crop_to_box(img, box)
        assert result.size == (30, 40)

    def test_degenerate_box_returns_original(self):
        img = Image.new("RGB", (100, 100), (0, 255, 0))
        box = CropBox(x=50, y=50, width=0, height=0)
        result = crop_to_box(img, box)
        assert result is img


class TestApplyShapeMask:
    def test_rectangle_preserves_source_mode(self):
        img = Image.new("RGB", (50, 50), (255, 0, 0))
        result = apply_shape_mask(img, ShapeType.RECTANGLE)
        assert result.mode == "RGB"

    def test_contain_preserves_alpha_for_logo_transparency(self):
        img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        result = apply_shape_mask(img, ShapeType.CONTAIN)
        assert result.mode == "RGBA"
        assert result.getpixel((25, 25))[3] == 128

    def test_circle_has_alpha(self):
        img = Image.new("RGB", (50, 50), (255, 0, 0))
        result = apply_shape_mask(img, ShapeType.CIRCLE)
        assert result.mode == "RGBA"
        # corner pixel should be masked out (alpha 0), center should be opaque
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((25, 25))[3] == 255

    def test_rounded_rect_has_alpha(self):
        img = Image.new("RGB", (50, 50), (255, 0, 0))
        result = apply_shape_mask(img, ShapeType.ROUNDED_RECT)
        assert result.mode == "RGBA"


class TestApplyGeometryFullPipeline:
    def test_product_preset_crop_end_to_end(self):
        preset = PRESET_REGISTRY["product"]
        img = Image.new("RGB", (1000, 1000), (10, 20, 30))
        box = CropBox(x=100, y=100, width=400, height=400)
        result = apply_geometry(img, box, rotation_degrees=0, preset=preset)
        assert result.size == (400, 400)
        assert result.mode == "RGB"  # SQUARE shape carries no alpha

    def test_gender_section_preset_produces_circle(self):
        preset = PRESET_REGISTRY["gender_section"]
        img = Image.new("RGB", (800, 800), (10, 20, 30))
        box = CropBox(x=0, y=0, width=600, height=600)
        result = apply_geometry(img, box, rotation_degrees=0, preset=preset)
        assert result.mode == "RGBA"

    def test_rotation_rejected_for_no_rotation_preset(self):
        preset = PRESET_REGISTRY["hero"]  # rotation NONE
        img = Image.new("RGB", (2000, 800), (10, 20, 30))
        box = CropBox(x=0, y=0, width=1920, height=700)
        with pytest.raises(CropGeometryError):
            apply_geometry(img, box, rotation_degrees=15, preset=preset)

    def test_strict_bounds_preset_rejects_oob_box(self):
        preset = PRESET_REGISTRY["hero"]  # strict_bounds=True
        img = Image.new("RGB", (1000, 500), (10, 20, 30))
        box = CropBox(x=0, y=0, width=1920, height=700)  # exceeds source
        with pytest.raises(CropGeometryError):
            apply_geometry(img, box, rotation_degrees=0, preset=preset)


class TestDefaultCropBox:
    def test_none_aspect_returns_full_image(self):
        box = default_crop_box(800, 600, None)
        assert box == CropBox(x=0, y=0, width=800, height=600)

    def test_centers_square_crop_in_wide_image(self):
        box = default_crop_box(1000, 500, 1.0)
        assert box.width == 500
        assert box.height == 500
        assert box.x == 250
        assert box.y == 0

    def test_centers_wide_crop_in_tall_image(self):
        box = default_crop_box(500, 1000, 2.0)
        assert box.width == 500
        assert box.height == 250
        assert box.x == 0
        assert box.y == 375
