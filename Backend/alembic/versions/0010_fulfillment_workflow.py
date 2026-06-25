"""Add fulfillment workflow fields and timeline tracking.

Revision ID: 0010_fulfillment_workflow
Revises: 0009_add_max_order_quantity
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

from alembic import op

revision: str = "0010_fulfillment_workflow"
down_revision: str | None = "0009_add_max_order_quantity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "fulfillment_status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "orders",
        sa.Column("packed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "shipping_label_generated_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "orders",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("shipment_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("fulfilled_by", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("last_fulfillment_action", sa.String(50), nullable=True),
    )

    op.add_column(
        "shipments",
        sa.Column("dispatch_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "shipments",
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "shipments",
        sa.Column("dispatch_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "shipments",
        sa.Column("fulfilled_by", UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        "fulfillment_timeline",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("order_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("admin_name", sa.String(255), nullable=True),
        sa.Column("details", JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_fulfillment_timeline_order_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["profiles.id"],
            name="fk_fulfillment_timeline_actor_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_fulfillment_timeline_order_id",
        "fulfillment_timeline",
        ["order_id"],
    )
    op.create_index(
        "idx_fulfillment_timeline_action",
        "fulfillment_timeline",
        ["action"],
    )
    op.create_index(
        "idx_fulfillment_timeline_created_at",
        "fulfillment_timeline",
        ["created_at"],
    )

    op.create_check_constraint(
        "ck_orders_fulfillment_status",
        "orders",
        "fulfillment_status IN ('pending', 'packing', 'label_generated', 'dispatched', 'in_transit', 'delivered', 'cancelled', 'returned', 'refunded')",
    )

    op.create_check_constraint(
        "ck_orders_shipping_provider",
        "orders",
        "shipping_provider IS NULL OR shipping_provider IN ('india_post', 'dtdc', 'delhivery', 'blue_dart', 'xpressbees', 'shadowfax', 'ekart', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_shipping_provider", "orders")
    op.drop_constraint("ck_orders_fulfillment_status", "orders")
    op.drop_index("idx_fulfillment_timeline_created_at")
    op.drop_index("idx_fulfillment_timeline_action")
    op.drop_index("idx_fulfillment_timeline_order_id")
    op.drop_table("fulfillment_timeline")
    op.drop_column("shipments", "fulfilled_by")
    op.drop_column("shipments", "dispatch_notes")
    op.drop_column("shipments", "expected_delivery_date")
    op.drop_column("shipments", "dispatch_date")
    op.drop_column("orders", "last_fulfillment_action")
    op.drop_column("orders", "fulfilled_by")
    op.drop_column("orders", "shipment_notes")
    op.drop_column("orders", "dispatched_at")
    op.drop_column("orders", "shipping_label_generated_at")
    op.drop_column("orders", "packed_at")
    op.drop_column("orders", "fulfillment_status")
