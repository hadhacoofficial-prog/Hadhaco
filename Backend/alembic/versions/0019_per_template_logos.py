"""add per-template logo fields to company_config

Revision ID: 0019_per_template_logos
Revises: 0018_drop_company_address_lines
Create Date: 2026-07-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_per_template_logos"
down_revision: str | None = "0018_drop_company_address_lines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "company_config",
        sa.Column("packing_slip_logo_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_config",
        sa.Column("shipping_label_logo_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_config", "shipping_label_logo_url")
    op.drop_column("company_config", "packing_slip_logo_url")
