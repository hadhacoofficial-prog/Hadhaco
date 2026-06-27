"""company_config table

Revision ID: 0013_company_config
Revises: 0012_address_landmark_alternate_phone
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_company_config"
down_revision: str | None = "0012_address_landmark_alternate_phone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tagline", sa.String(255), nullable=True),
        sa.Column("gstin", sa.String(20), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(2), nullable=False, server_default="IN"),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("support_email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("logo_r2_key", sa.Text(), nullable=True),
        sa.Column("instagram_url", sa.Text(), nullable=True),
        sa.Column("facebook_url", sa.Text(), nullable=True),
    )
    # Seed the single company record with Hadha defaults
    op.execute("""
        INSERT INTO company_config (
            id, name, tagline, phone, support_email, website
        ) VALUES (
            1,
            'Hadha Jewellery',
            'Timeless Beauty, Trusted Quality',
            '+91 XXXXX XXXXX',
            'info@hadhajewellery.com',
            'www.hadhajewellery.com'
        )
        """)


def downgrade() -> None:
    op.drop_table("company_config")
