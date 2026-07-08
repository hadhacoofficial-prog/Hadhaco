"""Tests for app.modules.media.validation."""

import io

import pytest
from PIL import Image

from app.modules.media.preset_registry import PRESET_REGISTRY
from app.modules.media.validation import (
    ImageValidationError,
    resolve_extension,
    validate_upload,
)


def _jpeg_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


class TestValidateUpload:
    def test_accepts_valid_image_within_limits(self):
        preset = PRESET_REGISTRY["product"]
        content = _jpeg_bytes(900, 900)
        validate_upload(content, "photo.jpg", "image/jpeg", preset)  # no raise

    def test_rejects_disallowed_mime_type(self):
        preset = PRESET_REGISTRY["product"]
        content = _jpeg_bytes(900, 900)
        with pytest.raises(ImageValidationError):
            validate_upload(content, "photo.gif", "image/gif", preset)

    def test_rejects_undersized_image(self):
        preset = PRESET_REGISTRY["product"]  # min 800x800
        content = _jpeg_bytes(100, 100)
        with pytest.raises(ImageValidationError):
            validate_upload(content, "photo.jpg", "image/jpeg", preset)

    def test_rejects_oversized_file(self):
        preset = PRESET_REGISTRY["avatar"]  # 5 MB limit
        content = b"0" * (6 * 1024 * 1024)
        with pytest.raises(ImageValidationError):
            validate_upload(content, "big.jpg", "image/jpeg", preset)

    def test_svg_skips_dimension_check(self):
        preset = PRESET_REGISTRY["footer_logo"]
        svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
        validate_upload(svg, "logo.svg", "image/svg+xml", preset)  # no raise


class TestResolveExtension:
    def test_from_filename(self):
        assert resolve_extension("photo.PNG", "image/png") == "png"

    def test_falls_back_to_content_type(self):
        assert resolve_extension("noextension", "image/webp") == "webp"
