"""Tests for app.tasks.maintenance.manage_partitions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from celery.app.task import Task
from redis.exceptions import ConnectionError as RedisConnectionError

from app.tasks.maintenance import manage_partitions


def _fake_retry(self, exc=None, **kwargs):
    raise exc


class TestManagePartitions:
    def test_success_calls_worker_run(self):
        with patch(
            "app.tasks.maintenance.partition_manager.run", new=AsyncMock()
        ) as run_mock:
            manage_partitions()
        run_mock.assert_awaited_once()

    def test_transient_db_error_calls_task_retry(self):
        exc = RedisConnectionError("down")
        with (
            patch(
                "app.tasks.maintenance.partition_manager.run",
                new=AsyncMock(side_effect=exc),
            ),
            patch("app.tasks.maintenance.backoff_seconds", return_value=0),
            patch.object(Task, "retry", _fake_retry),
        ):
            with pytest.raises(RedisConnectionError):
                manage_partitions()

    def test_non_transient_error_propagates_without_retry(self):
        with patch(
            "app.tasks.maintenance.partition_manager.run",
            new=AsyncMock(side_effect=ValueError("DDL permission denied")),
        ):
            with pytest.raises(ValueError):
                manage_partitions()
