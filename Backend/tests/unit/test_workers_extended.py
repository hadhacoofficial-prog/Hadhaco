"""Extended worker tests covering run() functions with mocked DB sessions."""

from unittest.mock import AsyncMock, MagicMock, patch


def _make_session_mock():
    """Return a mock that acts as an async context manager."""
    mock_db = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    return mock_db


class TestPartitionManagerWorker:
    async def test_run_executes_two_sql_statements(self):
        import app.workers.partition_manager as worker

        mock_db = _make_session_mock()
        execute_calls = []

        async def capture_execute(sql, *args, **kwargs):
            execute_calls.append(sql)
            return MagicMock()

        mock_db.execute = capture_execute
        mock_db.commit = AsyncMock()

        with patch(
            "app.workers.partition_manager.AsyncSessionLocal",
            return_value=mock_db,
        ):
            await worker.run()

        assert len(execute_calls) == 2
