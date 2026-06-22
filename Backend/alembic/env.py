import asyncio
import time as _time
from logging.config import fileConfig
from urllib.parse import urlparse, urlunparse

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

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

# ── Connection URL helpers ────────────────────────────────────────────────────

# Retry knobs for the "session pool exhausted" scenario.
# Sequence: 5s → 10s → 20s → 30s → 30s (total wait ≤ 95s before giving up).
_MIGRATION_RETRIES = 5
_MIGRATION_BACKOFFS = (5, 10, 20, 30, 30)


def get_migration_url() -> str:
    """
    Return the database URL Alembic should use for migrations.

    Priority order:
      1. ALEMBIC_DATABASE_URL — should point to the Supabase Transaction Pooler
         (port 6543). Transaction mode releases the server connection back to
         PgBouncer's pool immediately after each COMMIT. The migration's single
         NullPool connection therefore goes through a completely separate pool
         path and does NOT compete with the FastAPI app's session-mode slots.

      2. DATABASE_URL — fallback for deployments that have not yet added
         ALEMBIC_DATABASE_URL. Safe but risks EMAXCONNSESSION if the FastAPI
         pool is near capacity when the migration container starts.

    Connection type comparison (Supabase PgBouncer):
      Session Pooler   (port 5432): one backend assigned per client for the
        entire session lifetime. Client limit is plan-dependent. Used by FastAPI.
      Transaction Pooler (port 6543): backend assigned only for one transaction,
        returned to pool on COMMIT/ROLLBACK. Higher throughput, no session
        state (no SET, no named PREPARE, no LISTEN). Safe for Alembic.
      Direct Connection  (port 5432 via db.*.supabase.co): bypasses PgBouncer
        entirely. Hard limit = pg max_connections. Not recommended for app use.
    """
    return settings.ALEMBIC_DATABASE_URL or settings.DATABASE_URL


def _mask_url(url: str) -> str:
    """Return the URL with the password replaced by *** (never log passwords)."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            safe_netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urlunparse(parsed._replace(netloc=safe_netloc))
        return url
    except Exception:
        return "<url-parse-error>"


def _url_endpoint(url: str) -> str:
    """Extract host:port from a database URL for logging."""
    try:
        parsed = urlparse(url)
        return f"{parsed.hostname}:{parsed.port or 5432}"
    except Exception:
        return "unknown"


def _pool_label() -> str:
    """Human-readable pool type string for the migration log."""
    if settings.ALEMBIC_DATABASE_URL:
        return "Transaction Pooler (ALEMBIC_DATABASE_URL, port 6543)"
    return "Session Pooler fallback (DATABASE_URL — add ALEMBIC_DATABASE_URL to prevent EMAXCONNSESSION)"


# ── Offline mode ──────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """
    Emit migration SQL to stdout without connecting to the database.
    Used when you want to review the SQL before applying it manually.
    """
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


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    migration_url = get_migration_url()

    # ── Structured migration header ───────────────────────────────────────────
    print("[alembic] ─────────────────────────────────────────────────────")
    print(f"[alembic] Migration endpoint : {_url_endpoint(migration_url)}")
    print(f"[alembic] Safe URL           : {_mask_url(migration_url)}")
    print(f"[alembic] Pool type          : {_pool_label()}")
    print("[alembic] Pool class         : NullPool — no persistent connections held")
    print("[alembic] ─────────────────────────────────────────────────────")

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = migration_url

    # NullPool: SQLAlchemy creates a fresh TCP connection on every connect()
    # call and destroys it on close(). There is zero client-side connection
    # pool. This is the correct choice for a short-lived migration container
    # because:
    #   • It never holds idle connections that would occupy session-pooler slots.
    #   • Combined with the Transaction Pooler URL (port 6543), the single
    #     connection is returned to PgBouncer as soon as the migration transaction
    #     commits — even before the container exits.
    #   • There is no pool warm-up overhead for a one-shot process.
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    t_total = _time.monotonic()
    last_exc: BaseException | None = None

    # ── Retry loop (handles EMAXCONNSESSION and transient network blips) ──────
    for attempt in range(_MIGRATION_RETRIES):
        try:
            t_connect = _time.monotonic()
            async with connectable.connect() as connection:
                connect_ms = round((_time.monotonic() - t_connect) * 1000)
                print(
                    f"[alembic] Connection acquired in {connect_ms}ms "
                    f"(attempt {attempt + 1}/{_MIGRATION_RETRIES})"
                )
                await connection.run_sync(do_run_migrations)
            last_exc = None
            break  # success — exit retry loop

        except Exception as exc:
            last_exc = exc
            if attempt >= _MIGRATION_RETRIES - 1:
                break  # no more retries — fall through to raise

            delay = _MIGRATION_BACKOFFS[attempt]
            print(
                f"[alembic] Attempt {attempt + 1}/{_MIGRATION_RETRIES} failed "
                f"({type(exc).__name__}): {str(exc)[:400]}"
            )
            print(f"[alembic] Retrying in {delay}s…")
            await asyncio.sleep(delay)

    # ── Always dispose the engine so asyncpg connections are cleanly closed ───
    await connectable.dispose()

    duration_s = round(_time.monotonic() - t_total, 2)

    if last_exc is not None:
        print(
            f"[alembic] FAILED after {_MIGRATION_RETRIES} attempts "
            f"({duration_s}s total): {last_exc}"
        )
        raise RuntimeError(
            f"alembic upgrade head failed after {_MIGRATION_RETRIES} attempts. "
            f"Last error: {last_exc}"
        ) from last_exc

    print(f"[alembic] ✓ Migration completed in {duration_s}s")


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
