"""Extend company_config with full business profile fields.

Adds columns to the singleton company_config row so every piece of
business identity (contact, location, social, SEO, maps, etc.) is
stored in one place instead of being hardcoded.

Revision ID: 0064_company_config_extended_fields
Revises: 0063_variant_search_and_perf_indexes
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0064_company_config_extended_fields"
down_revision: str | None = "0063_variant_search_and_perf_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # General
    op.add_column("company_config", sa.Column("legal_name", sa.String(255), nullable=True))
    op.add_column("company_config", sa.Column("brand_name", sa.String(255), nullable=True))
    op.add_column("company_config", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("company_config", sa.Column("domain", sa.String(255), nullable=True))

    # Logos
    op.add_column("company_config", sa.Column("favicon_url", sa.Text(), nullable=True))

    # Contact
    op.add_column("company_config", sa.Column("alternate_phone", sa.String(30), nullable=True))
    op.add_column("company_config", sa.Column("whatsapp", sa.String(30), nullable=True))
    op.add_column("company_config", sa.Column("sales_email", sa.String(255), nullable=True))

    # Location
    op.add_column("company_config", sa.Column("address_line_1", sa.String(255), nullable=True))
    op.add_column("company_config", sa.Column("address_line_2", sa.String(255), nullable=True))

    # Maps
    op.add_column("company_config", sa.Column("google_maps_url", sa.Text(), nullable=True))
    op.add_column("company_config", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("company_config", sa.Column("longitude", sa.Float(), nullable=True))

    # Business
    op.add_column("company_config", sa.Column("cin", sa.String(30), nullable=True))
    op.add_column("company_config", sa.Column("business_hours", sa.String(255), nullable=True))

    # Social
    op.add_column("company_config", sa.Column("youtube_url", sa.Text(), nullable=True))
    op.add_column("company_config", sa.Column("twitter_x_url", sa.Text(), nullable=True))
    op.add_column("company_config", sa.Column("linkedin_url", sa.Text(), nullable=True))
    op.add_column("company_config", sa.Column("pinterest_url", sa.Text(), nullable=True))

    # SEO
    op.add_column("company_config", sa.Column("default_meta_title", sa.String(255), nullable=True))
    op.add_column("company_config", sa.Column("default_meta_description", sa.Text(), nullable=True))
    op.add_column("company_config", sa.Column("organization_description", sa.Text(), nullable=True))

    # Theme
    op.add_column("company_config", sa.Column("theme_color", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("company_config", "theme_color")
    op.drop_column("company_config", "organization_description")
    op.drop_column("company_config", "default_meta_description")
    op.drop_column("company_config", "default_meta_title")
    op.drop_column("company_config", "pinterest_url")
    op.drop_column("company_config", "linkedin_url")
    op.drop_column("company_config", "twitter_x_url")
    op.drop_column("company_config", "youtube_url")
    op.drop_column("company_config", "business_hours")
    op.drop_column("company_config", "cin")
    op.drop_column("company_config", "longitude")
    op.drop_column("company_config", "latitude")
    op.drop_column("company_config", "google_maps_url")
    op.drop_column("company_config", "address_line_2")
    op.drop_column("company_config", "address_line_1")
    op.drop_column("company_config", "sales_email")
    op.drop_column("company_config", "whatsapp")
    op.drop_column("company_config", "alternate_phone")
    op.drop_column("company_config", "favicon_url")
    op.drop_column("company_config", "domain")
    op.drop_column("company_config", "description")
    op.drop_column("company_config", "brand_name")
    op.drop_column("company_config", "legal_name")
