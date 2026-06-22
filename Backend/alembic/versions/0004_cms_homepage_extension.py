"""Extend CMS module for full homepage CMS.

landing_sections: +6 columns (section_type, draft_config, status,
                               scheduled_at, published_at, published_by)
New tables: cms_section_items, cms_media, cms_version_history,
            cms_cache_version, cms_publish_log
Seeds 16 default landing_section rows (ON CONFLICT DO NOTHING).

Revision ID: 0004_cms_homepage_extension
Revises: 0003_performance_indexes
Create Date: 2026-06-20
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004_cms_homepage_extension"
down_revision: str | None = "0003_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Seed data — mirrors the hardcoded homepage components
# ---------------------------------------------------------------------------

_SEED: list[dict] = [
    {
        "key": "navbar",
        "type": "navbar",
        "title": "Navbar",
        "order": -10,
        "config": {},
    },
    {
        "key": "announcement_bar",
        "type": "announcement_bar",
        "title": "Announcement Bar",
        "order": 0,
        "config": {"rotation_speed": 4, "show_close": True},
    },
    {
        "key": "hero_carousel",
        "type": "hero_carousel",
        "title": "Hero Carousel",
        "order": 10,
        "config": {"auto_rotate": True, "rotation_speed": 6},
    },
    {
        "key": "shop_by_gender",
        "type": "category_grid",
        "title": "Shop by Gender",
        "order": 20,
        "config": {"title": "Shop by Style", "columns": 4},
    },
    {
        "key": "featured_collection",
        "type": "collection_showcase",
        "title": "Featured Collection",
        "order": 30,
        "config": {"title": "Featured Collection", "grid_size": "3", "card_style": "overlay"},
    },
    {
        "key": "featured_products",
        "type": "product_grid",
        "title": "Featured Products",
        "order": 40,
        "config": {
            "title": "Handpicked for You",
            "eyebrow": "Featured Products",
            "source": "featured",
            "max_products": 8,
            "view_all_url": "/products",
        },
    },
    {
        "key": "craftsmanship_video",
        "type": "video_section",
        "title": "Craftsmanship Video",
        "order": 50,
        "config": {
            "eyebrow": "Our Craftsmanship",
            "title": "Cast by hand in our Visakhapatnam atelier.",
            "subtitle": "Every Hadha piece is shaped, polished and quality-checked by our master silversmiths — keeping South Indian artisanship alive, one creation at a time.",
            "mp4_url": "https://videos.pexels.com/video-files/11353206/11353206-hd_1920_1080_25fps.mp4",
            "poster_url": "",
            "autoplay": True,
            "loop": True,
            "muted": True,
            "controls": False,
        },
    },
    {
        "key": "new_arrivals",
        "type": "product_grid",
        "title": "New Arrivals",
        "order": 60,
        "config": {
            "title": "New Arrivals",
            "eyebrow": "Just In",
            "source": "newest",
            "max_products": 8,
            "view_all_url": "/products?sort=newest",
        },
    },
    {
        "key": "shop_by_category",
        "type": "category_grid",
        "title": "Shop by Category",
        "order": 70,
        "config": {"title": "Shop by Category", "columns": 3},
    },
    {
        "key": "promo_banner",
        "type": "image_banner",
        "title": "Promo Banner",
        "order": 80,
        "config": {
            "title": "The Bugadi Edit",
            "subtitle": "Press-on temple silhouettes in solid 92.5 silver.",
            "cta_text": "Shop the edit",
            "cta_url": "/collections",
        },
    },
    {
        "key": "trending",
        "type": "product_grid",
        "title": "Trending",
        "order": 90,
        "config": {
            "title": "Trending Now",
            "eyebrow": "Most loved",
            "source": "best_seller",
            "max_products": 8,
            "view_all_url": "/products?sort=trending",
        },
    },
    {
        "key": "why_choose_us",
        "type": "content_block",
        "title": "Why Choose Us",
        "order": 100,
        "config": {"title": "Why Hadha"},
    },
    {
        "key": "reviews",
        "type": "testimonials",
        "title": "Customer Reviews",
        "order": 110,
        "config": {"title": "What Our Customers Say", "sort": "recent"},
    },
    {
        "key": "instagram_gallery",
        "type": "instagram_gallery",
        "title": "Instagram Gallery",
        "order": 120,
        "config": {
            "title": "Worn by our community.",
            "handle": "hadha.silver",
            "max_items": 9,
            "source": "collections",
        },
    },
    {
        "key": "newsletter",
        "type": "newsletter",
        "title": "Newsletter",
        "order": 130,
        "config": {
            "heading": "Be first to know.",
            "description": "Join the Hadha circle for early access to drops, members-only edits, and quiet little gifts.",
            "placeholder": "Your email address",
            "btn_text": "Subscribe",
            "success_message": "Welcome to the Hadha Circle!",
        },
    },
    {
        "key": "footer",
        "type": "footer",
        "title": "Footer",
        "order": 999,
        "config": {
            "copyright_name": "Hadha Silver Jewellery",
            "company_address": "MVP Sector 1, MVP Colony, Visakhapatnam 530017",
            "phone": "+91 98765 43210",
            "email": "hello@hadha.co",
            "whatsapp": "",
            "instagram": "https://instagram.com/hadha.silver",
            "youtube": "",
            "facebook": "",
            "description": "Popula Dabba's Hadha — handcrafted 92.5 silver jewellery rooted in South Indian heritage, made for everyday and treasured for a lifetime.",
        },
    },
]


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ── Extend landing_sections ───────────────────────────────────────────────
    op.add_column(
        "landing_sections",
        sa.Column("section_type", sa.Text(), server_default="custom", nullable=False),
    )
    op.add_column(
        "landing_sections",
        sa.Column("draft_config", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column(
        "landing_sections",
        sa.Column("status", sa.Text(), server_default="published", nullable=False),
    )
    op.add_column(
        "landing_sections",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "landing_sections",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "landing_sections",
        sa.Column(
            "published_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "landing_sections",
        sa.Column("version_number", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_index(
        "idx_landing_sections_sort_active",
        "landing_sections",
        ["sort_order", "is_active"],
    )

    # ── cms_section_items ─────────────────────────────────────────────────────
    op.create_table(
        "cms_section_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "section_id",
            UUID(as_uuid=True),
            sa.ForeignKey("landing_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("config", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_section_items_section_sort",
        "cms_section_items",
        ["section_id", "sort_order"],
    )

    # ── cms_media ─────────────────────────────────────────────────────────────
    op.create_table(
        "cms_media",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("cdn_url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("folder", sa.String(255), server_default="/", nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "metadata",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_cms_media_folder_created",
        "cms_media",
        ["folder", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── cms_version_history ───────────────────────────────────────────────────
    op.create_table(
        "cms_version_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "section_id",
            UUID(as_uuid=True),
            sa.ForeignKey("landing_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("config_snapshot", JSONB(), nullable=False),
        sa.Column(
            "items_snapshot",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "published_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("change_summary", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("section_id", "version_number", name="uq_section_version"),
    )
    op.create_index(
        "idx_version_history_section",
        "cms_version_history",
        ["section_id", "version_number"],
    )

    # ── cms_cache_version ─────────────────────────────────────────────────────
    op.create_table(
        "cms_cache_version",
        sa.Column("cache_key", sa.String(128), primary_key=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "invalidated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "invalidated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ── cms_publish_log ───────────────────────────────────────────────────────
    op.create_table(
        "cms_publish_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("section_key", sa.String(128), nullable=True),
        sa.Column(
            "admin_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_publish_log_created",
        "cms_publish_log",
        ["created_at"],
    )

    # ── Seed ─────────────────────────────────────────────────────────────────
    conn = op.get_bind()
    for s in _SEED:
        config_json = json.dumps(s["config"])
        conn.execute(
            sa.text(
                "INSERT INTO landing_sections "
                "(id, section_key, section_type, title, sort_order, "
                "config, draft_config, is_active, status, version_number, created_at, updated_at) "
                "VALUES "
                "(gen_random_uuid(), :key, :stype, :title, :order, "
                "CAST(:config AS jsonb), CAST(:config AS jsonb), "
                "true, 'published', 1, NOW(), NOW()) "
                "ON CONFLICT (section_key) DO UPDATE SET "
                "section_type = EXCLUDED.section_type"
            ),
            {
                "key": s["key"],
                "stype": s["type"],
                "title": s["title"],
                "order": s["order"],
                "config": config_json,
            },
        )
    conn.execute(
        sa.text(
            "INSERT INTO cms_cache_version (cache_key, version, invalidated_at) "
            "VALUES ('homepage', 1, NOW()) ON CONFLICT DO NOTHING"
        )
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    op.drop_index("idx_publish_log_created", table_name="cms_publish_log")
    op.drop_table("cms_publish_log")
    op.drop_table("cms_cache_version")
    op.drop_index("idx_version_history_section", table_name="cms_version_history")
    op.drop_table("cms_version_history")
    op.drop_index("idx_cms_media_folder_created", table_name="cms_media")
    op.drop_table("cms_media")
    op.drop_index("idx_section_items_section_sort", table_name="cms_section_items")
    op.drop_table("cms_section_items")
    op.drop_index("idx_landing_sections_sort_active", table_name="landing_sections")
    op.drop_column("landing_sections", "version_number")
    op.drop_column("landing_sections", "published_by")
    op.drop_column("landing_sections", "published_at")
    op.drop_column("landing_sections", "scheduled_at")
    op.drop_column("landing_sections", "status")
    op.drop_column("landing_sections", "draft_config")
    op.drop_column("landing_sections", "section_type")
