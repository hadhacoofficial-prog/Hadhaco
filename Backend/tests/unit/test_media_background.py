"""Tests for app.modules.media.background — variant generation orchestration.

Covers the soft-delete race guarded against in generate_variants_for_breakpoints
(image removed mid-run must not have its status resurrected), and the CB-1
performance fix (parallel R2 uploads via asyncio.gather instead of one
await-per-variant in a nested for loop)."""

import asyncio
import time
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
    image.version = 1
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
        # version is bumped again on completion — not just when crop()/
        # upload() first persist the request — so the `?v=` cache-buster on
        # variant URLs points at a URL the browser has never cached stale
        # content under (docs audit CB-1 Phase 2 cache-busting fix).
        assert update_fields.call_args.args[2] == {"status": "ready", "version": 2}

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


def _generated_variants_for(preset) -> dict[Breakpoint, list[GeneratedVariant]]:
    return {
        bp: [
            GeneratedVariant(
                variant_name=spec.name,
                breakpoint=bp,
                dpr=1,
                format="webp",
                width=spec.width,
                height=spec.height,
                content=b"x",
            )
            for spec in preset.output_variants
        ]
        for bp in preset.breakpoints
    }


class TestGenerateVariantsForBreakpointsPerformance:
    """Proves the CB-1 Phase 1 fix: uploads across every breakpoint's
    artifacts now run concurrently (asyncio.gather), not one `await` at a
    time in a nested for loop. Uses the real `category` preset — 2
    breakpoints x 3 variants x 1 dpr = 6 artifacts, matching the shape of
    the crop request observed taking 12-27s in production before this fix.
    An artificial per-upload delay stands in for real R2 network latency so
    the test is deterministic and fast regardless of live infra."""

    UPLOAD_DELAY_S = 0.2

    async def test_uploads_run_concurrently_not_sequentially(self):
        preset = PRESET_REGISTRY["category"]
        image = _mock_image()
        db = _mock_db()
        generated_by_breakpoint = _generated_variants_for(preset)
        artifact_count = sum(len(v) for v in generated_by_breakpoint.values())
        assert artifact_count == 6  # 2 breakpoints x 3 variants x 1 dpr

        async def _slow_put_variant(key, content, *, fmt):
            await asyncio.sleep(self.UPLOAD_DELAY_S)

        with (
            patch("app.modules.media.background.PILImage.open") as pil_open,
            patch(
                "app.modules.media.background.apply_geometry", return_value=MagicMock()
            ),
            patch(
                "app.modules.media.background.generate_variants_for_breakpoint",
                side_effect=lambda cropped, specs, bp: generated_by_breakpoint[bp],
            ),
            patch(
                "app.modules.media.background.storage.build_variant_key",
                return_value="images/category/category/none/x/desktop/thumbnail.webp",
            ),
            patch(
                "app.modules.media.background.storage.put_variant",
                new=AsyncMock(side_effect=_slow_put_variant),
            ),
            patch(
                "app.modules.media.background.storage.public_url",
                return_value="https://cdn/x.webp",
            ),
            patch.object(background._repo, "replace_variants", new=AsyncMock()),
            patch.object(
                background._repo, "get_image", new=AsyncMock(return_value=image)
            ),
            patch.object(background._repo, "update_fields", new=AsyncMock()),
        ):
            pil_open.return_value.load = MagicMock()
            t0 = time.perf_counter()
            await background.generate_variants_for_breakpoints(
                db,
                image,
                preset,
                b"orig",
                _crops_for(preset.breakpoints),
                preset.breakpoints,
            )
            elapsed = time.perf_counter() - t0

        sequential_baseline = artifact_count * self.UPLOAD_DELAY_S  # "before": 1.2s
        # "after": one round of concurrent uploads (~0.2s) plus scheduling
        # overhead — generously bounded well under half the old sequential
        # cost, so this fails loudly if the gather-based fan-out regresses
        # back to a sequential await-per-artifact loop.
        assert elapsed < sequential_baseline / 2, (
            f"expected concurrent uploads (~{self.UPLOAD_DELAY_S}s) to beat "
            f"the sequential baseline ({sequential_baseline}s) by 2x+, got {elapsed:.3f}s"
        )
        assert elapsed < self.UPLOAD_DELAY_S * 2

    async def test_all_variant_rows_persisted_correctly_when_parallelized(self):
        """Parallelizing uploads must not scramble which row lands on which
        breakpoint, or drop/duplicate any artifact."""
        preset = PRESET_REGISTRY["category"]
        image = _mock_image()
        db = _mock_db()
        generated_by_breakpoint = _generated_variants_for(preset)

        async def _fast_put_variant(key, content, *, fmt):
            return None

        with (
            patch("app.modules.media.background.PILImage.open") as pil_open,
            patch(
                "app.modules.media.background.apply_geometry", return_value=MagicMock()
            ),
            patch(
                "app.modules.media.background.generate_variants_for_breakpoint",
                side_effect=lambda cropped, specs, bp: generated_by_breakpoint[bp],
            ),
            patch(
                "app.modules.media.background.storage.build_variant_key",
                return_value="images/category/category/none/x/desktop/thumbnail.webp",
            ),
            patch(
                "app.modules.media.background.storage.put_variant",
                new=AsyncMock(side_effect=_fast_put_variant),
            ),
            patch(
                "app.modules.media.background.storage.public_url",
                return_value="https://cdn/x.webp",
            ),
            patch.object(
                background._repo, "replace_variants", new=AsyncMock()
            ) as replace_variants,
            patch.object(
                background._repo, "get_image", new=AsyncMock(return_value=image)
            ),
            patch.object(background._repo, "update_fields", new=AsyncMock()),
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

        # replace_variants called once per breakpoint, each with exactly its
        # own 3 variant rows, all status='ready'.
        assert replace_variants.await_count == len(preset.breakpoints)
        calls_by_breakpoint = {
            c.args[2]: c.args[3] for c in replace_variants.await_args_list
        }
        assert set(calls_by_breakpoint) == {bp.value for bp in preset.breakpoints}
        for bp in preset.breakpoints:
            rows = calls_by_breakpoint[bp.value]
            assert len(rows) == 3
            assert {r["breakpoint"] for r in rows} == {bp.value}
            assert all(r["status"] == "ready" for r in rows)
            assert {r["variant_name"] for r in rows} == {
                spec.name for spec in preset.output_variants
            }
