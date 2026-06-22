"""Unit tests for the APScheduler queue service."""

from unittest.mock import MagicMock, patch


class TestQueueService:
    def test_queue_service_starts_scheduler(self):
        from app.workers.queue import QueueService

        svc = QueueService()
        with patch.object(svc._scheduler, "start") as mock_start:
            svc.start()
            mock_start.assert_called_once()

    def test_queue_service_shutdown_when_running(self):

        from app.workers.queue import QueueService

        svc = QueueService()
        # Start the scheduler first so running=True, then shut it down
        with patch.object(svc._scheduler, "start"):
            svc._scheduler._state = 1  # RUNNING state in APScheduler
        with patch.object(svc._scheduler, "shutdown") as mock_shutdown:
            with patch.object(
                type(svc._scheduler),
                "running",
                new_callable=lambda: property(lambda self: True),
            ):
                svc.shutdown()
                mock_shutdown.assert_called_once_with(wait=False)

    def test_queue_service_shutdown_not_called_when_already_stopped(self):
        from app.workers.queue import QueueService

        svc = QueueService()
        # Scheduler not started → running=False → shutdown() skips the call
        with patch.object(svc._scheduler, "shutdown") as mock_shutdown:
            svc.shutdown()  # running is False by default (not started)
            mock_shutdown.assert_not_called()

    def test_add_interval_job_registers_with_correct_id(self):
        from app.workers.queue import QueueService

        svc = QueueService()
        mock_fn = MagicMock()
        with patch.object(svc._scheduler, "add_job") as mock_add:
            svc.add_interval_job(mock_fn, seconds=60, job_id="test_job")
            mock_add.assert_called_once()
            call_kwargs = mock_add.call_args[1]
            assert call_kwargs["id"] == "test_job"
            assert call_kwargs["max_instances"] == 1

    def test_add_cron_job_registers_with_correct_id(self):
        from app.workers.queue import QueueService

        svc = QueueService()
        mock_fn = MagicMock()
        with patch.object(svc._scheduler, "add_job") as mock_add:
            svc.add_cron_job(mock_fn, cron="10 0 1 * *", job_id="cron_job")
            mock_add.assert_called_once()
            call_kwargs = mock_add.call_args[1]
            assert call_kwargs["id"] == "cron_job"

    def test_build_queue_returns_queue_service(self):
        from app.workers.queue import QueueService, build_queue

        with (
            patch.object(QueueService, "add_interval_job"),
            patch.object(QueueService, "add_cron_job"),
        ):
            q = build_queue()
            assert isinstance(q, QueueService)

    def test_build_queue_registers_exactly_seven_workers(self):
        from app.workers.queue import QueueService, build_queue

        interval_ids = []
        cron_ids = []

        def capture_interval(self, fn, *, seconds, job_id):
            interval_ids.append(job_id)

        def capture_cron(self, fn, *, cron, job_id):
            cron_ids.append(job_id)

        with (
            patch.object(QueueService, "add_interval_job", capture_interval),
            patch.object(QueueService, "add_cron_job", capture_cron),
        ):
            build_queue()

        assert len(interval_ids) + len(cron_ids) == 7
        assert "partition_manager" in cron_ids
        assert "shipment_sync" in interval_ids
        assert "abandoned_cart" in interval_ids
        assert "inventory_alerts" in interval_ids
        assert "notification_retry" in interval_ids
        assert "review_reminder" in interval_ids
