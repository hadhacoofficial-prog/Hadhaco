"""Tests for the Notification Event Registry sync behavior."""

from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from app.modules.notifications.event_registry import (
    NOTIFICATION_EVENTS,
    NotificationCategory,
    sync_notification_rules,
)


class TestEventRegistryCategories:
    def test_no_low_inventory_alert_entry(self):
        event_types = {e.event_type for e in NOTIFICATION_EVENTS}
        assert "low_inventory_alert" not in event_types

    def test_every_category_is_a_valid_enum_member(self):
        valid = {c.value for c in NotificationCategory}
        for event in NOTIFICATION_EVENTS:
            assert event.category.value in valid


class TestSyncNotificationRules:
    async def test_sync_updates_only_descriptive_fields_on_conflict(self):
        db = AsyncMock()
        await sync_notification_rules(db)

        assert db.execute.await_count == len(NOTIFICATION_EVENTS)
        for call in db.execute.call_args_list:
            stmt = call.args[0]
            compiled = str(
                stmt.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            do_update_clause = compiled.split("DO UPDATE SET")[1]
            # Descriptive metadata IS refreshed from the registry...
            for col in (
                "display_name",
                "category",
                "description",
                "is_system",
                "display_order",
            ):
                assert col in do_update_clause
            # ...but admin-editable fields are never part of the UPDATE SET.
            for col in (
                "enabled",
                "email_enabled",
                "whatsapp_enabled",
                "priority",
                "retry_policy",
                "cooldown_seconds",
                "customer_visible",
                "admin_visible",
            ):
                assert col not in do_update_clause
        db.commit.assert_awaited_once()
