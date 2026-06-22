"""Extended worker tests covering run() functions with mocked DB sessions."""

from unittest.mock import AsyncMock, MagicMock, patch


def _make_session_mock():
    """Return a mock that acts as an async context manager."""
    mock_db = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    return mock_db


class TestShipmentSyncWorker:
    async def test_run_with_no_shipped_orders(self):
        import app.workers.shipment_sync as worker

        mock_db = _make_session_mock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.workers.shipment_sync.AsyncSessionLocal", return_value=mock_db):
            await worker.run()

    async def test_run_handles_sync_exception_gracefully(self):
        import uuid

        import app.workers.shipment_sync as worker

        mock_db = _make_session_mock()

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.workers.shipment_sync.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.workers.shipment_sync._shipping.sync_shipment_status",
                AsyncMock(side_effect=RuntimeError("timeout")),
            ),
        ):
            await worker.run()  # Should not propagate the exception


class TestInventoryAlertsWorker:
    async def test_run_with_no_low_stock_products(self):
        import app.workers.inventory_alerts as worker

        mock_db = _make_session_mock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.workers.inventory_alerts.AsyncSessionLocal", return_value=mock_db),
            patch("app.workers.inventory_alerts.event_bus.publish", AsyncMock()),
        ):
            await worker.run()

    async def test_run_publishes_events_for_low_stock(self):
        import uuid

        import app.workers.inventory_alerts as worker

        mock_db = _make_session_mock()

        mock_row = {
            "id": uuid.uuid4(),
            "name": "Silver Ring",
            "sku": "SR-001",
            "stock_quantity": 2,
            "low_stock_threshold": 5,
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [mock_row]
        mock_db.execute = AsyncMock(return_value=mock_result)

        published_events = []

        async def capture_publish(event):
            published_events.append(event)

        with (
            patch("app.workers.inventory_alerts.AsyncSessionLocal", return_value=mock_db),
            patch("app.workers.inventory_alerts.event_bus.publish", capture_publish),
        ):
            await worker.run()

        assert len(published_events) == 1
        assert published_events[0].product_id == str(mock_row["id"])


class TestNotificationRetryWorker:
    async def test_run_calls_retry_pending(self):
        import app.workers.notification_retry as worker

        mock_db = _make_session_mock()
        mock_retry = AsyncMock()

        with (
            patch("app.workers.notification_retry.AsyncSessionLocal", return_value=mock_db),
            patch.object(type(worker._svc), "retry_pending", mock_retry),
        ):
            await worker.run()

        mock_retry.assert_called_once()


class TestPartitionManagerWorker:
    async def test_run_executes_two_sql_statements(self):
        import app.workers.partition_manager as worker

        mock_db = _make_session_mock()
        execute_calls = []

        async def capture_execute(sql, *args, **kwargs):
            execute_calls.append(sql)
            return MagicMock()

        mock_db.execute = capture_execute
        mock_db.commit = AsyncMock()

        with patch("app.workers.partition_manager.AsyncSessionLocal", return_value=mock_db):
            await worker.run()

        assert len(execute_calls) == 2


class TestReviewReminderWorker:
    async def test_run_with_no_candidates(self):
        import app.workers.review_reminder as worker

        mock_db = _make_session_mock()
        mock_result = MagicMock()
        mock_result.all.return_value = []  # note: .all() not .mappings().all()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.workers.review_reminder.AsyncSessionLocal", return_value=mock_db),
            patch("app.workers.review_reminder.event_bus.publish", AsyncMock()),
        ):
            await worker.run()

    async def test_run_skips_orders_already_reviewed(self):
        import uuid

        import app.workers.review_reminder as worker

        mock_db = _make_session_mock()

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.user_id = uuid.uuid4()
        mock_order.order_number = "ORD-001"
        customer_email = "test@example.com"
        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_order, customer_email)]
        mock_db.execute = AsyncMock(return_value=mock_result)

        published_events = []

        async def capture_publish(event):
            published_events.append(event)

        with (
            patch("app.workers.review_reminder.AsyncSessionLocal", return_value=mock_db),
            patch.object(type(worker._review_repo), "has_any_review", AsyncMock(return_value=True)),
            patch("app.workers.review_reminder.event_bus.publish", capture_publish),
        ):
            await worker.run()

        assert published_events == []  # already reviewed — no event sent


class TestAbandonedCartWorker:
    async def test_run_returns_early_when_feature_disabled(self):
        import app.workers.abandoned_cart as worker

        mock_db = _make_session_mock()
        mock_db.execute = AsyncMock()

        # SettingsService is imported inside run(), so patch at the definition site
        with (
            patch("app.workers.abandoned_cart.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.modules.settings.service.SettingsService.is_feature_enabled",
                AsyncMock(return_value=False),
            ),
        ):
            await worker.run()

        mock_db.execute.assert_not_called()

    async def test_run_with_no_carts_when_feature_enabled(self):
        import app.workers.abandoned_cart as worker

        mock_db = _make_session_mock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.workers.abandoned_cart.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.modules.settings.service.SettingsService.is_feature_enabled",
                AsyncMock(return_value=True),
            ),
        ):
            await worker.run()
