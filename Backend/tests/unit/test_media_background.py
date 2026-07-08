"""Tests for app.modules.media.background — variant generation orchestration.

Covers the soft-delete race guarded against in generate_variants_for_breakpoints
(image removed mid-run must not have its status resurrected) and the
not-found path in generate_variants_task (image removed/never committed
before the deferred task ran)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.media import background
from app.modules.media.preset_registry import PRESET_REGISTRY, Breakpoint
from app.modules.media.schemas import BreakpointCropIn, CropBoxIn
from app.modules.media.variant_generator import GeneratedVariant

pytestmark = pytest.mark.asyncio


def _mock_db() -> AsyncMock:
    """AsyncSession mock with `.add` forced sync (AsyncMock would otherwise
    auto-mock every attribute as async, per CLAUDE.md's async-mock rules)."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _crops_for(breakpoints: list[Breakpoint]) -> dict[Breakpoint, BreakpointCropIn]:
    return {
        bp: BreakpointCropIn(box=CropBoxIn(x=0, y=0, width=100, height=100))
        for bp in breakpoints
    }


def _mock_image() -> MagicMock:
    image = MagicMock()
    image.id = uuid.uuid4()
    image.owner_type = "user"
    image.owner_id = None
    image.variants = []
    return image


class TestGenerateVariantsForBreakpoints:
    async def test_writes_ready_status_when_image_still_live(self):
        preset = PRESET_REGISTRY["avatar"]
        image = _mock_image()
        db = _mock_db()

        generated = GeneratedVariant(
            variant_name="avatar",
            breakpoint=Breakpoint.ALL,
            dpr=1,
            format="webp",
            width=200,
            height=200,
            content=b"x",
        )

        with (
            patch("app.modules.media.background.PILImage.open") as pil_open,
            patch(
                "app.modules.media.background.apply_geometry", return_value=MagicMock()
            ),
            patch(
                "app.modules.media.background.generate_variants_for_breakpoint",
                return_value=[generated],
            ),
            patch(
                "app.modules.media.background.storage.build_variant_key",
                return_value="images/avatar/user/none/x/all/avatar.webp",
            ),
            patch("app.modules.media.background.storage.put_variant"),
            patch(
                "app.modules.media.background.storage.public_url",
                return_value="https://cdn/x.webp",
            ),
            patch.object(background._repo, "replace_variants", new=AsyncMock()),
            patch.object(
                background._repo, "get_image", new=AsyncMock(return_value=image)
            ),
            patch.object(
                background._repo, "update_fields", new=AsyncMock()
            ) as update_fields,
        ):
            pil_open.return_value.load = MagicMock()
            await background.generate_variants_for_breakpoints(
                db,
                image,
                preset,
                b"orig",
                _crops_for(preset.breakpoints),
                preset.breakpoints,
            )

        update_fields.assert_awaited_once()
        assert update_fields.call_args.args[1] is image
        assert update_fields.call_args.args[2] == {"status": "ready"}

    async def test_skips_status_write_when_image_deleted_mid_run(self, caplog):
        """If the image was soft-deleted while variant generation for its
        breakpoints was still running, the final status write must be
        skipped rather than resurrecting `status` on a row the user removed
        (background.py's re-check before the final update_fields call)."""
        preset = PRESET_REGISTRY["avatar"]
        image = _mock_image()
        db = _mock_db()

        generated = GeneratedVariant(
            variant_name="avatar",
            breakpoint=Breakpoint.ALL,
            dpr=1,
            format="webp",
            width=200,
            height=200,
            content=b"x",
        )

        with (
            patch("app.modules.media.background.PILImage.open") as pil_open,
            patch(
                "app.modules.media.background.apply_geometry", return_value=MagicMock()
            ),
            patch(
                "app.modules.media.background.generate_variants_for_breakpoint",
                return_value=[generated],
            ),
            patch(
                "app.modules.media.background.storage.build_variant_key",
                return_value="images/avatar/user/none/x/all/avatar.webp",
            ),
            patch("app.modules.media.background.storage.put_variant"),
            patch(
                "app.modules.media.background.storage.public_url",
                return_value="https://cdn/x.webp",
            ),
            patch.object(background._repo, "replace_variants", new=AsyncMock()),
            # The mid-run re-check finds the image gone (soft-deleted).
            patch.object(
                background._repo, "get_image", new=AsyncMock(return_value=None)
            ),
            patch.object(
                background._repo, "update_fields", new=AsyncMock()
            ) as update_fields,
        ):
            pil_open.return_value.load = MagicMock()
            with caplog.at_level("WARNING", logger="app.modules.media.background"):
                await background.generate_variants_for_breakpoints(
                    db,
                    image,
                    preset,
                    b"orig",
                    _crops_for(preset.breakpoints),
                    preset.breakpoints,
                )

        update_fields.assert_not_awaited()
        assert "deleted mid-run" in caplog.text


class TestGenerateVariantsTask:
    async def test_missing_image_logs_warning_and_noops(self, caplog):
        """The image being gone by the time the deferred task runs is an
        expected race (soft-deleted, or an upload whose request never
        committed) — not an application error, so it must warn, not error,
        and must not touch storage or attempt generation."""
        preset = PRESET_REGISTRY["hero"]
        image_id = uuid.uuid4()
        db = _mock_db()

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.database.AsyncWorkerSessionLocal", return_value=session_cm),
            patch.object(
                background._repo, "get_image", new=AsyncMock(return_value=None)
            ),
            patch("app.modules.media.background.storage.get_object_bytes") as get_bytes,
            patch(
                "app.modules.media.background.generate_variants_for_breakpoints",
                new=AsyncMock(),
            ) as gen,
        ):
            with caplog.at_level("WARNING", logger="app.modules.media.background"):
                await background.generate_variants_task(
                    image_id, preset, _crops_for(preset.breakpoints), preset.breakpoints
                )

        get_bytes.assert_not_called()
        gen.assert_not_awaited()
        assert "not found" in caplog.text
        assert not any(r.levelname == "ERROR" for r in caplog.records)

    async def test_existing_image_runs_generation(self):
        preset = PRESET_REGISTRY["hero"]
        image_id = uuid.uuid4()
        image = _mock_image()
        image.id = image_id
        image.original_key = "images/hero/banner/none/x/original.jpg"
        db = _mock_db()

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.core.database.AsyncWorkerSessionLocal", return_value=session_cm),
            patch.object(
                background._repo, "get_image", new=AsyncMock(return_value=image)
            ),
            patch(
                "app.modules.media.background.storage.get_object_bytes",
                return_value=b"orig-bytes",
            ) as get_bytes,
            patch(
                "app.modules.media.background.generate_variants_for_breakpoints",
                new=AsyncMock(),
            ) as gen,
        ):
            crops = _crops_for(preset.breakpoints)
            await background.generate_variants_task(
                image_id, preset, crops, preset.breakpoints
            )

        get_bytes.assert_called_once_with("images/hero/banner/none/x/original.jpg")
        gen.assert_awaited_once_with(
            db, image, preset, b"orig-bytes", crops, preset.breakpoints
        )
