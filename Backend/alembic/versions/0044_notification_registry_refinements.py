"""Notification registry refinements — additive, plus one scoped cleanup.

Adds: lifecycle timestamps on notification_logs (sent_at/delivered_at/read_at/
failed_at), template_id/template_version pins on notification_logs, a version
counter on notification_templates, and a notification_template_versions
snapshot-history table.

Also removes the `low_inventory_alert` notification_rules/notification_templates
rows: this event was never wired to a publisher (confirmed via codebase audit —
no LowInventoryEvent, no event_bus.publish call anywhere) and the user opted to
remove it rather than build one. This is the only DELETE in this migration and
is scoped to that single event_type; every other change is additive.

Revision ID: 0044_notification_registry_refinements
Revises: 0043_notification_provider_settings
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0044_notification_registry_refinements"
down_revision: str | None = "0043_notification_provider_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Lifecycle timestamps + template pin on notification_logs
    op.add_column(
        "notification_logs",
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_logs",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_logs",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_logs",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_logs",
        sa.Column("template_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "notification_logs", sa.Column("template_version", sa.Integer, nullable=True)
    )

    # 2. Version counter on notification_templates
    op.add_column(
        "notification_templates",
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
    )

    # 3. Template version snapshot history
    op.create_table(
        "notification_template_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("template_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("template_body", sa.Text, nullable=False),
        sa.Column("variables", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("template_id", "version", name="uq_template_version"),
    )

    # 4. Scoped cleanup — the one orphaned event, removed by explicit user decision.
    op.execute(
        "DELETE FROM notification_templates WHERE event_type = 'low_inventory_alert'"
    )
    op.execute(
        "DELETE FROM notification_rules WHERE event_type = 'low_inventory_alert'"
    )


def downgrade() -> None:
    op.drop_table("notification_template_versions")
    op.drop_column("notification_templates", "version")
    op.drop_column("notification_logs", "template_version")
    op.drop_column("notification_logs", "template_id")
    op.drop_column("notification_logs", "failed_at")
    op.drop_column("notification_logs", "read_at")
    op.drop_column("notification_logs", "delivered_at")
    op.drop_column("notification_logs", "sent_at")
