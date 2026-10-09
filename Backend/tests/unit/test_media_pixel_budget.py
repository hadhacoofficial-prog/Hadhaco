import io

import pytest
from PIL import Image

from app.modules.media.validation import (
    MAX_IMAGE_PIXELS,
    ImageValidationError,
    assert_pixel_budget,
)


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (w, h)).save(buf, format="PNG")
    return buf.getvalue()


def test_small_image_passes():
    assert_pixel_budget(_png(64, 64))


def test_oversized_dimensions_rejected_from_header_only():
    # ~170 Mpx but compresses to a few hundred KB: must be rejected without
    # decoding pixel data.
    data = _png(13000, 13000)
    assert 13000 * 13000 > MAX_IMAGE_PIXELS
    with pytest.raises(ImageValidationError):
        assert_pixel_budget(data)


def test_garbage_is_rejected():
    with pytest.raises(ImageValidationError):
        assert_pixel_budget(b"not an image")


def test_cms_folder_and_extension_are_validated():
    from app.modules.cms.media_service import _EXT_BY_MIME, _FOLDER_RE

    assert _FOLDER_RE.fullmatch("cms/hero")
    for bad in ("../x", "a/../b", "A/B", "cms//x", "a" * 41, "x/y/z/w/v", "cms/ünï"):
        assert not _FOLDER_RE.fullmatch(bad)
    assert _EXT_BY_MIME["image/png"] == "png"
