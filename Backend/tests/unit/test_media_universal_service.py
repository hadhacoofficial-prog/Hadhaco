"""Tests for app.modules.media.universal_service.UniversalImageService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.media.preset_registry import PRESET_REGISTRY, Breakpoint
from app.modules.media.schemas import (
    BreakpointCropIn,
    CropBoxIn,
    CropGeometryIn,
    FocusPointIn,
)
from app.modules.media.universal_service import (
    UniversalImageService,
    UniversalImageServiceError,
    _artifact_count,
    _default_crops_for_preset,
    _geometry_metadata,
)


class TestArtifactCount:
    def test_avatar_preset_is_small(self):
        preset = PRESET_REGISTRY["avatar"]
        # 2 variants (avatar, avatar-sm), 1 dpr each, 1 breakpoint ("all")
        assert _artifact_count(preset, preset.breakpoints) == 2

    def test_hero_preset_exceeds_background_threshold(self):
        preset = PRESET_REGISTRY["hero"]
        # 1 variant x 2 dprs x 3 breakpoints = 6
        assert _artifact_count(preset, preset.breakpoints) == 6


class TestDefaultCropsForPreset:
    def test_seeds_one_entry_per_breakpoint(self):
        preset = PRESET_REGISTRY["hero"]
        crops = _default_crops_for_preset(preset, 4000, 3000)
        assert set(crops.keys()) == set(preset.breakpoints)
        for bp in preset.breakpoints:
            assert crops[bp].box.width > 0
            assert crops[bp].box.height > 0


class TestGeometryMetadata:
    def test_includes_preset_and_crops(self):
        preset = PRESET_REGISTRY["product"]
        crops = _default_crops_for_preset(preset, 1000, 1000)
        meta = _geometry_metadata(preset, 1000, 1000, crops, FocusPointIn())
        assert meta["preset_id"] == "product"
        assert meta["original_dimensions"] == {"width": 1000, "height": 1000}
        assert set(meta["crops"].keys()) == {"desktop", "tablet", "mobile"}


def _jpeg_bytes(width: int, height: int) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _mock_db() -> AsyncMock:
    """AsyncSession mock with `.add` forced sync (AsyncMock would otherwise
    auto-mock every attribute as async, per CLAUDE.md's async-mock rules)."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


class TestUpload:
    async def test_upload_rejects_invalid_file(self):
        svc = UniversalImageService()
        db = _mock_db()
        with pytest.raises(UniversalImageServiceError):
            await svc.upload(
                db,
                preset_id="avatar",
                file_bytes=b"not-an-image",
                filename="x.jpg",
                content_type="image/jpeg",
                owner_type="user",
                owner_id=None,
                uploaded_by=None,
                background_tasks=MagicMock(),
            )

    async def test_upload_small_preset_generates_synchronously(self):
        svc = UniversalImageService()
        db = _mock_db()
        background_tasks = MagicMock()

        with (
            patch(
                "app.modules.media.universal_service.storage.build_original_key"
            ) as build_key,
            patch(
                "app.modules.media.universal_service.storage.put_original"
            ) as put_original,
            patch(
                "app.modules.media.universal_service.background.generate_variants_for_breakpoints",
                new=AsyncMock(),
            ) as gen_sync,
        ):
            build_key.return_value = "images/avatar/user/none/some-id/original.jpg"
            content = _jpeg_bytes(300, 300)

            image = await svc.upload(
                db,
                preset_id="avatar",
                file_bytes=content,
                filename="avatar.jpg",
                content_type="image/jpeg",
                owner_type="user",
                owner_id=None,
                uploaded_by=None,
                background_tasks=background_tasks,
            )

        put_original.assert_called_once()
        gen_sync.assert_awaited_once()
        background_tasks.add_task.assert_not_called()
        assert image.preset_id == "avatar"
        assert image.original_width == 300
        assert image.original_height == 300
        assert image.status == "pending"

    async def test_upload_large_preset_defers_to_background_task(self):
        svc = UniversalImageService()
        db = _mock_db()
        background_tasks = MagicMock()

        with (
            patch(
                "app.modules.media.universal_service.storage.build_original_key"
            ) as build_key,
            patch("app.modules.media.universal_service.storage.put_original"),
            patch(
                "app.modules.media.universal_service.background.generate_variants_for_breakpoints",
                new=AsyncMock(),
            ) as gen_sync,
        ):
            build_key.return_value = "images/hero/banner/none/some-id/original.jpg"
            content = _jpeg_bytes(2000, 800)

            await svc.upload(
                db,
                preset_id="hero",
                file_bytes=content,
                filename="hero.jpg",
                content_type="image/jpeg",
                owner_type="banner",
                owner_id=None,
                uploaded_by=None,
                background_tasks=background_tasks,
            )

        gen_sync.assert_not_awaited()
        background_tasks.add_task.assert_called_once()


class TestCrop:
    async def test_crop_merges_payload_into_existing_geometry(self):
        svc = UniversalImageService()
        db = _mock_db()
        background_tasks = MagicMock()

        image = MagicMock()
        # "collection" (3 variants x 1 dpr = 3 artifacts/breakpoint) stays
        # under the background-task threshold when only one breakpoint
        # changes, unlike "product" (3 variants x 2 dpr = 6, which would
        # itself trigger the background path and defeat this test's point).
        image.preset_id = "collection"
        image.original_key = "images/collection/collection/x/y/original.jpg"
        image.original_width = 1000
        image.original_height = 1000
        image.variants = []

        payload = CropGeometryIn(
            crops={
                Breakpoint.DESKTOP: BreakpointCropIn(
                    box=CropBoxIn(x=10, y=10, width=500, height=500),
                    zoom=1.2,
                    rotation=0,
                )
            },
            focus_point=FocusPointIn(x=0.3, y=0.7),
        )

        with (
            patch(
                "app.modules.media.universal_service.storage.get_object_bytes",
                return_value=_jpeg_bytes(1000, 1000),
            ),
            patch(
                "app.modules.media.universal_service._repo.update_metadata",
                new=AsyncMock(return_value=image),
            ) as update_meta,
            patch(
                "app.modules.media.universal_service.background.generate_variants_for_breakpoints",
                new=AsyncMock(),
            ) as gen_sync,
        ):
            await svc.crop(
                db, image=image, payload=payload, background_tasks=background_tasks
            )

        update_meta.assert_awaited_once()
        saved_metadata = update_meta.call_args.args[2]
        assert saved_metadata["crops"]["desktop"]["box"] == {
            "x": 10.0,
            "y": 10.0,
            "width": 500.0,
            "height": 500.0,
        }
        assert saved_metadata["focus_point"] == {"x": 0.3, "y": 0.7}
        # Only the changed breakpoint should be regenerated, not all three.
        gen_sync.assert_awaited_once()
        _, _, _, _, _, changed_breakpoints = gen_sync.call_args.args
        assert changed_breakpoints == [Breakpoint.DESKTOP]
