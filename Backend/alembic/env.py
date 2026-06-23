"""Alembic migration environment — synchronous psycopg driver.

Connection priority:
  1. ALEMBIC_DATABASE_URL (postgresql+psycopg://) — Supabase Direct Connection,
     bypasses pgBouncer entirely. No prepared-statement conflicts, no pool limits.
  2. DATABASE_URL fallback — asyncpg driver is swapped to psycopg automatically
     so the same session-pooler host can be used with the sync driver.

Why psycopg (not asyncpg)?
  asyncpg requires an async event loop that is incompatible with Alembic's
  synchronous migration runner. psycopg (v3 sync) works with NullPool and all
  pgBouncer modes without prepared-statement housekeeping.
"""

import time as _time
from logging.config import fileConfig
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import settings
from app.core.database import Base

# ── Model discovery ───────────────────────────────────────────────────────────


def _import_all_models() -> None:
    """Import every modules/*/models.py so autogenerate sees the full schema."""
    import importlib
    import pkgutil

    import app.modules as modules_pkg

    for mod in pkgutil.iter_modules(modules_pkg.__path__):
        try:
            importlib.import_module(f"app.modules.{mod.name}.models")
        except ModuleNotFoundError:
            continue


_import_all_models()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# ── URL helpers ───────────────────────────────────────────────────────────────


def get_migration_url() -> str:
    """
    Return the psycopg URL Alembic should use.

    Prefers ALEMBIC_DATABASE_URL (direct connection, no pgBouncer).
    Falls back to DATABASE_URL with the driver swapped from asyncpg → psycopg.
    """
    raw = settings.ALEMBIC_DATABASE_URL or settings.DATABASE_URL

    # Normalise to psycopg driver regardless of source.
    if raw.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg://" + raw[len("postgresql+asyncpg://") :]
    elif raw.startswith("postgresql://") and "+psycopg" not in raw:
        url = "postgresql+psycopg://" + raw[len("postgresql://") :]
    else:
        url = raw

    if not url.startswith("postgresql+psycopg://"):
        raise SystemExit(
            f"[alembic] Migration URL must use postgresql+psycopg://. Got: {_mask_url(url)}\n"
            "Set ALEMBIC_DATABASE_URL=postgresql+psycopg://... in your .env."
        )
    return url


def _mask_url(url: str) -> str:
    """Return the URL with the password replaced by ***."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            safe = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urlunparse(parsed._replace(netloc=safe))
        return url
    except Exception:
        return "<url-parse-error>"


def _url_endpoint(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.hostname}:{parsed.port or 5432}"
    except Exception:
        return "unknown"


def _conn_label() -> str:
    if settings.ALEMBIC_DATABASE_URL:
        host = urlparse(settings.ALEMBIC_DATABASE_URL).hostname or ""
        if host.startswith("db.") and "supabase.co" in host:
            return "Direct Connection — bypasses pgBouncer (ALEMBIC_DATABASE_URL)"
    return "Session Pooler fallback — psycopg driver, DATABASE_URL host"


# ── Offline mode ──────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Emit migration SQL to stdout without a live connection."""
    url = get_migration_url()
    print(f"[alembic] Offline mode — endpoint: {_url_endpoint(url)}")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    migration_url = get_migration_url()

    print("[alembic] ─────────────────────────────────────────────────────")
    print(f"[alembic] Migration endpoint : {_url_endpoint(migration_url)}")
    print(f"[alembic] Safe URL           : {_mask_url(migration_url)}")
    print(f"[alembic] Connection type    : {_conn_label()}")
    print("[alembic] Driver             : psycopg (sync) — no pgBouncer conflicts")
    print("[alembic] Pool class         : NullPool — one connection, disposed on close")
    print("[alembic] ─────────────────────────────────────────────────────")

    t_total = _time.monotonic()
    engine = create_engine(migration_url, poolclass=pool.NullPool)

    t_connect = _time.monotonic()
    try:
        with engine.connect() as connection:
            connect_ms = round((_time.monotonic() - t_connect) * 1000)
            print(f"[alembic] Connection acquired in {connect_ms}ms")
            do_run_migrations(connection)
    except Exception as exc:
        duration_s = round(_time.monotonic() - t_total, 2)
        print(f"[alembic] FAILED ({duration_s}s): {exc}")
        raise
    finally:
        engine.dispose()

    duration_s = round(_time.monotonic() - t_total, 2)
    print(f"[alembic] ✓ Migration completed in {duration_s}s")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
