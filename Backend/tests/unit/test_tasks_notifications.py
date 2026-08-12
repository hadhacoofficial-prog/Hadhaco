"""Tests for app.tasks.notifications.retry_failed and its single-flight lock.

The lock exists because NotificationRepository.get_pending_retries's
FOR UPDATE SKIP LOCKED only guards the initial SELECT — NotificationService
._retry_log commits after each row (to free the DB connection before its
HTTP call), releasing that row's lock before the next row in the same batch.
Two overlapping task runs could otherwise both process the same batch and
double-send a customer notification. See app/tasks/notifications.py's
module docstring and Docs/CELERY_MIGRATION_PLAN.md §10/§11.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.app.task import Task
from redis.exceptions import ConnectionError as RedisConnectionError

from app.tasks.notifications import retry_failed


def _fake_retry(self, exc=None, **kwargs):
    raise exc


def _redis_mock(*, acquire: bool) -> MagicMock:
    redis = MagicMock()
    redis.set = AsyncMock(return_value=acquire)
    redis.delete = AsyncMock(return_value=1)
    return redis


class TestSingleFlightLock:
    def test_runs_and_releases_lock_when_acquired(self):
        redis = _redis_mock(acquire=True)
        with (
            patch("app.tasks.notifications.redis_available", return_value=True),
            patch("app.tasks.notifications.get_redis_pool", return_value=redis),
            patch(
                "app.tasks.notifications.notification_retry.run", new=AsyncMock()
            ) as run_mock,
        ):
            retry_failed()

        run_mock.assert_awaited_once()
        redis.set.assert_awaited_once_with(
            "hadha:tasks:notifications.retry_failed:lock", "1", nx=True, ex=150
        )
        redis.delete.assert_awaited_once_with(
            "hadha:tasks:notifications.retry_failed:lock"
        )

    def test_skips_run_when_another_instance_holds_the_lock(self):
        redis = _redis_mock(acquire=False)
        with (
            patch("app.tasks.notifications.redis_available", return_value=True),
            patch("app.tasks.notifications.get_redis_pool", return_value=redis),
            patch(
                "app.tasks.notifications.notification_retry.run", new=AsyncMock()
            ) as run_mock,
        ):
            retry_failed()

        run_mock.assert_not_awaited()
        redis.delete.assert_not_awaited()

    def test_fail_open_when_redis_unavailable(self):
        """A Redis outage must not silently stop notification retries from
        ever running — same fail-open contract as the former WorkerLeader."""
        with (
            patch("app.tasks.notifications.redis_available", return_value=False),
            patch(
                "app.tasks.notifications.notification_retry.run", new=AsyncMock()
            ) as run_mock,
        ):
            retry_failed()

        run_mock.assert_awaited_once()

    def test_lock_released_even_when_run_raises(self):
        redis = _redis_mock(acquire=True)
        with (
            patch("app.tasks.notifications.redis_available", return_value=True),
            patch("app.tasks.notifications.get_redis_pool", return_value=redis),
            patch(
                "app.tasks.notifications.notification_retry.run",
                new=AsyncMock(side_effect=RuntimeError("db gone")),
            ),
        ):
            with pytest.raises(RuntimeError):
                retry_failed()

        redis.delete.assert_awaited_once_with(
            "hadha:tasks:notifications.retry_failed:lock"
        )


class TestRetryFailedTaskRetrySemantics:
    def test_transient_error_calls_task_retry(self):
        redis = _redis_mock(acquire=True)
        exc = RedisConnectionError("down")
        with (
            patch("app.tasks.notifications.redis_available", return_value=True),
            patch("app.tasks.notifications.get_redis_pool", return_value=redis),
            patch(
                "app.tasks.notifications.notification_retry.run",
                new=AsyncMock(side_effect=exc),
            ),
            patch("app.tasks.notifications.backoff_seconds", return_value=0),
            patch.object(Task, "retry", _fake_retry),
        ):
            with pytest.raises(RedisConnectionError):
                retry_failed()

    def test_non_transient_error_propagates_without_celery_retry(self):
        """Provider send failures are handled by NotificationService's own
        attempt_count/next_retry_at backoff, never by a Celery-level retry —
        stacking one on top would risk re-running the sweep before
        next_retry_at updates, i.e. a duplicate customer-facing send."""
        redis = _redis_mock(acquire=True)
        with (
            patch("app.tasks.notifications.redis_available", return_value=True),
            patch("app.tasks.notifications.get_redis_pool", return_value=redis),
            patch(
                "app.tasks.notifications.notification_retry.run",
                new=AsyncMock(side_effect=ValueError("template render bug")),
            ),
        ):
            with pytest.raises(ValueError):
                retry_failed()
