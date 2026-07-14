"""Tests for the reservation expiry background worker."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


class TestReservationExpiryWorker:
    async def test_run_delegates_to_run_with_session(self):
        with patch(
            "app.workers.reservation_expiry.run_with_session", AsyncMock()
        ) as mock_runner:
            from app.workers.reservation_expiry import run

            await run()

            mock_runner.assert_called_once()
            fn = mock_runner.call_args[0][0]
            assert callable(fn)

    async def test_expire_reservations_calls_inventory_service(self):
        """_expire_reservations calls ReservationService.expire_stale_reservations."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_inv_svc = AsyncMock()
        mock_inv_svc.expire_stale_reservations = AsyncMock(return_value=[])

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_inv_svc,
        ):
            await reservation_expiry._expire_reservations(db)

            mock_inv_svc.expire_stale_reservations.assert_called_once_with(db)

    async def test_expire_reservations_calls_order_side_effects_when_orders_expired(
        self,
    ):
        """When order IDs are returned, OrderService.handle_expired_order_side_effects is called."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        order_ids = [uuid.uuid4(), uuid.uuid4()]

        mock_inv_svc = AsyncMock()
        mock_inv_svc.expire_stale_reservations = AsyncMock(return_value=order_ids)

        mock_order_svc = AsyncMock()
        mock_order_svc.handle_expired_order_side_effects = AsyncMock()

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_inv_svc,
        ):
            with patch(
                "app.modules.orders.service.OrderService",
                return_value=mock_order_svc,
            ):
                await reservation_expiry._expire_reservations(db)

                mock_order_svc.handle_expired_order_side_effects.assert_called_once_with(
                    db, order_ids
                )

    async def test_expire_reservations_skips_side_effects_when_no_orders(self):
        """When no order IDs returned, OrderService is never called."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_inv_svc = AsyncMock()
        mock_inv_svc.expire_stale_reservations = AsyncMock(return_value=[])

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_inv_svc,
        ):
            with patch("app.modules.orders.service.OrderService") as mock_order_cls:
                await reservation_expiry._expire_reservations(db)

                mock_order_cls.assert_not_called()

    async def test_expire_reservations_logs_when_expired(self):
        """When orders are expired, the worker logs an info message."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        order_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        mock_inv_svc = AsyncMock()
        mock_inv_svc.expire_stale_reservations = AsyncMock(return_value=order_ids)

        mock_order_svc = AsyncMock()
        mock_order_svc.handle_expired_order_side_effects = AsyncMock()

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_inv_svc,
        ):
            with patch(
                "app.modules.orders.service.OrderService",
                return_value=mock_order_svc,
            ):
                with patch("app.workers.reservation_expiry.log") as mock_log:
                    await reservation_expiry._expire_reservations(db)

                    mock_log.info.assert_called_once_with(
                        "reservations_expired_batch", count=3
                    )

    async def test_expire_reservations_does_not_log_info_when_empty(self):
        """When no orders expired, no info log (only debug)."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_inv_svc = AsyncMock()
        mock_inv_svc.expire_stale_reservations = AsyncMock(return_value=[])

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_inv_svc,
        ):
            with patch("app.workers.reservation_expiry.log") as mock_log:
                await reservation_expiry._expire_reservations(db)

                mock_log.info.assert_not_called()
                mock_log.debug.assert_called_once()

    async def test_expire_reservations_propagates_exception(self):
        """If the service raises, the worker propagates."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_inv_svc = AsyncMock()
        mock_inv_svc.expire_stale_reservations = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_inv_svc,
        ):
            with pytest.raises(RuntimeError, match="DB connection lost"):
                await reservation_expiry._expire_reservations(db)
