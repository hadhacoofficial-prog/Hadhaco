"""
Production logging configuration.

One place that owns every logging decision:
  - structlog is the single formatter — no duplicate handlers, no double printing
  - uvicorn's own handlers are stripped and replaced with ours at startup
  - SQL echo is off by default; set LOG_SQL=true to re-enable for local debugging
  - APScheduler, httpx, boto3, and other chatty libraries are silenced to WARNING
  - Request-level context (request_id, user_id, ip) is injected by middleware;
    every log line inside a request automatically carries those fields

Usage anywhere in the app:
    log = structlog.get_logger(__name__)
    log.info("order_created", order_id=str(order.id), total=order.total)
"""
from __future__ import annotations

import logging
import sys

import structlog

# ── Loggers silenced in every environment ──────────────────────────────────────
# Keep this list narrow — each entry is a conscious tradeoff between signal and
# noise. WARNING still surfaces actual errors; we just drop the chatty INFO/DEBUG.
_SILENCE: dict[str, int] = {
    # Access log replaced by RequestLoggingMiddleware
    "uvicorn.access": logging.WARNING,
    # SQLAlchemy internals — only sqlalchemy.engine is conditional (see below)
    "sqlalchemy.pool": logging.WARNING,
    "sqlalchemy.dialects": logging.WARNING,
    "sqlalchemy.orm": logging.WARNING,
    # APScheduler fires INFO on every tick ("Looking for jobs", "Next wakeup")
    "apscheduler.scheduler": logging.WARNING,
    "apscheduler.executors.default": logging.WARNING,
    "apscheduler.jobstores": logging.WARNING,
    # HTTP client internals
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "hpack": logging.WARNING,
    # AWS / Cloudflare R2 SDK
    "boto3": logging.WARNING,
    "botocore": logging.WARNING,
    "s3transfer": logging.WARNING,
    # Password hashing lib logs algorithm discovery at INFO
    "passlib": logging.WARNING,
    # multipart body parser emits per-part DEBUG noise
    "multipart": logging.WARNING,
    # File watcher used by uvicorn --reload
    "watchfiles": logging.WARNING,
    # urllib3 connection pool chatter
    "urllib3": logging.WARNING,
    # asyncio event loop internals
    "asyncio": logging.WARNING,
}


def configure_logging(debug: bool = False, log_sql: bool = False) -> None:
    """
    Configure structlog and the stdlib root logger.

    dev  (debug=True) → ConsoleRenderer: coloured, aligned columns, inline tracebacks
    prod (debug=False) → JSONRenderer: one JSON object per line, machine-parseable

    SQL echo is disabled by default.  Pass log_sql=True (or debug=True) to show
    all SQL statements — useful when debugging a query, not appropriate for prod.

    Call exactly once at application startup before any logging occurs.
    """
    # ── Shared processor chain ─────────────────────────────────────────────────
    # These run for both structlog-native loggers AND stdlib loggers that are
    # routed through structlog's ProcessorFormatter (uvicorn, sqlalchemy, etc.).
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,        # inject request_id, user_id, ip
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="%H:%M:%S.%f" if debug else "iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]

    if debug:
        # Show the exact module and function that emitted the log — helpful when
        # chasing down where a log line comes from during local development.
        shared_processors.insert(0, structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.FUNC_NAME,
            ]
        ))
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
        # In dev mode ConsoleRenderer handles exc_info natively; no ExceptionRenderer needed.
        formatter_processors: list = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ]
    else:
        renderer = structlog.processors.JSONRenderer()
        # ExceptionRenderer turns exc_info tuples into a structured dict before
        # JSONRenderer serialises them — avoids raw Python repr in the JSON output.
        formatter_processors = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.ExceptionRenderer(),
            renderer,
        ]

    # ── Configure structlog ────────────────────────────────────────────────────
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── Single stdout handler shared by everyone ───────────────────────────────
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=formatter_processors,
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Replace the root logger's handlers completely so nothing bypasses structlog.
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # ── Re-route uvicorn's own loggers through root ────────────────────────────
    # Uvicorn installs StreamHandlers on "uvicorn" and "uvicorn.error" before
    # the lifespan starts.  Clearing them here means startup/shutdown messages
    # pass through our formatter instead of uvicorn's plain-text one.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lgr = logging.getLogger(name)
        lgr.handlers.clear()
        lgr.propagate = True

    # ── Silence noisy third-party loggers ─────────────────────────────────────
    for name, level in _SILENCE.items():
        logging.getLogger(name).setLevel(level)

    # SQL echo is controlled exclusively by LOG_SQL, never by APP_DEBUG.
    # APP_DEBUG=true gives you pretty console output and callsite info but
    # does NOT flood the terminal with SQL — set LOG_SQL=true separately
    # only when you actually need to inspect a query.
    sql_level = logging.INFO if log_sql else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Convenience wrapper so callers don't import structlog directly."""
    return structlog.get_logger(name)
