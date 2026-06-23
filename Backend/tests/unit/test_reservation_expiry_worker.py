"""Tests for the reservation expiry background worker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestReservationExpiryWorker:
    async def test_run_delegates_to_run_with_session(self):
        with patch(
            "app.workers.reservation_expiry.run_with_session", AsyncMock()
        ) as mock_runner:
            from app.workers.reservation_expiry import run

            await run()

            mock_runner.assert_called_once()
            # First arg is the actual coroutine function _expire_reservations
            fn = mock_runner.call_args[0][0]
            assert callable(fn)

    async def test_expire_reservations_calls_service(self):
        """_expire_reservations calls ReservationService.expire_stale_reservations."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_svc = AsyncMock()
        mock_svc.expire_stale_reservations = AsyncMock(return_value=3)

        # ReservationService is imported locally inside _expire_reservations,
        # so we patch it at the source module where it's defined.
        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_svc,
        ):
            await reservation_expiry._expire_reservations(db)

            mock_svc.expire_stale_reservations.assert_called_once_with(db)

    async def test_expire_reservations_logs_when_expired(self):
        """When count > 0, the worker logs an info message."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.expire_stale_reservations = AsyncMock(return_value=5)

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_svc,
        ):
            with patch("app.workers.reservation_expiry.log") as mock_log:
                await reservation_expiry._expire_reservations(db)

                mock_log.info.assert_called_once_with(
                    "reservations_expired_batch", count=5
                )

    async def test_expire_reservations_does_not_log_info_when_zero(self):
        """When count == 0, no info log (only debug)."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.expire_stale_reservations = AsyncMock(return_value=0)

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_svc,
        ):
            with patch("app.workers.reservation_expiry.log") as mock_log:
                await reservation_expiry._expire_reservations(db)

                mock_log.info.assert_not_called()
                mock_log.debug.assert_called_once()

    async def test_expire_reservations_propagates_exception(self):
        """If the service raises, the worker propagates (caller handles retry logic)."""
        from app.workers import reservation_expiry

        db = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.expire_stale_reservations = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )

        with patch(
            "app.modules.inventory.reservation_service.ReservationService",
            return_value=mock_svc,
        ):
            with pytest.raises(RuntimeError, match="DB connection lost"):
                await reservation_expiry._expire_reservations(db)
