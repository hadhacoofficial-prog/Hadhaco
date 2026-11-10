"""Tests for app.workers.media_generation — the background variant-
generation worker (CB-1 Phase 2): claim-and-generate, retry-on-failure, and
crash recovery (reclaim_stale_processing). The Celery-dispatched fast path
(app.tasks.media.generate_variants) is a thin wrapper around process_one()
and is tested in tests/unit/test_tasks_media.py."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _session_cm(db):
    """Mock for `AsyncSessionLocal()` used as `async with ... as db`."""
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
                "app.workers.media_generation.AsyncSessionLocal",
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
                "app.workers.media_generation.AsyncSessionLocal",
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
                "app.workers.media_generation.AsyncSessionLocal",
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
                "app.workers.media_generation.AsyncSessionLocal",
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


class TestRun:
    """run() now reclaims + discovers pending images in one AsyncSession/
    transaction instead of two separate ones (Docs/MEDIA_SWEEP_OPTIMIZATION_REPORT.md)
    — these tests pin that: exactly one session opened, exactly one commit,
    reclaim's rollback-on-failure semantics preserved, and every downstream
    process_one() call still happens exactly as before."""

    def _run_mocks(self, db, *, reclaimed=0, pending=()):
        from app.workers import media_generation

        session_ctor = MagicMock(return_value=_session_cm(db))
        return (
            patch("app.workers.media_generation.AsyncSessionLocal", session_ctor),
            session_ctor,
            patch.object(
                media_generation._repo,
                "reclaim_stale_processing",
                new=AsyncMock(return_value=reclaimed),
            ),
            patch.object(
                media_generation._repo,
                "list_pending_images",
                new=AsyncMock(return_value=list(pending)),
            ),
        )

    async def test_reclaims_stale_then_processes_each_pending_id(self):
        """Scenario: multiple pending images. Also pins the merged-session
        behavior: exactly one AsyncSessionLocal() call, exactly one commit."""
        from app.workers import media_generation

        db = _mock_db()
        pending_a, pending_b = MagicMock(), MagicMock()
        pending_a.id = uuid.uuid4()
        pending_b.id = uuid.uuid4()
        p_session, session_ctor, p_reclaim, p_list = self._run_mocks(
            db, reclaimed=0, pending=[pending_a, pending_b]
        )

        with (
            p_session,
            p_reclaim,
            p_list,
            patch(
                "app.workers.media_generation.process_one", new=AsyncMock()
            ) as process_one,
        ):
            await media_generation.run()

        assert process_one.await_count == 2
        process_one.assert_any_call(pending_a.id)
        process_one.assert_any_call(pending_b.id)
        session_ctor.assert_called_once()
        db.commit.assert_awaited_once()
        db.rollback.assert_not_awaited()

    async def test_no_pending_or_stale_images_processes_nothing(self):
        """Scenario: no pending images at all. The session still opens,
        runs both (empty-result) queries, and commits cleanly — no error,
        no process_one calls."""
        from app.workers import media_generation

        db = _mock_db()
        p_session, session_ctor, p_reclaim, p_list = self._run_mocks(
            db, reclaimed=0, pending=[]
        )

        with (
            p_session,
            p_reclaim,
            p_list,
            patch(
                "app.workers.media_generation.process_one", new=AsyncMock()
            ) as process_one,
        ):
            await media_generation.run()

        process_one.assert_not_awaited()
        db.commit.assert_awaited_once()

    async def test_stale_and_pending_images_together_processes_all_pending_ids(self):
        """Scenario: a stale 'processing' row and independently-pending rows
        in the same tick. Within the merged transaction, list_pending_images
        runs *after* reclaim_stale_processing and would see rows the reclaim
        just flipped to 'pending' (same-transaction read-your-own-writes) —
        here that's simulated by list's mocked return already including the
        reclaimed image's id, since the two repo calls are independently
        mocked at this layer; the ordering itself is asserted via call order
        below."""
        from app.workers import media_generation

        db = _mock_db()
        reclaimed_then_pending, already_pending = MagicMock(), MagicMock()
        reclaimed_then_pending.id = uuid.uuid4()
        already_pending.id = uuid.uuid4()
        call_order: list[str] = []

        async def _reclaim(*a, **k):
            call_order.append("reclaim")
            return 1

        async def _list(*a, **k):
            call_order.append("list")
            return [reclaimed_then_pending, already_pending]

        with (
            patch(
                "app.workers.media_generation.AsyncSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo, "reclaim_stale_processing", side_effect=_reclaim
            ),
            patch.object(
                media_generation._repo, "list_pending_images", side_effect=_list
            ),
            patch(
                "app.workers.media_generation.process_one", new=AsyncMock()
            ) as process_one,
        ):
            await media_generation.run()

        assert call_order == ["reclaim", "list"]
        assert process_one.await_count == 2
        process_one.assert_any_call(reclaimed_then_pending.id)
        process_one.assert_any_call(already_pending.id)

    async def test_list_failure_after_reclaim_rolls_back_and_skips_processing(self):
        """Scenario: task failure/rollback. If list_pending_images raises
        after a successful reclaim, the whole transaction (including the
        reclaim's UPDATE) rolls back rather than partially committing — the
        image is simply re-reclaimed next tick (self-healing, see run()'s
        docstring), not lost. No process_one call, no commit."""
        import asyncpg

        from app.workers import media_generation

        db = _mock_db()

        with (
            patch(
                "app.workers.media_generation.AsyncSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "reclaim_stale_processing",
                new=AsyncMock(return_value=1),
            ),
            patch.object(
                media_generation._repo,
                "list_pending_images",
                new=AsyncMock(
                    side_effect=asyncpg.exceptions.PostgresError("connection reset")
                ),
            ),
            patch(
                "app.workers.media_generation.process_one", new=AsyncMock()
            ) as process_one,
        ):
            await media_generation.run()

        process_one.assert_not_awaited()
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    async def test_non_transient_reclaim_error_is_logged_and_swallowed(self):
        """A non-transient exception must not propagate out of run() (Celery
        would otherwise treat it as a task failure needing its own handling)
        — it's rolled back and swallowed, same as before the session merge."""
        from app.workers import media_generation

        db = _mock_db()

        with (
            patch(
                "app.workers.media_generation.AsyncSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "reclaim_stale_processing",
                new=AsyncMock(side_effect=ValueError("unexpected")),
            ),
            patch.object(
                media_generation._repo, "list_pending_images", new=AsyncMock()
            ),
            patch(
                "app.workers.media_generation.process_one", new=AsyncMock()
            ) as process_one,
        ):
            await media_generation.run()  # must not raise

        process_one.assert_not_awaited()
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_repeated_execution_is_idempotent(self):
        """Scenario: idempotent repeated execution. Two consecutive run()
        calls — the second finds nothing left to do (as a real second tick
        would, once the first tick's images are no longer 'pending') — must
        not double-process or error."""
        from app.workers import media_generation

        db = _mock_db()
        pending = MagicMock()
        pending.id = uuid.uuid4()

        with (
            patch(
                "app.workers.media_generation.AsyncSessionLocal",
                return_value=_session_cm(db),
            ),
            patch.object(
                media_generation._repo,
                "reclaim_stale_processing",
                new=AsyncMock(side_effect=[1, 0]),
            ),
            patch.object(
                media_generation._repo,
                "list_pending_images",
                new=AsyncMock(side_effect=[[pending], []]),
            ),
            patch(
                "app.workers.media_generation.process_one", new=AsyncMock()
            ) as process_one,
        ):
            await media_generation.run()
            await media_generation.run()

        assert process_one.await_count == 1
        process_one.assert_awaited_once_with(pending.id)
        assert db.commit.await_count == 2
