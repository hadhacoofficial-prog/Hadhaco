"""Tests for the Phase 2 backend additions: retry-by-id, template
restore/duplicate, provider enable/disable gating, WhatsApp template sync,
last_triggered/last_sent on rules, and logs search/category filtering."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService


class TestRetryLogById:
    def setup_method(self):
        self.svc = NotificationService()

    async def test_retry_log_by_id_returns_false_when_missing(self):
        db = AsyncMock()
        with patch.object(
            NotificationRepository, "get_log_by_id", AsyncMock(return_value=None)
        ):
            result = await self.svc.retry_log_by_id(db, uuid.uuid4())
        assert result is False

    async def test_retry_log_by_id_uses_pinned_template(self):
        db = AsyncMock()
        log = MagicMock()
        log.template_id = uuid.uuid4()
        template = MagicMock()
        with (
            patch.object(
                NotificationRepository, "get_log_by_id", AsyncMock(return_value=log)
            ),
            patch.object(
                NotificationRepository,
                "get_template_by_id",
                AsyncMock(return_value=template),
            ) as mock_by_id,
            patch.object(self.svc, "_retry_log", AsyncMock()) as mock_retry,
        ):
            result = await self.svc.retry_log_by_id(db, uuid.uuid4())
        assert result is True
        mock_by_id.assert_awaited_once_with(db, log.template_id)
        mock_retry.assert_awaited_once_with(db, log, template)

    async def test_retry_log_by_id_falls_back_to_active_template(self):
        db = AsyncMock()
        log = MagicMock()
        log.template_id = None
        log.event_type = "order_created"
        log.channel = "email"
        template = MagicMock()
        with (
            patch.object(
                NotificationRepository, "get_log_by_id", AsyncMock(return_value=log)
            ),
            patch.object(
                NotificationRepository,
                "get_template",
                AsyncMock(return_value=template),
            ) as mock_get_template,
            patch.object(self.svc, "_retry_log", AsyncMock()),
        ):
            result = await self.svc.retry_log_by_id(db, uuid.uuid4())
        assert result is True
        mock_get_template.assert_awaited_once_with(
            db, event_type="order_created", channel="email"
        )


class TestTemplateDuplicateAndRestore:
    def setup_method(self):
        self.repo = NotificationRepository()

    async def test_duplicate_template_returns_none_when_missing(self):
        db = AsyncMock()
        with patch.object(
            NotificationRepository, "get_template_by_id", AsyncMock(return_value=None)
        ):
            result = await self.repo.duplicate_template(db, uuid.uuid4())
        assert result is None

    async def test_duplicate_template_creates_inactive_copy(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        source = MagicMock()
        source.name = "order_created_email"
        source.channel = "email"
        source.event_type = "order_created"
        source.subject = "Hi"
        source.template_body = "Body"
        source.variables = None
        with patch.object(
            NotificationRepository,
            "get_template_by_id",
            AsyncMock(return_value=source),
        ):
            result = await self.repo.duplicate_template(db, uuid.uuid4())
        assert result is not None
        assert result.is_active is False
        assert result.name.startswith("order_created_email_copy_")
        db.add.assert_called_once()

    async def test_restore_uses_snapshot_content_via_update_template(self):
        db = AsyncMock()
        template_id = uuid.uuid4()
        snapshot = MagicMock()
        snapshot.subject = "Old subject"
        snapshot.template_body = "Old body"
        snapshot.variables = {"params": ["x"]}
        restored_template = MagicMock()

        with (
            patch.object(
                NotificationRepository,
                "get_template_version",
                AsyncMock(return_value=snapshot),
            ),
            patch.object(
                NotificationRepository,
                "update_template",
                AsyncMock(return_value=restored_template),
            ) as mock_update,
        ):
            snapshot_result = await self.repo.get_template_version(db, template_id, 1)
            result = await self.repo.update_template(
                db,
                template_id,
                {
                    "subject": snapshot_result.subject,
                    "template_body": snapshot_result.template_body,
                    "variables": snapshot_result.variables,
                },
                updated_by=None,
            )
        assert result is restored_template
        mock_update.assert_awaited_once()
        called_data = mock_update.call_args.args[2]
        assert called_data["template_body"] == "Old body"


class TestProviderEnabledGating:
    async def test_provider_enabled_defaults_true_when_unset(self):
        svc = NotificationService()
        db = AsyncMock()
        with patch.object(
            svc._settings_repo, "get_provider_config", AsyncMock(return_value={})
        ):
            result = await svc._provider_enabled(db, "email")
        assert result is True

    async def test_provider_enabled_false_when_explicitly_disabled(self):
        svc = NotificationService()
        db = AsyncMock()
        with patch.object(
            svc._settings_repo,
            "get_provider_config",
            AsyncMock(return_value={"enabled": "false"}),
        ):
            result = await svc._provider_enabled(db, "whatsapp")
        assert result is False


class TestWhatsAppTemplateSync:
    async def test_list_whatsapp_templates_returns_empty_when_not_configured(self):
        svc = SettingsService()
        db = AsyncMock()
        with patch(
            "app.modules.settings.service._repo.get_provider_config",
            AsyncMock(return_value={}),
        ):
            result = await svc.list_whatsapp_templates(db)
        assert result == []

    async def test_list_whatsapp_templates_maps_meta_response(self):
        svc = SettingsService()
        db = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {
                    "name": "order_created",
                    "language": "en_US",
                    "status": "APPROVED",
                    "category": "TRANSACTIONAL",
                }
            ]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        with (
            patch(
                "app.modules.settings.service._repo.get_provider_config",
                AsyncMock(return_value={"access_token": "tok", "waba_id": "12345"}),
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await svc.list_whatsapp_templates(db)
        assert result == [
            {
                "name": "order_created",
                "language": "en_US",
                "status": "APPROVED",
                "category": "TRANSACTIONAL",
            }
        ]


class TestRulesLastTriggeredAndSent:
    async def test_list_rules_attaches_last_triggered_and_sent(self):
        rule = MagicMock()
        rule.event_type = "order_created"

        rules_result = MagicMock()
        rules_result.scalars.return_value.all.return_value = [rule]

        triggered_row = MagicMock()
        triggered_row.event_type = "order_created"
        triggered_row.last_triggered_at = "2026-07-01T00:00:00Z"
        triggered_result = MagicMock()
        triggered_result.all.return_value = [triggered_row]

        sent_row = MagicMock()
        sent_row.event_type = "order_created"
        sent_row.last_sent_at = "2026-07-02T00:00:00Z"
        sent_result = MagicMock()
        sent_result.all.return_value = [sent_row]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[rules_result, triggered_result, sent_result]
        )

        repo = NotificationRepository()
        result = await repo.list_rules(db)

        assert result == [rule]
        assert rule.last_triggered_at == "2026-07-01T00:00:00Z"
        assert rule.last_sent_at == "2026-07-02T00:00:00Z"


class TestLogsSearchAndCategoryFilter:
    async def test_list_logs_search_matches_uuid_exact(self):
        log_id = uuid.uuid4()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        logs_result = MagicMock()
        logs_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[count_result, logs_result])

        repo = NotificationRepository()
        _, total = await repo.list_logs(db, search=str(log_id))
        assert total == 1

    async def test_list_logs_search_text_falls_back_to_ilike(self):
        count_result = MagicMock()
        count_result.scalar.return_value = 3
        logs_result = MagicMock()
        logs_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[count_result, logs_result])

        repo = NotificationRepository()
        _, total = await repo.list_logs(db, search="+91999")
        assert total == 3
