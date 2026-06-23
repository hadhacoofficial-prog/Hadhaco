"""
Standalone migration runner for 0007_order_status_full.
Run from the Backend directory:
  hadha/Scripts/python.exe scripts/run_migration_007.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import unquote, urlparse

import asyncpg


def parse_pg_url(url: str) -> dict:
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    p = urlparse(url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "database": p.path.lstrip("/"),
        "statement_cache_size": 0,
    }


_ALLOWED = (
    "pending",
    "stock_reserved",
    "payment_pending",
    "confirmed",
    "processing",
    "packed",
    "shipped",
    "delivered",
    "cancelled",
    "payment_failed",
    "payment_expired",
    "return_requested",
    "returned",
    "refunded",
)

_DDL = f"""
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_check;
ALTER TABLE orders ADD CONSTRAINT orders_status_check
    CHECK (status IN ({', '.join(repr(s) for s in _ALLOWED)}));
UPDATE alembic_version SET version_num = '0007_order_status_full';
"""


async def main() -> None:
    db_url = ""
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_file):
        for line in open(env_file):
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                db_url = line.split("=", 1)[1].strip()
                break
    if not db_url:
        sys.exit("DATABASE_URL not found")

    kwargs = parse_pg_url(db_url)
    print(f"Connecting to {kwargs['host']}:{kwargs['port']} ...")
    conn = await asyncpg.connect(**kwargs)
    try:
        ver = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"Current alembic version: {ver}")

        if ver == "0007_order_status_full":
            print("Migration 0007 already applied.")
            return

        if ver != "0006_order_status_fix":
            sys.exit(f"Unexpected version '{ver}' — expected 0006. Aborting.")

        print("Applying migration 0007 ...")
        async with conn.transaction():
            await conn.execute(_DDL)
        print("Migration 0007 applied successfully.")

        new_ver = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"Alembic version now: {new_ver}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
