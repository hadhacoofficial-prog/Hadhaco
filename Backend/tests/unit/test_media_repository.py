"""Tests for app.modules.media.repository.ImageRepository's background
generation queue methods (CB-1 Phase 2): try_claim_pending,
reclaim_stale_processing, list_pending_images, mark_generation_failed.

Mocked AsyncSession, no real DB required — mirrors tests/unit/test_repositories.py's
style (`db.execute` side_effect returns canned per-call results)."""

import uuid
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


class TestListPendingImages:
    def setup_method(self):
        self.repo = ImageRepository()

    async def test_returns_pending_images(self):
        images = [MagicMock(), MagicMock()]
        db = _db(_scalars_result(images))

        result = await self.repo.list_pending_images(db, limit=20)

        assert result == images


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
