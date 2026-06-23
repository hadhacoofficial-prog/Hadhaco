"""
Standalone migration runner for 0005_reservation_system.
Uses asyncpg directly (no SQLAlchemy) to bypass prepared-statement issues.
Run from the Backend directory:
  hadha/Scripts/python.exe scripts/run_migration_005.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import unquote, urlparse

import asyncpg


def parse_pg_url(url: str) -> dict:
    """Turn postgresql+asyncpg://user:pass@host:port/db into asyncpg.connect kwargs."""
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


_DDL = """
DO $$ BEGIN
    CREATE TYPE inventory_reservation_status
        AS ENUM ('ACTIVE', 'COMPLETED', 'RELEASED', 'EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE inventory_transaction_type
        AS ENUM ('RESERVE', 'RELEASE', 'SALE', 'RETURN', 'RESTOCK', 'ADJUSTMENT');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS reserved_quantity INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sold_quantity     INTEGER NOT NULL DEFAULT 0;

ALTER TABLE product_variants
    ADD COLUMN IF NOT EXISTS reserved_quantity INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sold_quantity     INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS inventory_reservations (
    id                 UUID PRIMARY KEY,
    reservation_number VARCHAR(40) NOT NULL UNIQUE,
    user_id            UUID NOT NULL REFERENCES profiles(id)  ON DELETE RESTRICT,
    order_id           UUID          REFERENCES orders(id)    ON DELETE SET NULL,
    product_id         UUID NOT NULL REFERENCES products(id)  ON DELETE RESTRICT,
    variant_id         UUID          REFERENCES product_variants(id) ON DELETE SET NULL,
    quantity           INTEGER NOT NULL,
    status             inventory_reservation_status NOT NULL DEFAULT 'ACTIVE',
    expires_at         TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inv_res_user_id    ON inventory_reservations(user_id);
CREATE INDEX IF NOT EXISTS idx_inv_res_order_id   ON inventory_reservations(order_id);
CREATE INDEX IF NOT EXISTS idx_inv_res_product_id ON inventory_reservations(product_id);
CREATE INDEX IF NOT EXISTS idx_inv_res_status     ON inventory_reservations(status);
CREATE INDEX IF NOT EXISTS idx_inv_res_expires_at ON inventory_reservations(expires_at);
CREATE INDEX IF NOT EXISTS idx_inv_res_status_expires
    ON inventory_reservations(status, expires_at);

CREATE TABLE IF NOT EXISTS inventory_transactions (
    id               UUID PRIMARY KEY,
    product_id       UUID NOT NULL REFERENCES products(id)             ON DELETE RESTRICT,
    variant_id       UUID          REFERENCES product_variants(id)      ON DELETE SET NULL,
    reservation_id   UUID          REFERENCES inventory_reservations(id) ON DELETE SET NULL,
    order_id         UUID          REFERENCES orders(id)                ON DELETE SET NULL,
    transaction_type inventory_transaction_type NOT NULL,
    quantity         INTEGER NOT NULL,
    before_available INTEGER NOT NULL,
    after_available  INTEGER NOT NULL,
    before_reserved  INTEGER NOT NULL,
    after_reserved   INTEGER NOT NULL,
    before_sold      INTEGER NOT NULL,
    after_sold       INTEGER NOT NULL,
    reference        VARCHAR(255),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inv_txn_product_id     ON inventory_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_inv_txn_reservation_id ON inventory_transactions(reservation_id);
CREATE INDEX IF NOT EXISTS idx_inv_txn_order_id       ON inventory_transactions(order_id);
CREATE INDEX IF NOT EXISTS idx_inv_txn_type           ON inventory_transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_inv_txn_created_at     ON inventory_transactions(created_at);

UPDATE alembic_version SET version_num = '0005_reservation_system';
"""


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        # load from .env in Backend/
        env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_file):
            for line in open(env_file):
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    db_url = line.split("=", 1)[1].strip()
                    break
    if not db_url:
        sys.exit("DATABASE_URL not found — set it in .env or environment")

    kwargs = parse_pg_url(db_url)
    print(f"Connecting to {kwargs['host']}:{kwargs['port']} as {kwargs['user']} ...")

    conn = await asyncpg.connect(**kwargs)
    try:
        ver = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"Current alembic version: {ver}")

        if ver == "0005_reservation_system":
            print("Migration 0005 already applied — nothing to do.")
            return

        if ver != "0004_cms_homepage_extension":
            sys.exit(f"Unexpected version '{ver}' — expected 0004. Aborting.")

        print("Applying migration 0005_reservation_system ...")
        async with conn.transaction():
            await conn.execute(_DDL)
        print("Migration 0005 applied successfully.")

        new_ver = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"Alembic version now: {new_ver}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
