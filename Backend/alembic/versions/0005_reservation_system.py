"""Stock reservation system — prevent overselling with atomic row-level locking.

Adds reserved_quantity + sold_quantity columns to products/product_variants.
Creates inventory_reservations and inventory_transactions tables.
Available stock = stock_quantity - reserved_quantity - sold_quantity.

Revision ID: 0005_reservation_system
Revises: 0004_cms_homepage_extension
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0005_reservation_system"
down_revision: str | None = "0004_cms_homepage_extension"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. New ENUMs ──────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE inventory_reservation_status
                AS ENUM ('ACTIVE', 'COMPLETED', 'RELEASED', 'EXPIRED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE inventory_transaction_type
                AS ENUM ('RESERVE', 'RELEASE', 'SALE', 'RETURN', 'RESTOCK', 'ADJUSTMENT');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """)

    # ── 2. Extend products table ───────────────────────────────────────────────
    op.add_column(
        "products",
        sa.Column(
            "reserved_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "sold_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # ── 3. Extend product_variants table ──────────────────────────────────────
    op.add_column(
        "product_variants",
        sa.Column(
            "reserved_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "product_variants",
        sa.Column(
            "sold_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # ── 4. inventory_reservations table ───────────────────────────────────────
    op.create_table(
        "inventory_reservations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("reservation_number", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "COMPLETED",
                "RELEASED",
                "EXPIRED",
                name="inventory_reservation_status",
                create_type=False,
            ),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_inv_res_user_id", "inventory_reservations", ["user_id"])
    op.create_index("idx_inv_res_order_id", "inventory_reservations", ["order_id"])
    op.create_index("idx_inv_res_product_id", "inventory_reservations", ["product_id"])
    op.create_index("idx_inv_res_status", "inventory_reservations", ["status"])
    op.create_index("idx_inv_res_expires_at", "inventory_reservations", ["expires_at"])
    op.create_index(
        "idx_inv_res_status_expires",
        "inventory_reservations",
        ["status", "expires_at"],
    )

    # ── 5. inventory_transactions table ───────────────────────────────────────
    op.create_table(
        "inventory_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reservation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("inventory_reservations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "transaction_type",
            sa.Enum(
                "RESERVE",
                "RELEASE",
                "SALE",
                "RETURN",
                "RESTOCK",
                "ADJUSTMENT",
                name="inventory_transaction_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("before_available", sa.Integer(), nullable=False),
        sa.Column("after_available", sa.Integer(), nullable=False),
        sa.Column("before_reserved", sa.Integer(), nullable=False),
        sa.Column("after_reserved", sa.Integer(), nullable=False),
        sa.Column("before_sold", sa.Integer(), nullable=False),
        sa.Column("after_sold", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_inv_txn_product_id", "inventory_transactions", ["product_id"])
    op.create_index(
        "idx_inv_txn_reservation_id",
        "inventory_transactions",
        ["reservation_id"],
    )
    op.create_index("idx_inv_txn_order_id", "inventory_transactions", ["order_id"])
    op.create_index("idx_inv_txn_type", "inventory_transactions", ["transaction_type"])
    op.create_index("idx_inv_txn_created_at", "inventory_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_table("inventory_transactions")
    op.drop_table("inventory_reservations")
    op.drop_column("product_variants", "sold_quantity")
    op.drop_column("product_variants", "reserved_quantity")
    op.drop_column("products", "sold_quantity")
    op.drop_column("products", "reserved_quantity")
    op.execute("DROP TYPE IF EXISTS inventory_transaction_type")
    op.execute("DROP TYPE IF EXISTS inventory_reservation_status")
