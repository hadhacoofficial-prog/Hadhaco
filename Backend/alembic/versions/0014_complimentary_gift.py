"""add complimentary_gift to orders

Revision ID: 0014_complimentary_gift
Revises: 0013_company_config
Create Date: 2026-06-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_complimentary_gift"
down_revision = "0013_company_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("complimentary_gift", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "complimentary_gift")
