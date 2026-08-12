"""Tests for app.modules.media.repository.ImageRepository's background
generation queue methods (CB-1 Phase 2): try_claim_pending,
reclaim_stale_processing, list_pending_images, mark_generation_failed.

Mocked AsyncSession, no real DB required — mirrors tests/unit/test_repositories.py's
style (`db.execute` side_effect returns canned per-call results)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.media.repository import ImageRepository

pytestmark = pytest.mark.asyncio


def _scalar_one_or_none(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


class TestTryClaimPending:
    def setup_method(self):
        self.repo = ImageRepository()

    async def test_returns_none_when_nothing_claimable(self):
        """0 rows matched status='pending' — already claimed, finished, or
        gone. Must not go on to fetch/mutate anything."""
        image_id = uuid.uuid4()
        db = _db(_scalar_one_or_none(None))

        result = await self.repo.try_claim_pending(db, image_id)

        assert result is None
        db.execute.assert_awaited_once()

    async def test_claims_and_bumps_attempts(self):
        """A successful claim increments metadata_["generation"]["attempts"]
        and stamps started_at, so the retry-limit check in the worker sees
        an accurate count even if generation itself later fails."""
        image_id = uuid.uuid4()
        mock_image = MagicMock()
        mock_image.metadata_ = {"crops": {}, "generation": {"attempts": 1}}

        db = _db(
            _scalar_one_or_none(image_id),  # the UPDATE...RETURNING
            _scalar_one_or_none(mock_image),  # the get_image() re-fetch
        )

        result = await self.repo.try_claim_pending(db, image_id)

        assert result is mock_image
        assert mock_image.metadata_["generation"]["attempts"] == 2
        assert "started_at" in mock_image.metadata_["generation"]
        # Original metadata (crops) preserved, not clobbered.
        assert "crops" in mock_image.metadata_
        db.add.assert_called_once_with(mock_image)

    async def test_returns_none_when_image_vanishes_after_claim(self):
        """Claimed the row (UPDATE matched), but the follow-up SELECT
        (scoped to deleted_at IS NULL) finds nothing — a soft-delete raced
        in between. Must not crash trying to bump metadata on None."""
        image_id = uuid.uuid4()
        db = _db(
            _scalar_one_or_none(image_id),
            _scalar_one_or_none(None),
        )

        result = await self.repo.try_claim_pending(db, image_id)

        assert result is None


class TestReclaimStaleProcessing:
    def setup_method(self):
        self.repo = ImageRepository()

    async def test_returns_count_of_reclaimed_images(self):
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        db = _db(_scalars_result(ids))

        count = await self.repo.reclaim_stale_processing(db, stale_after_seconds=120)

        assert count == 3
        db.execute.assert_awaited_once()

    async def test_returns_zero_when_nothing_stale(self):
        db = _db(_scalars_result([]))

        count = await self.repo.reclaim_stale_processing(db, stale_after_seconds=120)

        assert count == 0

    async def test_query_shape_only_matches_stale_processing_rows(self):
        """No live DB in this suite (see tests/conftest.py), so this proves
        the built statement's WHERE/SET clauses are structurally correct —
        the actual row-filtering is then a property of Postgres executing
        that (proven-correct) SQL, not something a mocked db.execute can
        exercise directly.

        Specifically proves:
        - a 'ready'/'pending'/'failed' row can never match (WHERE binds
          status == 'processing' only) — covers "completed image untouched"
        - a 'processing' row whose updated_at is *at or after* the cutoff
          can never match (WHERE binds updated_at < cutoff, cutoff computed
          from stale_after_seconds at call time) — covers "fresh processing
          image untouched"
        - matched rows are set back to 'pending', not any other status
        """
        db = _db(_scalars_result([]))
        before_call = datetime.now(UTC)

        await self.repo.reclaim_stale_processing(db, stale_after_seconds=120)

        after_call = datetime.now(UTC)
        stmt = db.execute.call_args.args[0]
        params = stmt.compile().params

        assert params["status_1"] == "processing"
        assert params["status"] == "pending"
        # cutoff must be ~120s before "now" at call time, not e.g. 120s in
        # the future or unrelated to stale_after_seconds entirely.
        cutoff = params["updated_at_1"]
        assert (
            before_call - timedelta(seconds=121)
            <= cutoff
            <= after_call - timedelta(seconds=119)
        )


class TestListPendingImages:
    def setup_method(self):
        self.repo = ImageRepository()

    async def test_returns_pending_images(self):
        images = [MagicMock(), MagicMock()]
        db = _db(_scalars_result(images))

        result = await self.repo.list_pending_images(db, limit=20)

        assert result == images

    async def test_query_shape_excludes_non_pending_and_deleted_rows(self):
        """Statement-shape check (see docstring above) — proves 'ready'/
        'processing'/'failed' rows (WHERE binds status == 'pending' only)
        and soft-deleted rows (WHERE includes deleted_at IS NULL) can never
        match, structurally."""
        db = _db(_scalars_result([]))

        await self.repo.list_pending_images(db, limit=20)

        stmt = db.execute.call_args.args[0]
        assert stmt.compile().params["status_1"] == "pending"
        assert "deleted_at IS NULL" in str(stmt)


class TestSoftDeleteNeverLeavesAProcessingStatus:
    """reclaim_stale_processing's WHERE clause doesn't filter on deleted_at
    at all — it doesn't need to, because soft_delete unconditionally flips
    status away from 'processing' in the same write. Proves that invariant
    directly, since it's what actually keeps a deleted image safe from
    being reclaimed, not a filter in the reclaim query itself."""

    def setup_method(self):
        self.repo = ImageRepository()

    async def test_soft_delete_sets_status_to_archived_not_processing(self):
        image = MagicMock()
        image.status = "processing"
        db = AsyncMock()
        db.add = MagicMock()

        await self.repo.soft_delete(db, image)

        assert image.status == "archived"
        assert image.deleted_at is not None


class TestMarkGenerationFailed:
    def setup_method(self):
        self.repo = ImageRepository()

    async def test_records_error_and_sets_failed_status(self):
        image = MagicMock()
        image.metadata_ = {"crops": {}, "generation": {"attempts": 3}}
        db = AsyncMock()
        db.add = MagicMock()

        await self.repo.mark_generation_failed(db, image, "boom: corrupt original")

        assert image.status == "failed"
        assert image.metadata_["generation"]["last_error"] == "boom: corrupt original"
        assert "finished_at" in image.metadata_["generation"]
        # Attempt count from the claim is preserved, not reset.
        assert image.metadata_["generation"]["attempts"] == 3
        db.add.assert_called_once_with(image)
        db.flush.assert_awaited_once()


class TestUpdateMetadata:
    """update_metadata's `refresh` kwarg skips the two post-flush reload
    round-trips when the caller knows another write to the same image
    follows immediately (UniversalImageService.crop() with changed
    breakpoints) — flush() must still always run so that next write sees
    the change, but refresh()/refresh(variants) should be skippable."""

    def setup_method(self):
        self.repo = ImageRepository()

    def _image(self):
        image = MagicMock()
        image.version = 1
        image.metadata_ = {}
        return image

    async def test_default_refreshes_scalars_and_variants(self):
        image = self._image()
        db = _db()

        result = await self.repo.update_metadata(db, image, {"crops": {}})

        assert result is image
        assert image.metadata_ == {"crops": {}}
        assert image.version == 2
        db.flush.assert_awaited_once()
        assert db.refresh.await_count == 2
        db.refresh.assert_any_await(image)
        db.refresh.assert_any_await(image, attribute_names=["variants"])

    async def test_refresh_false_flushes_but_skips_both_reloads(self):
        image = self._image()
        db = _db()

        result = await self.repo.update_metadata(
            db, image, {"crops": {"desktop": {}}}, refresh=False
        )

        assert result is image
        assert image.metadata_ == {"crops": {"desktop": {}}}
        assert image.version == 2
        db.flush.assert_awaited_once()
        db.refresh.assert_not_awaited()


class TestReplaceVariants:
    """replace_variants upserts (INSERT ... ON CONFLICT DO UPDATE) instead of
    delete-then-insert, specifically to stay race-safe when two
    media-generation jobs for the same image run concurrently (e.g. an
    upload's initial generation overlapping a crop triggered moments later)
    — see app/modules/media/repository.py's docstring for the full story.
    Mocked AsyncSession, no real DB required."""

    def setup_method(self):
        self.repo = ImageRepository()

    def _existing_variant(self, variant_name: str, dpr: int):
        v = MagicMock()
        v.variant_name = variant_name
        v.dpr = dpr
        return v

    async def test_upserts_new_rows_without_deleting_anything(self):
        """No pre-existing rows for this breakpoint — the upsert INSERT runs,
        the stale-cleanup SELECT finds nothing, no db.delete calls at all."""
        image = MagicMock()
        image.id = uuid.uuid4()
        db = _db(MagicMock(), _scalars_result([]))  # insert result, then SELECT result

        rows = [
            {
                "id": uuid.uuid4(),
                "breakpoint": "desktop",
                "variant_name": "thumbnail",
                "dpr": 1,
                "format": "webp",
                "url": "https://cdn/x@1x.webp",
                "width": 200,
                "height": 200,
                "size_bytes": 1234,
                "status": "ready",
                "error_message": None,
            }
        ]

        await self.repo.replace_variants(db, image, "desktop", rows)

        assert db.execute.await_count == 2  # upsert INSERT, then stale-cleanup SELECT
        db.delete.assert_not_awaited()
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once_with(image, attribute_names=["variants"])

    async def test_deletes_only_stale_rows_not_in_new_set(self):
        """A variant (variant_name='medium', dpr=1) that the new generation
        no longer produces gets deleted; one still present in the new set
        is left alone — proves the cleanup is scoped by key, not blanket."""
        image = MagicMock()
        image.id = uuid.uuid4()
        stale = self._existing_variant("medium", 1)
        kept = self._existing_variant("thumbnail", 1)
        db = _db(MagicMock(), _scalars_result([stale, kept]))

        rows = [
            {
                "id": uuid.uuid4(),
                "breakpoint": "desktop",
                "variant_name": "thumbnail",
                "dpr": 1,
                "format": "webp",
                "url": "https://cdn/x@1x.webp",
                "width": 200,
                "height": 200,
                "size_bytes": 1234,
                "status": "ready",
                "error_message": None,
            }
        ]

        await self.repo.replace_variants(db, image, "desktop", rows)

        db.delete.assert_awaited_once_with(stale)

    async def test_empty_variant_rows_skips_insert_but_still_cleans_up(self):
        """No new rows to upsert — the insert statement must not run (an
        empty VALUES() list is invalid SQL) but stale-row cleanup and the
        final flush/refresh still happen."""
        image = MagicMock()
        image.id = uuid.uuid4()
        existing = self._existing_variant("thumbnail", 1)
        db = _db(_scalars_result([existing]))  # only the SELECT this time

        await self.repo.replace_variants(db, image, "desktop", [])

        assert db.execute.await_count == 1  # SELECT only, no insert
        db.delete.assert_awaited_once_with(existing)
        db.flush.assert_awaited_once()
