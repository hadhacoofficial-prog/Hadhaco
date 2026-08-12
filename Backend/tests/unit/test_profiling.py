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


def test_worker_context_queries_are_not_dropped_from_total():
    """Regression for RC-9 (Docs/CURRENT_SLOW_SQL_ROOT_CAUSE_ANALYSIS.md §8):
    a query recorded with no active request context (background worker,
    lifespan startup) used to vanish from sql.total_queries/total_ms even
    though sql_histogram counted it — total_queries must match the
    histogram's count, request-path SQL plus worker-context SQL."""
    profiler.reset()
    with patch("app.core.profiling._slow_sql_log.warning"):
        # No begin_request() — this is exactly the worker/startup shape.
        profiler.record_query(40.0, "SELECT worker_query")
        profiler.record_query(
            260.0, "SELECT worker_slow_query", slow_threshold_ms=200.0
        )

    snapshot = profiler.snapshot()
    assert snapshot["sql"]["worker_queries"] == 2
    assert snapshot["sql"]["request_queries"] == 0
    assert snapshot["sql"]["total_queries"] == 2
    assert snapshot["sql"]["total_ms"] == 300.0
    assert snapshot["sql"]["slow_queries"] == 1
    # The histogram already counted both — total_queries must now agree.
    assert snapshot["sql_latency"]["count"] == snapshot["sql"]["total_queries"]
    profiler.reset()


def test_request_and_worker_queries_both_counted_in_total():
    profiler.reset()
    profiler.begin_request()
    profiler.record_query(10.0, "SELECT request_query")
    profiler.end_request(path="/products", duration_ms=10.0)

    with patch("app.core.profiling._slow_sql_log.warning"):
        profiler.record_query(15.0, "SELECT worker_query")

    snapshot = profiler.snapshot()
    assert snapshot["sql"]["request_queries"] == 1
    assert snapshot["sql"]["worker_queries"] == 1
    assert snapshot["sql"]["total_queries"] == 2
    profiler.reset()
