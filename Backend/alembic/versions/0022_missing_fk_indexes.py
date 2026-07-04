"""Add missing indexes on FK columns (schema audit H2, H16, and the
FK-index table): orders.coupon_id, inventory_reservations.variant_id,
coupon_usages.order_id, support_tickets.order_id,
support_messages.sender_id, fulfillment_timeline.actor_id.

orders and inventory_reservations are the two hottest tables in the
schema, so their indexes are created CONCURRENTLY (no write-blocking
lock, at the cost of running outside this migration's transaction).
The other three tables are low-traffic and use a plain CREATE INDEX.

Revision ID: 0022_missing_fk_indexes
Revises: 0021_data_integrity_check_constraints
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022_missing_fk_indexes"
down_revision: str | None = "0021_data_integrity_check_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_orders_coupon_id",
            "orders",
            ["coupon_id"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "idx_inv_res_variant_id",
            "inventory_reservations",
            ["variant_id"],
            postgresql_concurrently=True,
        )

    op.create_index("idx_coupon_usages_order_id", "coupon_usages", ["order_id"])
    op.create_index("idx_support_tickets_order_id", "support_tickets", ["order_id"])
    op.create_index("idx_support_messages_sender_id", "support_messages", ["sender_id"])
    op.create_index(
        "idx_fulfillment_timeline_actor_id", "fulfillment_timeline", ["actor_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "idx_fulfillment_timeline_actor_id", table_name="fulfillment_timeline"
    )
    op.drop_index("idx_support_messages_sender_id", table_name="support_messages")
    op.drop_index("idx_support_tickets_order_id", table_name="support_tickets")
    op.drop_index("idx_coupon_usages_order_id", table_name="coupon_usages")

    with op.get_context().autocommit_block():
        op.drop_index(
            "idx_inv_res_variant_id",
            table_name="inventory_reservations",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "idx_orders_coupon_id", table_name="orders", postgresql_concurrently=True
        )
