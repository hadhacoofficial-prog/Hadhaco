"""Tests for app.tasks.media (sweep_pending, generate_variants)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from celery.app.task import Task
from redis.exceptions import ConnectionError as RedisConnectionError

from app.tasks.media import generate_variants, sweep_pending


def _fake_retry(self, exc=None, **kwargs):
    raise exc


class TestSweepPending:
    def test_success_calls_worker_run(self):
        with patch("app.tasks.media.media_generation.run", new=AsyncMock()) as run_mock:
            sweep_pending()
        run_mock.assert_awaited_once()

    def test_transient_db_error_calls_task_retry(self):
        exc = RedisConnectionError("down")
        with (
            patch(
                "app.tasks.media.media_generation.run", new=AsyncMock(side_effect=exc)
            ),
            patch("app.tasks.media.backoff_seconds", return_value=0),
            patch.object(Task, "retry", _fake_retry),
        ):
            with pytest.raises(RedisConnectionError):
                sweep_pending()


class TestGenerateVariants:
    def test_parses_str_image_id_to_uuid_and_calls_process_one(self):
        """Dispatched with .delay(str(image_id)) from universal_service.py —
        JSON serialization means the argument arrives as a plain str, which
        must round-trip back to the UUID process_one/ImageRepository expect."""
        image_id = uuid.uuid4()
        with patch(
            "app.tasks.media.media_generation.process_one", new=AsyncMock()
        ) as process_one:
            generate_variants(str(image_id))
        process_one.assert_awaited_once_with(image_id)

    def test_claim_race_with_sweep_is_a_safe_no_op(self):
        """If the periodic sweep already claimed this image before the fast
        path's task runs, try_claim_pending (inside process_one) is a no-op
        — process_one itself handles this, so the task wrapper just needs to
        not treat a clean no-op return as an error."""
        image_id = uuid.uuid4()
        with patch(
            "app.tasks.media.media_generation.process_one",
            new=AsyncMock(return_value=None),
        ) as process_one:
            generate_variants(str(image_id))  # must not raise
        process_one.assert_awaited_once_with(image_id)

    def test_transient_error_calls_task_retry(self):
        image_id = uuid.uuid4()
        exc = RedisConnectionError("down")
        with (
            patch(
                "app.tasks.media.media_generation.process_one",
                new=AsyncMock(side_effect=exc),
            ),
            patch("app.tasks.media.backoff_seconds", return_value=0),
            patch.object(Task, "retry", _fake_retry),
        ):
            with pytest.raises(RedisConnectionError):
                generate_variants(str(image_id))

    def test_non_transient_error_propagates(self):
        """A genuine generation failure is handled entirely inside
        process_one/_handle_failure (DB-tracked MAX_ATTEMPTS) — anything that
        still escapes is not Celery-retried past that, since process_one
        already decided permanent-failure vs. reset-to-pending."""
        image_id = uuid.uuid4()
        with patch(
            "app.tasks.media.media_generation.process_one",
            new=AsyncMock(side_effect=ValueError("corrupt image")),
        ):
            with pytest.raises(ValueError):
                generate_variants(str(image_id))
