"""Tests for app.celery_app — configuration, routing, and Beat schedule
completeness. Verifies every former APScheduler job (app/workers/queue.py,
deleted by this migration) has exactly one Celery Beat entry at the same
cadence, per Docs/CELERY_MIGRATION_PLAN.md §5 — except media-sweep-pending,
deliberately widened post-migration from 5s to 15s
(Docs/MEDIA_SWEEP_OPTIMIZATION_REPORT.md)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import app.tasks  # noqa: F401 — registers every task with celery_app
from app.celery_app import celery_app


class TestCeleryConfig:
    def test_broker_is_set(self):
        assert celery_app.conf.broker_url

    def test_broker_uses_dedicated_db_index(self):
        # DB 0 is the app cache, DB 1 is GlitchTip's Valkey — Celery must not
        # collide with either (plan §7).
        assert celery_app.conf.broker_url.rstrip("/").endswith("/2")

    def test_no_result_backend(self):
        assert celery_app.conf.result_backend is None

    def test_json_serialization_only(self):
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.accept_content == ["json"]

    def test_timezone_is_utc(self):
        assert celery_app.conf.timezone == "UTC"
        assert celery_app.conf.enable_utc is True

    def test_acks_late_and_single_prefetch(self):
        """A killed worker's in-flight task must be redelivered, not lost."""
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_no_default_queue_override(self):
        """Every task has an explicit route (asserted below) — a task
        landing on the unrouted default queue is a bug worth surfacing
        loudly, not a queue any worker in this deployment consumes."""
        assert celery_app.conf.task_default_queue in (None, "celery")


EXPECTED_TASK_QUEUES = {
    "media.sweep_pending": "media",
    "media.generate_variants": "media",
    "inventory.expire_reservations": "inventory",
    "notifications.retry_failed": "notifications",
    "cms.publish_scheduled": "cms",
    "admin.cleanup_sessions": "maintenance",
    "maintenance.manage_partitions": "maintenance",
}


class TestTaskRouting:
    def test_every_expected_task_is_registered(self):
        registered = {n for n in celery_app.tasks if not n.startswith("celery.")}
        assert registered == set(EXPECTED_TASK_QUEUES)

    def test_every_task_routes_to_its_declared_queue(self):
        for task_name, queue in EXPECTED_TASK_QUEUES.items():
            route = celery_app.conf.task_routes.get(task_name)
            assert route is not None, f"{task_name} has no route"
            assert route["queue"] == queue


# (Beat cadence, in seconds) — mirrors app/workers/queue.py::build_queue,
# deleted by this migration. Cron entries are asserted separately below.
#
# media-sweep-pending is a deliberate exception: widened from the original
# 5s to 15s post-migration (Docs/MEDIA_SWEEP_OPTIMIZATION_REPORT.md) — the
# 5s figure predates this migration and was never re-justified against the
# actual 120s stale-'processing' threshold once ported over verbatim here.
EXPECTED_INTERVAL_SCHEDULES = {
    "reservation-expiry": ("inventory.expire_reservations", 15),
    "cms-publish": ("cms.publish_scheduled", 60),
    "media-sweep-pending": ("media.sweep_pending", 15),
    "notification-retry": ("notifications.retry_failed", 30),
    "admin-session-cleanup": ("admin.cleanup_sessions", 3600),
}


class TestBeatSchedule:
    def test_every_former_apscheduler_job_has_exactly_one_beat_entry(self):
        schedule = celery_app.conf.beat_schedule
        assert len(schedule) == 6, "expected 6 Beat entries (6 former APScheduler jobs)"

    def test_interval_schedules_match_former_apscheduler_cadences(self):
        schedule = celery_app.conf.beat_schedule
        for entry_name, (task_name, seconds) in EXPECTED_INTERVAL_SCHEDULES.items():
            entry = schedule[entry_name]
            assert entry["task"] == task_name
            assert entry["schedule"] == timedelta(seconds=seconds)

    def test_partition_manager_cron_matches_former_apscheduler_trigger(self):
        """Former: CronTrigger.from_crontab("10 0 1 * *", timezone="UTC")."""
        from celery.schedules import crontab

        entry = celery_app.conf.beat_schedule["partition-manager"]
        assert entry["task"] == "maintenance.manage_partitions"
        assert entry["schedule"] == crontab(minute=10, hour=0, day_of_month=1)


class TestApiNoLongerStartsAScheduler:
    """Item 14/33 of the migration brief: API containers must not start
    APScheduler, WorkerLeader, or any scheduler after this migration."""

    def test_main_py_does_not_reference_apscheduler_or_worker_leader(self):
        main_source = (
            Path(__file__).resolve().parent.parent.parent / "app" / "main.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "AsyncIOScheduler",
            "apscheduler",
            "WorkerLeader",
            "worker_leader",
            "build_queue",
        ):
            assert forbidden not in main_source, f"main.py still references {forbidden}"

    def test_apscheduler_not_in_requirements(self):
        req_path = Path(__file__).resolve().parent.parent.parent / "requirements.txt"
        assert "APScheduler" not in req_path.read_text(encoding="utf-8")
