"""Baseline — schema is created by supabase/sql/setup.sql.

The database schema (tables, indexes, views, RLS policies, triggers, seed
data) is owned by the versioned SQL files in supabase/sql and applied with:

    psql $DATABASE_URL -f supabase/sql/setup.sql

This empty baseline anchors the Alembic history so future incremental
changes can be expressed as normal migrations. After running setup.sql on a
fresh database, mark it as up to date with:

    alembic stamp 0001_baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-11
"""
from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Schema is provisioned by supabase/sql/setup.sql — nothing to do here.
    pass


def downgrade() -> None:
    pass
