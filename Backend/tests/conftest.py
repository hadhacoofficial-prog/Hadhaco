"""Shared test fixtures.

Test settings are injected via environment variables BEFORE any app import,
so app.core.config.Settings resolves without a real .env. No external service
is contacted: unit tests exercise pure logic, integration tests drive the
ASGI app in-process without running the lifespan (no DB/Redis needed).
"""
import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env.test"


def _load_test_env() -> None:
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_test_env()

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture(scope="session")
def app():
    from app.main import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """In-process HTTP client. Lifespan is NOT run — DB/Redis are not required."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
