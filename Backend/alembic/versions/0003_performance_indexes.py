"""Add composite indexes for query performance.

Targets the three slow endpoints:
  GET /products  — WHERE status='active' AND deleted_at IS NULL ORDER BY created_at
  GET /orders    — WHERE user_id=? ORDER BY created_at DESC (list_for_user)
  GET /me        — no structural change here; covered by profile Redis cache

Revision ID: 0003_performance_indexes
Revises: 0002_profiles_fk
Create Date: 2026-06-20
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_performance_indexes"
down_revision: str | None = "0002_profiles_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── products ──────────────────────────────────────────────────────────────
    # Most common public filter: WHERE status='active' AND deleted_at IS NULL
    op.create_index(
        "idx_products_status_deleted",
        "products",
        ["status", "deleted_at"],
    )
    # Featured products page: WHERE is_featured=true AND status='active' AND deleted_at IS NULL
    op.create_index(
        "idx_products_featured_status_deleted",
        "products",
        ["is_featured", "status", "deleted_at"],
    )
    # Category filter: WHERE category_id=? AND status='active' AND deleted_at IS NULL
    op.create_index(
        "idx_products_category_status_deleted",
        "products",
        ["category_id", "status", "deleted_at"],
    )

    # ── orders ────────────────────────────────────────────────────────────────
    # list_for_user: WHERE user_id=? ORDER BY created_at DESC LIMIT N
    # Composite allows index-only seek + sort without a separate sort step.
    op.create_index(
        "idx_orders_user_created",
        "orders",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_orders_user_created", table_name="orders")
    op.drop_index("idx_products_category_status_deleted", table_name="products")
    op.drop_index("idx_products_featured_status_deleted", table_name="products")
    op.drop_index("idx_products_status_deleted", table_name="products")
