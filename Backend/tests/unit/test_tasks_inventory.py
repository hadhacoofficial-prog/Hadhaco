"""Tests for app.tasks.inventory.expire_reservations."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from celery.app.task import Task
from redis.exceptions import ConnectionError as RedisConnectionError

from app.tasks.inventory import expire_reservations


def _fake_retry(self, exc=None, **kwargs):
    raise exc


class TestExpireReservations:
    def test_success_calls_worker_run(self):
        """Business logic (SKIP LOCKED claim, exactly-once release) lives in
        app.workers.reservation_expiry.run, untouched by this migration —
        this task is a thin wrapper, so only the wrapper's own behavior is
        under test here."""
        with patch(
            "app.tasks.inventory.reservation_expiry.run", new=AsyncMock()
        ) as run_mock:
            expire_reservations()
        run_mock.assert_awaited_once()

    def test_transient_db_error_calls_task_retry(self):
        exc = RedisConnectionError("down")
        with (
            patch(
                "app.tasks.inventory.reservation_expiry.run",
                new=AsyncMock(side_effect=exc),
            ),
            patch("app.tasks.inventory.backoff_seconds", return_value=0),
            patch.object(Task, "retry", _fake_retry),
        ):
            with pytest.raises(RedisConnectionError):
                expire_reservations()

    def test_non_transient_error_left_for_next_beat_tick(self):
        """A business-logic failure is not Celery-retried immediately — it
        propagates so the next Beat tick (15s later) picks up the same
        still-expired reservation via the idempotent SKIP LOCKED claim,
        rather than racing a retry against itself."""
        with patch(
            "app.tasks.inventory.reservation_expiry.run",
            new=AsyncMock(side_effect=RuntimeError("unexpected state")),
        ):
            with pytest.raises(RuntimeError):
                expire_reservations()
