"""Post-delivery review CTA — re-seed the order-delivered templates.

The delivered email gains the product list plus a per-product "Write a Review"
section (each button deep-links to that product page's review section via
`item.review_url`), and the delivered WhatsApp body gains the review feedback
line. Content comes from `app.modules.notifications.emails.catalog`, the same
single source of truth migration 0051 seeds from, and uses the identical
snapshot-then-update mechanism: current content is copied into
`notification_template_versions` before the upgrade so admins can restore it.
Idempotent — rows already matching the catalog are skipped.

Revision ID: 0052_delivered_review_cta_templates
Revises: 0051_premium_notification_templates
Create Date: 2026-07-16
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.modules.notifications.emails.catalog import ALL_TEMPLATES

revision: str = "0052_delivered_review_cta_templates"
down_revision: str | None = "0051_premium_notification_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Only the order-delivered pair changes in this revision.
_TEMPLATE_NAMES = ["order_delivered_email", "order_delivered_whatsapp"]


def upgrade() -> None:
    conn = op.get_bind()

    for tpl in ALL_TEMPLATES:
        if tpl.name not in _TEMPLATE_NAMES:
            continue
        variables_json = (
            json.dumps(tpl.variables) if tpl.variables is not None else None
        )
        row = (
            conn.execute(
                sa.text(
                    "SELECT id, subject, template_body, variables, version "
                    "FROM notification_templates WHERE name = :name"
                ),
                {"name": tpl.name},
            )
            .mappings()
            .first()
        )

        if row is None:
            conn.execute(
                sa.text(
                    "INSERT INTO notification_templates "
                    "(name, channel, event_type, subject, template_body, "
                    "variables, is_active, version) "
                    "VALUES (:name, :channel, :event_type, :subject, :body, "
                    "CAST(:variables AS JSONB), TRUE, 1) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {
                    "name": tpl.name,
                    "channel": tpl.channel,
                    "event_type": tpl.event_type,
                    "subject": tpl.subject,
                    "body": tpl.body,
                    "variables": variables_json,
                },
            )
            continue

        unchanged = (
            row["template_body"] == tpl.body
            and row["subject"] == tpl.subject
            and (row["variables"] or None) == (tpl.variables or None)
        )
        if unchanged:
            continue

        # Snapshot the current content so admins can restore it, then upgrade.
        conn.execute(
            sa.text(
                "INSERT INTO notification_template_versions "
                "(template_id, version, subject, template_body, variables) "
                "VALUES (:template_id, :version, :subject, :body, "
                "CAST(:variables AS JSONB)) "
                "ON CONFLICT (template_id, version) DO NOTHING"
            ),
            {
                "template_id": row["id"],
                "version": row["version"],
                "subject": row["subject"],
                "body": row["template_body"],
                "variables": (
                    json.dumps(row["variables"])
                    if row["variables"] is not None
                    else None
                ),
            },
        )
        conn.execute(
            sa.text(
                "UPDATE notification_templates "
                "SET subject = :subject, template_body = :body, "
                "variables = CAST(:variables AS JSONB), "
                "version = version + 1, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "subject": tpl.subject,
                "body": tpl.body,
                "variables": variables_json,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Restore each upgraded template from the snapshot taken in upgrade() —
    # best-effort: the most recent snapshot below the current version.
    for name in _TEMPLATE_NAMES:
        row = (
            conn.execute(
                sa.text(
                    "SELECT id, version FROM notification_templates "
                    "WHERE name = :name"
                ),
                {"name": name},
            )
            .mappings()
            .first()
        )
        if row is None:
            continue
        snap = (
            conn.execute(
                sa.text(
                    "SELECT version, subject, template_body, variables "
                    "FROM notification_template_versions "
                    "WHERE template_id = :tid AND version < :v "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"tid": row["id"], "v": row["version"]},
            )
            .mappings()
            .first()
        )
        if snap is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE notification_templates "
                "SET subject = :subject, template_body = :body, "
                "variables = CAST(:variables AS JSONB), version = :version, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {
                "id": row["id"],
                "subject": snap["subject"],
                "body": snap["template_body"],
                "variables": (
                    json.dumps(snap["variables"])
                    if snap["variables"] is not None
                    else None
                ),
                "version": snap["version"],
            },
        )
