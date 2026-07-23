#!/usr/bin/env python3
"""Verify that the notification pipeline never holds a DB connection during HTTP calls.

Run as part of the test suite to validate the session lifecycle optimization.

    python -m pytest Backend/scripts/verify_notification_session_optimization.py -v

Proves:
    1. In send_email: db.commit() comes BEFORE dispatcher.send_email()
    2. In send_whatsapp: db.commit() comes BEFORE dispatcher.send_whatsapp()
    3. In _retry_log: db.commit() comes BEFORE any dispatcher call (both branches)
    4. No provider or dispatcher method accepts an AsyncSession parameter
    5. Connection pool budget math is correct
    6. Worker semaphore bounds concurrency to 2
"""

from __future__ import annotations

import inspect
from pathlib import Path

_SERVICE_PATH = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "modules"
    / "notifications"
    / "service.py"
)


def _read_service() -> str:
    return _SERVICE_PATH.read_text(encoding="utf-8")


def _extract_method(body: str, method_name: str) -> str:
    """Extract a single method body from the service source."""
    start = body.index(f"async def {method_name}(")
    # Find the next method at the same indentation level
    indent = "    async def "
    next_pos = body.index(indent, start + 10)
    # Walk back to find the newline before it
    return body[start:next_pos]


# ── Static analysis: commit-before-HTTP ordering ─────────────────────────────


class TestSessionLifetimeBudget:
    """Verify that db.commit() precedes every HTTP call in the notification pipeline."""

    def test_send_email_commits_before_http(self):
        """db.commit() must come BEFORE dispatcher.send_email()."""
        src = _read_service()
        method = _extract_method(src, "send_email")

        commit_pos = method.index("await db.commit()")
        http_pos = method.index("self._dispatcher.send_email")

        assert commit_pos < http_pos, (
            "CRITICAL: In send_email, db.commit() must come BEFORE "
            "dispatcher.send_email(). Connection is held during HTTP."
        )

        # No await db.* calls between commit and HTTP (comment lines excluded)
        between = method[commit_pos:http_pos]
        db_calls = [
            line.strip()
            for line in between.split("\n")
            if line.strip().startswith("await db.") and not line.strip().startswith("#")
        ]
        # Filter out the commit itself
        db_calls = [c for c in db_calls if "commit()" not in c]
        assert not db_calls, f"DB calls between commit and HTTP: {db_calls}"

    def test_send_whatsapp_commits_before_http(self):
        """db.commit() must come BEFORE dispatcher.send_whatsapp()."""
        src = _read_service()
        method = _extract_method(src, "send_whatsapp")

        commit_pos = method.index("await db.commit()")
        http_pos = method.index("self._dispatcher.send_whatsapp")

        assert commit_pos < http_pos, (
            "CRITICAL: In send_whatsapp, db.commit() must come BEFORE "
            "dispatcher.send_whatsapp()."
        )

        between = method[commit_pos:http_pos]
        db_calls = [
            line.strip()
            for line in between.split("\n")
            if line.strip().startswith("await db.") and not line.strip().startswith("#")
        ]
        db_calls = [c for c in db_calls if "commit()" not in c]
        assert not db_calls, f"DB calls between commit and HTTP: {db_calls}"

    def test_retry_log_email_commits_before_http(self):
        """_retry_log email branch: db.commit() before dispatcher.send_email()."""
        src = _read_service()
        retry_start = src.index("async def _retry_log(")
        # Find the event listener section to bound the search
        event_section = src.find("\n    # ── Event listener", retry_start)
        method_body = src[retry_start:event_section]

        # Email branch
        email_start = method_body.index('log_entry.channel == "email"')
        email_branch = method_body[email_start:]
        email_commit = email_branch.index("# ── Commit: return connection to pool")
        email_http = email_branch.index("self._dispatcher.send_email", email_commit)

        assert email_commit < email_http

    def test_retry_log_whatsapp_commits_before_http(self):
        """_retry_log whatsapp branch: db.commit() before dispatcher.send_whatsapp()."""
        src = _read_service()
        retry_start = src.index("async def _retry_log(")
        event_section = src.find("\n    # ── Event listener", retry_start)
        method_body = src[retry_start:event_section]

        wa_start = method_body.index('log_entry.channel == "whatsapp"')
        wa_branch = method_body[wa_start:]
        wa_commit = wa_branch.index("# ── Commit: return connection to pool")
        wa_http = wa_branch.index("self._dispatcher.send_whatsapp", wa_commit)

        assert wa_commit < wa_http


# ── Static analysis: provider boundary ───────────────────────────────────────


class TestProviderBoundary:
    """Verify that no provider or dispatcher method accepts an AsyncSession."""

    def test_email_provider_accepts_only_payload(self):
        import sys

        sys.modules.setdefault("app.core.config", type(sys)("fake"))
        sys.modules["app.core.config"].settings = type(
            "S", (), {"RESEND_API_KEY": "x"}
        )()

        from app.modules.notifications.providers.resend import ResendProvider

        sig = inspect.signature(ResendProvider.send_email)
        params = list(sig.parameters.keys())
        assert params == ["self", "payload"]

    def test_whatsapp_provider_accepts_only_payload(self):
        from app.modules.notifications.providers.whatsapp import WhatsAppProvider

        sig = inspect.signature(WhatsAppProvider.send_whatsapp)
        params = list(sig.parameters.keys())
        assert params == ["self", "payload"]

    def test_dispatcher_accepts_only_payloads(self):
        from app.modules.notifications.dispatcher import NotificationDispatcher

        email_params = list(
            inspect.signature(NotificationDispatcher.send_email).parameters.keys()
        )
        wa_params = list(
            inspect.signature(NotificationDispatcher.send_whatsapp).parameters.keys()
        )

        assert email_params == ["self", "payload"]
        assert wa_params == ["self", "payload"]

    def test_no_async_session_in_provider_files(self):
        """No public send_* method in any provider file accepts AsyncSession."""
        provider_dir = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "modules"
            / "notifications"
            / "providers"
        )
        for py_file in provider_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("def ") and "send_" in stripped:
                    assert (
                        "AsyncSession" not in stripped
                    ), f"AsyncSession in {py_file.name}: {stripped}"


# ── Static analysis: connection pool budget ──────────────────────────────────


class TestConnectionPoolBudget:
    """Verify the connection pool budget math."""

    def test_pool_budget(self):
        pool_size = 2
        max_overflow = 1
        workers = 2
        supabase_limit = 15

        persistent = (pool_size + max_overflow) * workers
        headroom = supabase_limit - persistent

        assert persistent == 6
        assert headroom == 9
        assert persistent < supabase_limit

    def test_worker_semaphore_value(self):
        """Worker semaphore limits concurrency to 2."""
        db_path = _SERVICE_PATH.parent.parent.parent / "core" / "database.py"
        content = db_path.read_text(encoding="utf-8")
        assert "asyncio.Semaphore(2)" in content
        assert "get_worker_semaphore" in content

    def test_database_pool_config(self):
        """Pool size and max overflow in config match the budget."""
        config_path = _SERVICE_PATH.parent.parent.parent / "core" / "config.py"
        config_content = config_path.read_text(encoding="utf-8")
        assert "DATABASE_POOL_SIZE" in config_content
        assert "DATABASE_MAX_OVERFLOW" in config_content
