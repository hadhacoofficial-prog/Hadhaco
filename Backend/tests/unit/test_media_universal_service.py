"""Tests for app.modules.media.universal_service.UniversalImageService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.media import background
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
    _crops_equal,
    _default_crops_for_preset,
    _geometry_metadata,
)


class TestCropBoxInAllowsNegativeOrigin:
    """CropBoxIn.x/y must not reject negative values at the request-schema
    layer — a box can legitimately start before the original's top-left
    corner (zoom/pan rounding, or a deliberate letterboxed frame), and
    crop_engine.validate_and_clamp_crop_box already clamps it back into
    bounds for non-strict_bounds presets. A `ge=0` constraint here would
    422 an ordinary editor interaction before that clamp ever runs."""

    def test_negative_x_and_y_are_accepted(self):
        box = CropBoxIn(x=-5, y=-20, width=899, height=899)
        assert box.x == -5
        assert box.y == -20

    def test_non_positive_width_or_height_still_rejected(self):
        with pytest.raises(ValueError):
            CropBoxIn(x=0, y=0, width=0, height=899)


class TestDefaultCropsForPreset:
    def test_seeds_one_entry_per_breakpoint(self):
        preset = PRESET_REGISTRY["hero_desktop"]
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


class TestCropsEqual:
    def test_identical_geometry_is_equal(self):
        a = BreakpointCropIn(box=CropBoxIn(x=1, y=2, width=3, height=4), zoom=1.5)
        b = BreakpointCropIn(box=CropBoxIn(x=1, y=2, width=3, height=4), zoom=1.5)
        assert _crops_equal(a, b) is True

    def test_tiny_float_drift_is_still_equal(self):
        # Round-tripping through JSON/Pydantic can introduce float noise —
        # equality must tolerate that instead of demanding bit-for-bit `==`.
        a = BreakpointCropIn(box=CropBoxIn(x=1.0, y=2.0, width=3.0, height=4.0))
        b = BreakpointCropIn(box=CropBoxIn(x=1.0000001, y=2.0, width=3.0, height=4.0))
        assert _crops_equal(a, b) is True

    def test_different_box_is_not_equal(self):
        a = BreakpointCropIn(box=CropBoxIn(x=1, y=2, width=3, height=4))
        b = BreakpointCropIn(box=CropBoxIn(x=10, y=2, width=3, height=4))
        assert _crops_equal(a, b) is False

    def test_none_is_not_equal(self):
        a = BreakpointCropIn(box=CropBoxIn(x=1, y=2, width=3, height=4))
        assert _crops_equal(a, None) is False


class TestParseStoredCrops:
    """parse_stored_crops now lives in background.py (shared with the
    media_generation worker), imported here as background.parse_stored_crops."""

    def test_parses_metadata_crops_back_into_breakpoint_crop_in(self):
        preset = PRESET_REGISTRY["product"]
        crops = _default_crops_for_preset(preset, 1000, 1000)
        meta = _geometry_metadata(preset, 1000, 1000, crops, FocusPointIn())
        image = MagicMock()
        image.metadata_ = meta
        parsed = background.parse_stored_crops(image)
        assert set(parsed.keys()) == set(preset.breakpoints)
        assert (
            parsed[Breakpoint.DESKTOP].box.width == crops[Breakpoint.DESKTOP].box.width
        )

    def test_empty_metadata_yields_empty_dict(self):
        image = MagicMock()
        image.metadata_ = {}
        assert background.parse_stored_crops(image) == {}


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
            )

    async def test_upload_enqueues_generation_and_returns_immediately(self):
        """A raster upload persists 'pending' + which breakpoints need
        regenerating and returns immediately — actual crop/encode/R2-upload
        now runs off the request, in the media_generation background worker
        (docs audit CB-1 Phase 2), not synchronously in-request."""
        svc = UniversalImageService()
        db = _mock_db()

        with (
            patch(
                "app.modules.media.universal_service.storage.build_original_key"
            ) as build_key,
            patch("app.modules.media.universal_service.storage.put_original"),
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            build_key.return_value = "images/hero/banner/none/some-id/original.jpg"
            content = _jpeg_bytes(2000, 800)

            image = await svc.upload(
                db,
                preset_id="hero_desktop",
                file_bytes=content,
                filename="hero.jpg",
                content_type="image/jpeg",
                owner_type="banner",
                owner_id=None,
                uploaded_by=None,
            )

        enqueue.assert_called_once_with(image.id)
        assert image.preset_id == "hero_desktop"
        assert image.status == "pending"
        assert set(image.metadata_["generation"]["pending_breakpoints"]) == {
            bp.value for bp in PRESET_REGISTRY["hero_desktop"].breakpoints
        }


class TestCrop:
    def _make_image(self, preset_id: str, width: int, height: int):
        preset = PRESET_REGISTRY[preset_id]
        crops = _default_crops_for_preset(preset, width, height)
        image = MagicMock()
        image.preset_id = preset_id
        image.original_key = f"images/{preset_id}/x/y/original.jpg"
        image.original_width = width
        image.original_height = height
        image.metadata_ = _geometry_metadata(
            preset, width, height, crops, FocusPointIn()
        )
        image.variants = []
        return image

    async def test_crop_merges_payload_into_existing_geometry(self):
        svc = UniversalImageService()
        db = _mock_db()
        image = self._make_image("collection", 1000, 1000)

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
                "app.modules.media.universal_service._repo.update_metadata",
                new=AsyncMock(return_value=image),
            ) as update_meta,
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            result = await svc.crop(db, image=image, payload=payload)

        update_meta.assert_awaited_once()
        saved_metadata = update_meta.call_args.args[2]
        assert saved_metadata["crops"]["desktop"]["box"] == {
            "x": 10.0,
            "y": 10.0,
            "width": 500.0,
            "height": 500.0,
        }
        assert saved_metadata["focus_point"] == {"x": 0.3, "y": 0.7}
        # Only the changed breakpoint should be queued for regeneration, not
        # all three — and this now holds regardless of preset/artifact
        # count, since it's just which breakpoints get enqueued, not a
        # size-based dispatch decision.
        enqueue.assert_called_once_with(result.id)
        assert result.metadata_["generation"]["pending_breakpoints"] == ["desktop"]

    async def test_product_single_breakpoint_crop_still_enqueues_generation(self):
        """Regression guard: "product" is 3 variants x 2 dprs x 3 breakpoints
        — even editing just one breakpoint must still queue that
        breakpoint for regeneration, not silently drop it."""
        svc = UniversalImageService()
        db = _mock_db()
        image = self._make_image("product", 1000, 1000)

        payload = CropGeometryIn(
            crops={
                Breakpoint.DESKTOP: BreakpointCropIn(
                    box=CropBoxIn(x=5, y=5, width=400, height=400),
                )
            },
        )

        with (
            patch(
                "app.modules.media.universal_service._repo.update_metadata",
                new=AsyncMock(return_value=image),
            ),
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            await svc.crop(db, image=image, payload=payload)

        enqueue.assert_called_once()

    async def test_resaving_identical_crop_skips_regeneration(self):
        """If the incoming crop for a breakpoint matches what's already
        stored AND that breakpoint already has a ready variant, there's
        nothing to regenerate — avoids needless R2 churn on a no-op Save."""
        svc = UniversalImageService()
        db = _mock_db()
        image = self._make_image("collection", 1000, 1000)
        stored = background.parse_stored_crops(image)[Breakpoint.DESKTOP]
        variant = MagicMock()
        variant.breakpoint = "desktop"
        variant.status = "ready"
        image.variants = [variant]

        payload = CropGeometryIn(
            crops={Breakpoint.DESKTOP: stored},
        )

        with (
            patch(
                "app.modules.media.universal_service._repo.update_metadata",
                new=AsyncMock(return_value=image),
            ),
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            await svc.crop(db, image=image, payload=payload)

        enqueue.assert_not_called()

    async def test_untouched_breakpoint_keeps_its_stored_crop(self):
        """Regression guard for the data-loss bug: editing only "desktop"
        must not silently reset "tablet"/"mobile" back to a fresh centered
        default — the merge base has to be the actually-stored geometry."""
        svc = UniversalImageService()
        db = _mock_db()
        image = self._make_image("product", 1000, 2000)  # non-square original
        original_mobile_box = background.parse_stored_crops(image)[
            Breakpoint.MOBILE
        ].box

        payload = CropGeometryIn(
            crops={
                Breakpoint.DESKTOP: BreakpointCropIn(
                    box=CropBoxIn(x=1, y=1, width=300, height=300),
                )
            },
        )

        with (
            patch(
                "app.modules.media.universal_service._repo.update_metadata",
                new=AsyncMock(return_value=image),
            ) as update_meta,
            patch("app.workers.media_generation.enqueue"),
        ):
            await svc.crop(db, image=image, payload=payload)

        saved_metadata = update_meta.call_args.args[2]
        mobile_box = saved_metadata["crops"]["mobile"]["box"]
        assert mobile_box == {
            "x": original_mobile_box.x,
            "y": original_mobile_box.y,
            "width": original_mobile_box.width,
            "height": original_mobile_box.height,
        }

    async def test_out_of_bounds_crop_on_strict_preset_raises_immediately(self):
        """CB-1 Phase 2 regression guard: moving generation to the
        background must not silently swallow a genuinely invalid crop
        request — strict_bounds presets still reject an out-of-bounds box
        synchronously (docs audit HP-3), using only the original's stored
        dimensions (no R2 fetch needed to validate)."""
        from app.modules.media.crop_engine import CropGeometryError

        svc = UniversalImageService()
        db = _mock_db()
        image = self._make_image("hero_desktop", 1920, 700)  # hero is strict_bounds

        payload = CropGeometryIn(
            crops={
                Breakpoint.DESKTOP: BreakpointCropIn(
                    # Box extends past the original's actual bounds.
                    box=CropBoxIn(x=0, y=0, width=5000, height=5000),
                )
            },
        )

        with (
            patch(
                "app.modules.media.universal_service._repo.update_metadata",
                new=AsyncMock(),
            ) as update_meta,
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            with pytest.raises(CropGeometryError):
                await svc.crop(db, image=image, payload=payload)

        # Must fail before persisting or enqueueing anything.
        update_meta.assert_not_awaited()
        enqueue.assert_not_called()

    async def test_slightly_out_of_bounds_crop_on_non_strict_preset_is_accepted(self):
        """Regression guard: a box that overshoots the original by a small
        margin (e.g. rounding from the editor's zoom/pan math) must NOT be
        rejected on a non-strict_bounds preset ("category" here) — the
        architecture's own design is to let crop_engine clamp it back into
        bounds when the background worker actually generates, not to 422 at
        the API layer. Previously CropBoxIn.y had ge=0, which rejected this
        before it ever reached that clamp logic."""
        svc = UniversalImageService()
        db = _mock_db()
        image = self._make_image("category", 899, 899)  # category is not strict_bounds

        payload = CropGeometryIn(
            crops={
                Breakpoint.DESKTOP: BreakpointCropIn(
                    # y is slightly negative — overshoots the top edge.
                    box=CropBoxIn(x=133, y=-20, width=899, height=899),
                )
            },
        )

        with (
            patch(
                "app.modules.media.universal_service._repo.update_metadata",
                new=AsyncMock(return_value=image),
            ) as update_meta,
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            result = await svc.crop(db, image=image, payload=payload)

        update_meta.assert_awaited_once()
        enqueue.assert_called_once_with(result.id)


class TestSvgUpload:
    """CB-3 regression guard: SVG has no raster dimensions PIL can decode —
    uploading one must never reach generate_variants_for_breakpoints, which
    crashes trying to PILImage.open() the raw SVG bytes."""

    async def test_svg_upload_skips_raster_pipeline_and_marks_ready(self):
        svc = UniversalImageService()
        db = _mock_db()
        svg = b"<svg xmlns='http://www.w3.org/2000/svg'><rect width='10' height='10'/></svg>"

        with (
            patch(
                "app.modules.media.universal_service.storage.build_original_key",
                return_value="images/footer_logo/company_config/none/some-id/original.svg",
            ),
            patch(
                "app.modules.media.universal_service.storage.put_original",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.media.universal_service.storage.public_url",
                return_value="https://cdn.example/original.svg",
            ),
            patch("app.workers.media_generation.enqueue") as enqueue,
            patch(
                "app.modules.media.universal_service._repo.replace_variants",
                new=AsyncMock(),
            ) as replace_variants,
            patch(
                "app.modules.media.universal_service._repo.update_fields",
                new=AsyncMock(),
            ) as update_fields,
        ):
            await svc.upload(
                db,
                preset_id="footer_logo",
                file_bytes=svg,
                filename="logo.svg",
                content_type="image/svg+xml",
                owner_type="company_config",
                owner_id=None,
                uploaded_by=None,
            )

        enqueue.assert_not_called()
        assert replace_variants.await_count == len(
            PRESET_REGISTRY["footer_logo"].breakpoints
        )
        variant_rows = replace_variants.call_args.args[3]
        assert all(
            row["url"] == "https://cdn.example/original.svg" for row in variant_rows
        )
        assert all(row["status"] == "ready" for row in variant_rows)
        update_fields.assert_awaited_once()
        assert update_fields.call_args.args[2] == {"status": "ready"}

    async def test_svg_upload_sanitizes_before_storing(self):
        svc = UniversalImageService()
        db = _mock_db()
        svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"

        with (
            patch(
                "app.modules.media.universal_service.storage.build_original_key",
                return_value="k",
            ),
            patch(
                "app.modules.media.universal_service.storage.put_original",
                new=AsyncMock(),
            ) as put_original,
            patch(
                "app.modules.media.universal_service.storage.public_url",
                return_value="https://cdn.example/k",
            ),
            patch(
                "app.modules.media.universal_service._repo.replace_variants",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.media.universal_service._repo.update_fields",
                new=AsyncMock(),
            ),
        ):
            await svc.upload(
                db,
                preset_id="footer_logo",
                file_bytes=svg,
                filename="logo.svg",
                content_type="image/svg+xml",
                owner_type="company_config",
                owner_id=None,
                uploaded_by=None,
            )

        stored_bytes = put_original.call_args.args[1]
        assert b"script" not in stored_bytes


class TestCropOnSvgImage:
    async def test_crop_on_svg_image_is_a_noop_finalize(self):
        """A crop request against a vector original has nothing to crop —
        it must re-confirm the variant slots rather than fall into the
        raster pipeline (which would crash on SVG bytes)."""
        svc = UniversalImageService()
        db = _mock_db()
        image = MagicMock()
        image.preset_id = "footer_logo"
        image.mime_type = "image/svg+xml"
        image.original_key = "images/footer_logo/x/y/original.svg"
        image.original_size_bytes = 123

        with (
            patch(
                "app.modules.media.universal_service.storage.get_object_bytes",
                new=AsyncMock(),
            ) as get_bytes,
            patch(
                "app.modules.media.universal_service.storage.public_url",
                return_value="https://cdn.example/original.svg",
            ),
            patch(
                "app.modules.media.universal_service._repo.replace_variants",
                new=AsyncMock(),
            ) as replace_variants,
            patch(
                "app.modules.media.universal_service._repo.update_fields",
                new=AsyncMock(),
            ) as update_fields,
        ):
            await svc.crop(db, image=image, payload=CropGeometryIn(crops={}))

        get_bytes.assert_not_called()
        replace_variants.assert_awaited()
        update_fields.assert_awaited_once()


class TestSkipInitialGeneration:
    """HP-5 regression guard: the editor's upload-then-crop flow passes
    skip_initial_generation=True so the default centered crop's variants
    are never generated just to be discarded a moment later by the real
    geometry from the immediately-following crop() call."""

    async def test_skip_initial_generation_avoids_double_encode(self):
        svc = UniversalImageService()
        db = _mock_db()

        with (
            patch(
                "app.modules.media.universal_service.storage.build_original_key",
                return_value="images/product/product/none/some-id/original.jpg",
            ),
            patch(
                "app.modules.media.universal_service.storage.put_original",
                new=AsyncMock(),
            ),
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            image = await svc.upload(
                db,
                preset_id="product",
                file_bytes=_jpeg_bytes(900, 900),
                filename="p.jpg",
                content_type="image/jpeg",
                owner_type="product",
                owner_id=None,
                uploaded_by=None,
                skip_initial_generation=True,
            )

        enqueue.assert_not_called()
        assert image.status == "pending"

    async def test_default_still_enqueues_generation(self):
        """Callers that don't opt in keep today's behavior exactly —
        avatar/review uploads never call crop() afterward, so they must
        still get variants generated (now via the background worker) from
        the upload call itself."""
        svc = UniversalImageService()
        db = _mock_db()

        with (
            patch(
                "app.modules.media.universal_service.storage.build_original_key",
                return_value="images/avatar/user/none/some-id/original.jpg",
            ),
            patch(
                "app.modules.media.universal_service.storage.put_original",
                new=AsyncMock(),
            ),
            patch("app.workers.media_generation.enqueue") as enqueue,
        ):
            await svc.upload(
                db,
                preset_id="avatar",
                file_bytes=_jpeg_bytes(300, 300),
                filename="a.jpg",
                content_type="image/jpeg",
                owner_type="user",
                owner_id=None,
                uploaded_by=None,
            )

        enqueue.assert_called_once()


class TestDeleteOrphanLogging:
    async def test_logs_warning_when_r2_purge_incomplete(self, caplog):
        """HP-7 regression guard: if the R2 folder purge fails, the DB row
        still gets soft-deleted (the admin action must not appear to fail),
        but the resulting orphaned objects must be logged, not swallowed."""
        svc = UniversalImageService()
        db = _mock_db()
        image = MagicMock()
        image.id = "abc-123"
        image.original_key = "images/product/product/x/y/original.jpg"

        with (
            patch(
                "app.modules.media.universal_service.storage.delete_image_folder",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "app.modules.media.universal_service._repo.soft_delete",
                new=AsyncMock(),
            ) as soft_delete,
            caplog.at_level("WARNING", logger="app.modules.media.universal_service"),
        ):
            await svc.delete(db, image=image)

        soft_delete.assert_awaited_once()
        assert "orphaned" in caplog.text
