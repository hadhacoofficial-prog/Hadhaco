"""Tests for app.tasks.cms.publish_scheduled."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from celery.app.task import Task
from redis.exceptions import ConnectionError as RedisConnectionError

from app.tasks.cms import publish_scheduled


def _fake_retry(self, exc=None, **kwargs):
    raise exc


class TestPublishScheduled:
    def test_success_calls_worker_run(self):
        with patch("app.tasks.cms.cms_publish.run", new=AsyncMock()) as run_mock:
            publish_scheduled()
        run_mock.assert_awaited_once()

    def test_transient_db_error_calls_task_retry(self):
        exc = RedisConnectionError("down")
        with (
            patch("app.tasks.cms.cms_publish.run", new=AsyncMock(side_effect=exc)),
            patch("app.tasks.cms.backoff_seconds", return_value=0),
            patch.object(Task, "retry", _fake_retry),
        ):
            with pytest.raises(RedisConnectionError):
                publish_scheduled()

    def test_non_transient_error_propagates_without_retry(self):
        with patch(
            "app.tasks.cms.cms_publish.run",
            new=AsyncMock(side_effect=ValueError("business logic bug")),
        ):
            with pytest.raises(ValueError):
                publish_scheduled()
