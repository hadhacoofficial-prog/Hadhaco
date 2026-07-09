"""Tests for app.workers.media_generation — the background variant-
generation worker (CB-1 Phase 2): claim-and-generate, retry-on-failure,
crash recovery (reclaim_stale_processing), and the asyncio.create_task
fast path (enqueue)."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _session_cm(db):
    """Mock for `AsyncWorkerSessionLocal()` used as `async with ... as db`."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


class TestProcessOneClaim:
    async def test_returns_early_when_claim_fails(self):
        """Something else (the fast path or another poll tick) already
        claimed or finished this image — a no-op, not an error."""
        from app.workers import media_generation

        db = _mock_db()
        image_id = uuid.uuid4()

        with (
            patch(
                "app.workers.media_generation.AsyncWorkerSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "try_claim_pending",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.workers.media_generation.background.generate_variants_for_breakpoints",
                new=AsyncMock(),
            ) as generate,
        ):
            await media_generation.process_one(image_id)

        generate.assert_not_awaited()
        db.commit.assert_awaited_once()


class TestProcessOneSuccess:
    async def test_generates_only_pending_breakpoints_and_commits_twice(self):
        """The claim (+ attempt bump) is committed immediately, separate
        from the generation commit, so a later failure can't roll back the
        attempt count along with the failed generation."""
        from app.modules.media.preset_registry import Breakpoint
        from app.workers import media_generation

        db = _mock_db()
        image_id = uuid.uuid4()
        image = MagicMock()
        image.id = image_id
        image.preset_id = "category"
        image.original_key = "images/category/category/x/y/original.jpg"
        image.metadata_ = {
            "crops": {},
            "generation": {"pending_breakpoints": ["desktop"], "attempts": 1},
        }

        with (
            patch(
                "app.workers.media_generation.AsyncWorkerSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "try_claim_pending",
                new=AsyncMock(return_value=image),
            ),
            patch(
                "app.workers.media_generation.storage.get_object_bytes",
                new=AsyncMock(return_value=b"orig"),
            ),
            patch(
                "app.workers.media_generation.background.parse_stored_crops",
                return_value={},
            ),
            patch(
                "app.workers.media_generation.background.generate_variants_for_breakpoints",
                new=AsyncMock(),
            ) as generate,
        ):
            await media_generation.process_one(image_id)

        generate.assert_awaited_once()
        _, _, _, _, _, breakpoints = generate.call_args.args
        assert breakpoints == [Breakpoint.DESKTOP]
        assert db.commit.await_count == 2  # claim, then post-generation


class TestProcessOneFailure:
    async def test_retries_when_below_max_attempts(self):
        from app.workers import media_generation

        db = _mock_db()
        image_id = uuid.uuid4()
        claimed = MagicMock()
        claimed.preset_id = "category"
        claimed.original_key = "k"
        claimed.metadata_ = {"generation": {"attempts": 1}}

        refetched = MagicMock()
        refetched.metadata_ = {"generation": {"attempts": 1}}

        with (
            patch(
                "app.workers.media_generation.AsyncWorkerSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "try_claim_pending",
                new=AsyncMock(return_value=claimed),
            ),
            patch(
                "app.workers.media_generation.storage.get_object_bytes",
                new=AsyncMock(side_effect=RuntimeError("R2 down")),
            ),
            patch.object(
                media_generation._repo,
                "get_image",
                new=AsyncMock(return_value=refetched),
            ),
            patch.object(
                media_generation._repo, "update_fields", new=AsyncMock()
            ) as update_fields,
            patch.object(
                media_generation._repo, "mark_generation_failed", new=AsyncMock()
            ) as mark_failed,
        ):
            await media_generation.process_one(image_id)

        update_fields.assert_awaited_once_with(db, refetched, {"status": "pending"})
        mark_failed.assert_not_awaited()

    async def test_marks_failed_after_max_attempts(self):
        from app.workers import media_generation

        db = _mock_db()
        image_id = uuid.uuid4()
        claimed = MagicMock()
        claimed.preset_id = "category"
        claimed.original_key = "k"
        claimed.metadata_ = {"generation": {"attempts": media_generation.MAX_ATTEMPTS}}

        refetched = MagicMock()
        refetched.metadata_ = {
            "generation": {"attempts": media_generation.MAX_ATTEMPTS}
        }

        with (
            patch(
                "app.workers.media_generation.AsyncWorkerSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "try_claim_pending",
                new=AsyncMock(return_value=claimed),
            ),
            patch(
                "app.workers.media_generation.storage.get_object_bytes",
                new=AsyncMock(side_effect=RuntimeError("corrupt original")),
            ),
            patch.object(
                media_generation._repo,
                "get_image",
                new=AsyncMock(return_value=refetched),
            ),
            patch.object(
                media_generation._repo, "update_fields", new=AsyncMock()
            ) as update_fields,
            patch.object(
                media_generation._repo, "mark_generation_failed", new=AsyncMock()
            ) as mark_failed,
        ):
            await media_generation.process_one(image_id)

        mark_failed.assert_awaited_once_with(db, refetched, "corrupt original")
        update_fields.assert_not_awaited()


class TestEnqueue:
    async def test_fires_task_and_tracks_strong_reference(self):
        """asyncio only weakly references a bare task — enqueue() must keep
        a strong reference until it completes, or the task can be
        garbage-collected mid-run."""
        from app.workers import media_generation

        image_id = uuid.uuid4()
        with patch(
            "app.workers.media_generation.process_one", new=AsyncMock()
        ) as process_one:
            media_generation.enqueue(image_id)
            assert len(media_generation._inflight_tasks) == 1
            await asyncio.sleep(0)  # let the task run to completion
            await asyncio.sleep(0)  # let the done-callback fire

        process_one.assert_awaited_once_with(image_id)
        assert len(media_generation._inflight_tasks) == 0


class TestRun:
    async def test_reclaims_stale_then_processes_each_pending_id(self):
        from app.workers import media_generation

        db = _mock_db()
        pending_a, pending_b = MagicMock(), MagicMock()
        pending_a.id = uuid.uuid4()
        pending_b.id = uuid.uuid4()

        with (
            patch(
                "app.workers.media_generation.AsyncWorkerSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "reclaim_stale_processing",
                new=AsyncMock(return_value=0),
            ),
            patch.object(
                media_generation._repo,
                "list_pending_images",
                new=AsyncMock(return_value=[pending_a, pending_b]),
            ),
            patch(
                "app.workers.media_generation.process_one", new=AsyncMock()
            ) as process_one,
        ):
            await media_generation.run()

        assert process_one.await_count == 2
        process_one.assert_any_call(pending_a.id)
        process_one.assert_any_call(pending_b.id)
