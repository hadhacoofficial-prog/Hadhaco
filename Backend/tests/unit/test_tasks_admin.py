"""Tests for app.tasks.admin.cleanup_sessions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from celery.app.task import Task
from redis.exceptions import ConnectionError as RedisConnectionError

from app.tasks.admin import cleanup_sessions


def _fake_retry(self, exc=None, **kwargs):
    """Stand-in for Task.retry that raises the given exception directly,
    so a test can assert retry() was reached without depending on Celery's
    eager-vs-worker retry-dispatch nuances (Task.retry behaves differently
    when a task is invoked directly vs. through the broker)."""
    raise exc


class TestCleanupSessions:
    def test_success_calls_worker_run(self):
        with patch(
            "app.tasks.admin.admin_session_cleanup.run", new=AsyncMock()
        ) as run_mock:
            cleanup_sessions()
        run_mock.assert_awaited_once()

    def test_transient_db_error_calls_task_retry(self):
        exc = RedisConnectionError("down")
        with (
            patch(
                "app.tasks.admin.admin_session_cleanup.run",
                new=AsyncMock(side_effect=exc),
            ),
            patch("app.tasks.admin.backoff_seconds", return_value=0),
            patch.object(Task, "retry", _fake_retry),
        ):
            with pytest.raises(RedisConnectionError):
                cleanup_sessions()

    def test_non_transient_error_propagates_without_retry(self):
        with patch(
            "app.tasks.admin.admin_session_cleanup.run",
            new=AsyncMock(side_effect=ValueError("business logic bug")),
        ):
            with pytest.raises(ValueError):
                cleanup_sessions()
