"""Add explicit ON DELETE behavior to FK columns that currently default
to Postgres NO ACTION (schema audit C2, H14): categories.parent_id,
returns.order_id/customer_id, return_items.order_item_id,
support_tickets.customer_id/order_id, support_messages.sender_id.

Without this, deleting an order/profile/category that has an associated
return, support ticket, or subcategory fails with a raw, uncontrolled
FK-violation error instead of a clean, predictable outcome, and blocks
GDPR-style profile erasure unpredictably depending on which of these
tables happens to hold rows for that customer.

RESTRICT is used for every column except support_tickets.order_id,
which uses SET NULL — a ticket should survive the order it references
being removed, matching the nullable column semantics already in place.

Revision ID: 0023_fk_ondelete_fixes
Revises: 0022_missing_fk_indexes
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023_fk_ondelete_fixes"
down_revision: str | None = "0022_missing_fk_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (constraint_name, table, column, ref_table, ondelete)
_FKS: list[tuple[str, str, str, str, str]] = [
    ("categories_parent_id_fkey", "categories", "parent_id", "categories", "RESTRICT"),
    ("returns_order_id_fkey", "returns", "order_id", "orders", "RESTRICT"),
    ("returns_customer_id_fkey", "returns", "customer_id", "profiles", "RESTRICT"),
    (
        "return_items_order_item_id_fkey",
        "return_items",
        "order_item_id",
        "order_items",
        "RESTRICT",
    ),
    (
        "support_tickets_customer_id_fkey",
        "support_tickets",
        "customer_id",
        "profiles",
        "RESTRICT",
    ),
    (
        "support_tickets_order_id_fkey",
        "support_tickets",
        "order_id",
        "orders",
        "SET NULL",
    ),
    (
        "support_messages_sender_id_fkey",
        "support_messages",
        "sender_id",
        "profiles",
        "RESTRICT",
    ),
]


def upgrade() -> None:
    for name, table, column, ref_table, ondelete in _FKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({column}) REFERENCES {ref_table}(id) ON DELETE {ondelete}"
        )


def downgrade() -> None:
    for name, table, column, ref_table, _ondelete in reversed(_FKS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({column}) REFERENCES {ref_table}(id)"
        )
