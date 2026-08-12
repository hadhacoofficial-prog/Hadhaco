"""P0-0 measurement: slow-SQL WARN logging + periodic metrics drain."""

from unittest.mock import patch

from app.core.profiling import profiler


def test_record_query_emits_warn_for_slow_sql():
    profiler.reset()
    with patch("app.core.profiling._slow_sql_log.warning") as warn:
        profiler.record_query(350.0, "SELECT 1 -- slow", slow_threshold_ms=200.0)
        warn.assert_called_once()
        args, kwargs = warn.call_args
        assert args[0] == "slow_sql"
        assert kwargs["duration_ms"] == 350.0
        assert kwargs["query"] == "SELECT 1 -- slow"
    profiler.reset()


def test_record_query_does_not_warn_for_fast_sql():
    profiler.reset()
    with patch("app.core.profiling._slow_sql_log.warning") as warn:
        profiler.record_query(5.0, "SELECT 1", slow_threshold_ms=200.0)
        warn.assert_not_called()
    profiler.reset()


def test_slow_sql_always_lands_in_global_deque(caplog):
    profiler.reset()
    with patch("app.core.profiling._slow_sql_log.warning"):
        # No begin_request() — proves slow SQL is tracked outside request
        # contexts too (workers, event listeners).
        profiler.record_query(250.0, "SELECT 2", slow_threshold_ms=200.0)
        snapshot = profiler.snapshot()
        assert snapshot["slow_sql_top5"][0]["query"] == "SELECT 2"
    profiler.reset()


def test_slow_sql_logged_to_perf_logger_truncates_query():
    profiler.reset()
    long_query = "SELECT * FROM products WHERE title ILIKE '%" + "x" * 400 + "'"
    with patch("app.core.profiling._slow_sql_log.warning") as warn:
        profiler.record_query(250.0, long_query, slow_threshold_ms=200.0)
        warn.assert_called_once()
        args, kwargs = warn.call_args
        assert args[0] == "slow_sql"
        assert len(kwargs["query"]) <= 200
    profiler.reset()


def test_drain_metrics_emits_snapshot_info_line():
    profiler.reset()
    profiler.begin_request()
    profiler.record_query(12.0, "SELECT 3")
    profiler.end_request(path="/products", duration_ms=12.0)

    with patch("app.core.profiling._metrics_log.info") as info:
        profiler.drain_metrics()
        info.assert_called_once()
        args, kwargs = info.call_args
        assert args[0] == "metrics_drain"
        assert kwargs["requests_total"] == 1
        assert kwargs["sql"]["total_queries"] == 1
    profiler.reset()
