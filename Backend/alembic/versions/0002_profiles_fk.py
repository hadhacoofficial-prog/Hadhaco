"""Standardize user FKs: auth.users -> public.profiles (single source of truth).

Repoints every business-table foreign key that referenced ``auth.users(id)``
to ``public.profiles(id)``. Because ``profiles.id == auth.users.id`` (profiles
is a 1:1 mirror of auth.users, kept in sync by the ``handle_new_user`` trigger),
no data migration is required — only the constraint targets change.

Only ``public.profiles`` continues to reference ``auth.users``; after this
migration no other table depends on the auth schema.

Constraint names are preserved (``<table>_<column>_fkey``) so the change is a
pure repoint. ``DROP ... IF EXISTS`` keeps the upgrade safe to re-run.

Revision ID: 0002_profiles_fk
Revises: 0001_baseline
Create Date: 2026-06-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_profiles_fk"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column, on_delete) — cascade rules preserved from the original schema.
_FKS: tuple[tuple[str, str, str], ...] = (
    ("user_addresses", "user_id", "CASCADE"),
    ("wishlists", "user_id", "CASCADE"),
    ("carts", "user_id", "CASCADE"),
    ("orders", "user_id", "RESTRICT"),
    ("payments", "user_id", "RESTRICT"),
    ("reviews", "user_id", "CASCADE"),
    ("review_votes", "user_id", "CASCADE"),
    ("coupon_usages", "user_id", "CASCADE"),
    ("inventory_movements", "created_by", "SET NULL"),
)


def _repoint(table: str, column: str, on_delete: str, target: str) -> None:
    constraint = f"{table}_{column}_fkey"
    op.execute(f'ALTER TABLE public."{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    op.execute(
        f'ALTER TABLE public."{table}" '
        f'ADD CONSTRAINT "{constraint}" FOREIGN KEY ("{column}") '
        f"REFERENCES {target}(id) ON DELETE {on_delete}"
    )


def upgrade() -> None:
    for table, column, on_delete in _FKS:
        _repoint(table, column, on_delete, "public.profiles")


def downgrade() -> None:
    for table, column, on_delete in _FKS:
        _repoint(table, column, on_delete, "auth.users")
