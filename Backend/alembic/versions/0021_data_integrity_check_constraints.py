"""Add missing DB-level CHECK constraints for coupon status and non-negative
money/quantity columns (schema audit C3, C4).

Every constraint is added NOT VALID: Postgres enforces it immediately for
all new INSERT/UPDATE statements, but does *not* scan or lock existing
rows at migration time. This is the standard safe pattern for adding
constraints to live tables whose current data hasn't been audited yet.

Before running VALIDATE CONSTRAINT <name> in a follow-up maintenance
window, confirm no existing rows violate it, e.g.:
    SELECT count(*) FROM products WHERE reserved_quantity < 0;
    SELECT count(*) FROM orders WHERE subtotal < 0 OR total < 0;
(repeat per table/column below). VALIDATE CONSTRAINT takes only a brief
SHARE UPDATE EXCLUSIVE lock and does not block concurrent reads/writes.

Revision ID: 0021_data_integrity_check_constraints
Revises: 0020_fulfillment_timeline_jsonb
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021_data_integrity_check_constraints"
down_revision: str | None = "0020_fulfillment_timeline_jsonb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS: list[tuple[str, str, str]] = [
    ("coupons", "coupons_status_check", "status IN ('active','inactive','draft')"),
    ("products", "products_reserved_quantity_check", "reserved_quantity >= 0"),
    ("products", "products_sold_quantity_check", "sold_quantity >= 0"),
    (
        "product_variants",
        "product_variants_reserved_quantity_check",
        "reserved_quantity >= 0",
    ),
    ("product_variants", "product_variants_sold_quantity_check", "sold_quantity >= 0"),
    ("orders", "orders_subtotal_check", "subtotal >= 0"),
    ("orders", "orders_tax_amount_check", "tax_amount >= 0"),
    ("orders", "orders_shipping_charge_check", "shipping_charge >= 0"),
    ("orders", "orders_discount_check", "discount >= 0"),
    ("orders", "orders_total_check", "total >= 0"),
    ("cart_items", "cart_items_unit_price_check", "unit_price >= 0"),
    ("payments", "payments_amount_check", "amount >= 0"),
    ("refunds", "refunds_amount_check", "amount >= 0"),
]


def upgrade() -> None:
    for table, name, condition in _CONSTRAINTS:
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID"
        )


def downgrade() -> None:
    for table, name, _condition in reversed(_CONSTRAINTS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
