"""Tests for app.modules.media.validation."""

import io

import pytest
from PIL import Image

from app.modules.media.preset_registry import PRESET_REGISTRY
from app.modules.media.validation import (
    ImageValidationError,
    resolve_extension,
    sanitize_svg,
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


class TestSanitizeSvg:
    def test_strips_script_tag(self):
        svg = (
            b"<svg xmlns='http://www.w3.org/2000/svg'>"
            b"<script>alert(1)</script><rect width='10' height='10'/></svg>"
        )
        cleaned = sanitize_svg(svg)
        assert b"script" not in cleaned
        assert b"rect" in cleaned

    def test_strips_on_event_attributes(self):
        svg = (
            b"<svg xmlns='http://www.w3.org/2000/svg'>"
            b"<rect onclick='alert(1)' width='10' height='10'/></svg>"
        )
        cleaned = sanitize_svg(svg)
        assert b"onclick" not in cleaned
        assert b"rect" in cleaned

    def test_strips_javascript_href(self):
        svg = (
            b"<svg xmlns='http://www.w3.org/2000/svg' "
            b"xmlns:xlink='http://www.w3.org/1999/xlink'>"
            b"<a xlink:href='javascript:alert(1)'><rect width='10' height='10'/></a>"
            b"</svg>"
        )
        cleaned = sanitize_svg(svg)
        assert b"javascript:" not in cleaned

    def test_preserves_safe_presentation_content(self):
        svg = (
            b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'>"
            b"<circle cx='5' cy='5' r='4' fill='#000'/></svg>"
        )
        cleaned = sanitize_svg(svg)
        assert b"circle" in cleaned
        assert b'fill="#000"' in cleaned or b"fill='#000'" in cleaned

    def test_rejects_unparseable_input(self):
        with pytest.raises(ImageValidationError):
            sanitize_svg(b"not xml at all <<<")
