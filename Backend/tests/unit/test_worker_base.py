"""Unit tests for workers/base.py run_with_session helper."""

from unittest.mock import AsyncMock, patch


class TestRunWithSession:
    async def test_success_calls_fn_with_db(self):
        from app.workers.base import run_with_session

        received_db = []

        async def fn(db):
            received_db.append(db)

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.workers.base.AsyncSessionLocal", return_value=mock_db):
            await run_with_session(fn)

        assert len(received_db) == 1

    async def test_exception_calls_rollback(self):
        from app.workers.base import run_with_session

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        async def failing_fn(db):
            raise RuntimeError("worker failure")

        with patch("app.workers.base.AsyncSessionLocal", return_value=mock_db):
            # Should not raise — exceptions are caught and logged
            await run_with_session(failing_fn)

        mock_db.rollback.assert_called_once()

    async def test_exception_does_not_propagate(self):
        from app.workers.base import run_with_session

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        async def always_raises(db):
            raise ValueError("something went wrong")

        with patch("app.workers.base.AsyncSessionLocal", return_value=mock_db):
            # Must not raise
            await run_with_session(always_raises)
