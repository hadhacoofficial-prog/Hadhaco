"""In-process performance-delta harness (BEFORE vs AFTER evidence).

Runs the real service/repository/route code against recording stubs so no
network, no database, and no production Redis is ever touched. Each test
counts DB round-trips (AsyncSession.execute/commit/rollback) and Redis
operation counts (get/setex/delete/scan_iter) and appends a JSON line to
``$PERF_RESULTS_DIR`` (default: ``tests/measurement/results``).

The same file is executed in the AFTER worktree (staged changes) and the
BEFORE worktree (``git worktree`` at HEAD) so the emitted JSONL can be
diffed per metric. Assertions are intentionally sanity-bounds only - the
BEFORE/AFTER delta is read from the recorded numbers, not asserted here.
"""

import asyncio
import json
import os
import re
import subprocess
import time
import uuid
from collections.abc import Callable
from fnmatch import translate
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import app.modules.categories.models  # noqa: E402,F401  (register Category mapper)
from app.core import cache_warmer
from app.core import database as dbmod
from app.core import redis as redis_mod
from app.core.cache import _compress_value, cache_swr
from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.auth.service import AuthService
from app.modules.catalog import router as catalog_router
from app.modules.catalog.repository import ProductRepository
from app.modules.catalog.schemas import ProductVariantUpdateRequest
from app.modules.catalog.service import CatalogService
from app.modules.collections.repository import CollectionRepository
from app.modules.media import router as media_router

_RESULTS: dict[str, int] = {}
_RESULTS_DIR = Path(
    os.environ.get("PERF_RESULTS_DIR") or Path(__file__).parent / "results"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _record(key: str, value: int) -> None:
    _RESULTS[key] = value


def _repo_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _repo_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return out.stdout.strip() or "detached"
    except Exception:
        return "unknown"


def _wrap(data: Any, ts: float) -> bytes:
    return _compress_value(json.dumps({"d": data, "t": ts}))


# --------------------------------------------------------------------------
# Recording stubs
# --------------------------------------------------------------------------


class RecordingResult:
    """A stand-in for a SQLAlchemy ``Result`` with configurable rows.

    Defaults to an empty result set so most read paths degrade gracefully
    (empty list, ``None`` scalar). ``one()`` returns a row whose shape matches
    the 2FA-gate query (``has_2fa`` / ``session_verified``).
    """

    def __init__(
        self,
        *,
        scalars_items: list[Any] | None = None,
        scalar_value: Any = None,
        one_row: Any | None = None,
        first_row: Any | None = None,
        rows: list[Any] | None = None,
        mapping_rows: list[dict[str, Any]] | None = None,
        rowcount: int = 1,
    ) -> None:
        self.scalars_items = scalars_items if scalars_items is not None else []
        self.scalar_value = scalar_value
        self.one_row = (
            one_row
            if one_row is not None
            else SimpleNamespace(has_2fa=False, session_verified=False)
        )
        self.first_row = first_row
        self.rows = rows if rows is not None else []
        self.mapping_rows = mapping_rows if mapping_rows is not None else []
        self.rowcount = rowcount

    def scalars(self) -> "_ScalarResult":
        return _ScalarResult(self)

    def mappings(self) -> "_MappingResult":
        return _MappingResult(self)

    def scalar(self) -> Any:
        return self.scalar_value

    def scalar_one(self) -> Any:
        return self.scalar_value

    def scalar_one_or_none(self) -> Any:
        return self.scalar_value

    def one(self) -> Any:
        return self.one_row

    def one_or_none(self) -> Any:
        return self.one_row

    def first(self) -> Any:
        return self.first_row

    def all(self) -> list[Any]:
        return self.rows

    def unique(self) -> "RecordingResult":
        return self

    def keys(self) -> list[str]:
        return []

    def __iter__(self):
        return iter(self.rows)


class _ScalarResult:
    def __init__(self, result: RecordingResult) -> None:
        self._result = result

    def all(self) -> list[Any]:
        return self._result.scalars_items

    def first(self) -> Any:
        return self._result.scalars_items[0] if self._result.scalars_items else None

    def scalar(self) -> Any:
        return self._result.scalar_value


class _MappingResult:
    def __init__(self, result: RecordingResult) -> None:
        self._result = result

    def all(self) -> list[dict[str, Any]]:
        return self._result.mapping_rows


class _FakeSyncSession:
    new = set()
    dirty = set()
    deleted = set()

    def get_transaction(self) -> None:
        return None


class RecordingSession:
    """Counts DB round-trips made by the real code under measurement."""

    def __init__(
        self,
        *,
        result_provider: Callable[[str], RecordingResult | None] | None = None,
    ) -> None:
        self.results: list[RecordingResult] = []
        self.result_provider = result_provider
        self.executes = 0
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0
        self.gets = 0
        self.flushes = 0
        self.adds = 0
        self.deletes = 0
        self.statements: list[str] = []
        self.sync_session = _FakeSyncSession()

    def _next_result(self, statement: str) -> RecordingResult:
        if self.result_provider is not None:
            provided = self.result_provider(statement)
            if provided is not None:
                return provided
        if self.results:
            return self.results.pop(0)
        return RecordingResult()

    async def execute(
        self, statement: Any, *args: Any, **kwargs: Any
    ) -> RecordingResult:
        self.executes += 1
        self.statements.append(str(statement))
        return self._next_result(str(statement))

    async def scalars(self, statement: Any, *args: Any, **kwargs: Any) -> _ScalarResult:
        return (await self.execute(statement)).scalars()

    async def get(self, model: Any, ident: Any) -> Any:
        self.gets += 1
        return None

    async def add(self, obj: Any) -> None:
        self.adds += 1

    async def add_all(self, objs: list[Any]) -> None:
        self.adds += len(objs)

    async def delete(self, obj: Any) -> None:
        self.deletes += 1

    async def flush(self, objects: list[Any] | None = None) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def close(self) -> None:
        self.closes += 1

    async def expire(self, obj: Any, attribute_names: list[str] | None = None) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        return None

    def execution_options(self, **kwargs: Any) -> "RecordingSession":
        return self

    def get_transaction(self) -> None:
        return None

    def connection(self) -> SimpleNamespace:
        return SimpleNamespace(info={})

    async def __aenter__(self) -> "RecordingSession":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


class RecordingRedis:
    """Counts Redis operations. ``get``/``setex``/``delete`` hit ``self.store``."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.counts: dict[str, int] = {
            "get": 0,
            "setex": 0,
            "delete": 0,
            "exists": 0,
            "set": 0,
        }
        self.scan_count = 0

    async def get(self, key: str) -> Any:
        self.counts["get"] += 1
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: Any) -> None:
        self.counts["setex"] += 1
        self.store[key] = value

    async def set(self, key: str, value: Any, **kwargs: Any) -> None:
        self.counts["set"] += 1
        self.store[key] = value

    async def delete(self, *keys: str) -> int:
        self.counts["delete"] += len(keys)
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
        return removed

    async def exists(self, *keys: str) -> int:
        self.counts["exists"] += len(keys)
        return sum(1 for key in keys if key in self.store)

    async def scan_iter(self, match: str | None = None, count: int | None = None):
        self.scan_count += 1
        pattern = translate(match or "*")
        for key in list(self.store):
            if re.match(pattern, key):
                yield key

    async def aclose(self) -> None:
        return None

    async def flushdb(self) -> None:
        return None


# --------------------------------------------------------------------------
# Result capture
# --------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _truncate_results():
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (_RESULTS_DIR / "perf-deltas.jsonl").write_text("", encoding="utf-8")
    yield


@pytest.fixture(autouse=True)
def _flush_results(request):
    yield
    line = json.dumps(
        {
            "nodeid": request.node.nodeid,
            "head": _repo_head(),
            "branch": _repo_branch(),
            "results": dict(_RESULTS),
        }
    )
    with open(_RESULTS_DIR / "perf-deltas.jsonl", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    _RESULTS.clear()


@pytest.fixture(autouse=True)
def _reset_redis_circuit_state():
    """Make the harness deterministic regardless of preceding tests.

    Tests in this file (SWR coalescing, cache bust, route PDP) count Redis
    operations through ``safe_redis_get``/``safe_redis_setex``, which short-
    circuit to zero ops whenever the module-level circuit breaker is OPEN
    (``redis_available()`` returns False). The stress suite running in the
    same pytest process exercises real Redis error paths and can leave the
    breaker OPEN; without a reset here the recorded op counts would drop to
    0 and these tests would fail spuriously. Reset the breaker to CLOSED
    before every test so BEFORE/AFTER numbers are comparable.
    """
    redis_mod._circuit_state = redis_mod._CircuitState.CLOSED
    redis_mod._circuit_failed_at = 0.0
    redis_mod._circuit_consecutive_failures = 0


# --------------------------------------------------------------------------
# P1-1: read-only requests skip COMMIT
# --------------------------------------------------------------------------


async def test_p1_1_get_db_no_commit_on_read_only(monkeypatch):
    session = RecordingSession()
    monkeypatch.setattr(dbmod, "AsyncSessionLocal", lambda: session)
    gen = dbmod.get_db()
    yielded = await gen.__anext__()
    assert yielded is session
    try:
        await gen.asend(None)
    except StopAsyncIteration:
        pass
    _record("p1_1_get_db_commits_read_only", session.commits)
    _record("p1_1_get_db_rollbacks_read_only", session.rollbacks)
    _record("p1_1_get_db_closes_read_only", session.closes)
    assert session.commits in (0, 1)


# --------------------------------------------------------------------------
# P1-2: 2FA gate collapses 2 queries into 1
# --------------------------------------------------------------------------


async def test_p1_2_2fa_gate_db_executes():
    svc = AuthService()
    session = RecordingSession()
    uid = str(uuid.uuid4())
    if hasattr(svc, "get_2fa_gate_state"):
        _record("p1_2_2fa_gate_method_present", 1)
        await svc.get_2fa_gate_state(session, uid, "sess-1")
    else:
        _record("p1_2_2fa_gate_method_present", 0)
        await svc.has_active_2fa(session, uid)
        await svc.is_admin_session_2fa_verified(session, uid, "sess-1")
    _record("p1_2_2fa_gate_db_executes", session.executes)
    assert session.executes in (1, 2)


# --------------------------------------------------------------------------
# P2-1: catalog list_products DB round-trips
# --------------------------------------------------------------------------


async def test_p2_1a_list_products_empty_db_executes():
    svc = CatalogService()
    session = RecordingSession()
    resp = await svc.list_products(session, page=1, page_size=20, status="active")
    _record("p2_1a_list_products_empty_db_executes", session.executes)
    _record("p2_1a_list_products_empty_total", int(resp.total))
    assert session.executes in (1, 2)


async def test_p2_1a_image_variants_query_removed():
    repo = ProductRepository()
    exists = hasattr(repo, "get_image_variants_for_images")
    _record("p2_1a_image_variants_method_present", int(exists))
    if exists:
        session = RecordingSession()
        await repo.get_image_variants_for_images(session, [uuid.uuid4()])
        _record("p2_1a_image_variants_db_executes", session.executes)


async def test_p2_1c_list_paginated_db_executes():
    repo = ProductRepository()
    session = RecordingSession()
    items, total = await repo.list_paginated(session, page=1, page_size=20)
    _record("p2_1c_list_paginated_db_executes", session.executes)
    _record("p2_1c_list_paginated_total", int(total))
    assert len(items) == 0
    assert session.executes in (1, 2)


async def test_p2_1c_collections_list_admin_db_executes():
    repo = CollectionRepository()
    session = RecordingSession()
    session.results.append(RecordingResult(scalar_value=0))
    session.results.append(RecordingResult(rows=[]))
    items, total = await repo.list_admin(session, page=1, page_size=20)
    _record("p2_1c_collections_list_admin_db_executes", session.executes)
    _record("p2_1c_collections_list_admin_total", int(total))
    assert len(items) == 0
    assert session.executes in (1, 2)


# --------------------------------------------------------------------------
# P2-1: variant update round-trips
# --------------------------------------------------------------------------


async def test_p2_1b_update_variant_repo_db_executes():
    repo = ProductRepository()
    session = RecordingSession()
    updated = await repo.update_variant(
        session, uuid.uuid4(), {"price_adjustment": 5.0}
    )
    _record("p2_1b_update_variant_repo_db_executes", session.executes)
    _record("p2_1b_update_variant_repo_get_count", session.gets)
    assert updated is None
    assert session.executes in (1, 2)


async def test_p2_1b_update_variant_service_non_stock_db_executes():
    svc = CatalogService()
    session = RecordingSession()
    fake_variant = SimpleNamespace(
        id=uuid.uuid4(), product_id=uuid.uuid4(), stock_quantity=5
    )
    session.results.append(RecordingResult(scalar_value=fake_variant))
    payload = ProductVariantUpdateRequest(price_adjustment=5.0)
    await svc.update_variant(session, fake_variant.id, payload)
    _record("p2_1b_update_variant_service_db_executes", session.executes)
    assert session.executes in (2, 3)


# --------------------------------------------------------------------------
# P2-2: cache_swr semantics (mechanism identical in both trees)
# --------------------------------------------------------------------------


async def test_p2_2_cache_swr_concurrent_cold_coalescing():
    redis = RecordingRedis()
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"id": "p1"}

    results = await asyncio.gather(
        *(cache_swr(redis, "k1", 600, 600, fetch) for _ in range(5))
    )
    assert len(results) == 5
    assert all(r == {"id": "p1"} for r in results)
    _record("p2_2_swr_5concurrent_cold_db_fetches", calls)
    _record("p2_2_swr_5concurrent_cold_redis_gets", redis.counts["get"])
    _record("p2_2_swr_5concurrent_cold_redis_setex", redis.counts["setex"])
    assert calls == 1


async def test_p2_2_cache_swr_fresh_then_stale_background_refresh():
    redis = RecordingRedis()
    key = "k2"
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return {"v": calls}

    redis.store[key] = _wrap({"v": 0}, time.time())
    fresh = await cache_swr(redis, key, 600, 600, fetch)
    _record("p2_2_swr_fresh_served_from_cache", int(fresh == {"v": 0}))
    _record("p2_2_swr_fresh_db_fetches", calls)
    assert calls == 0

    redis.store[key] = _wrap({"v": 0}, time.time() - 900)
    stale = await cache_swr(redis, key, 600, 600, fetch)
    assert stale == {"v": 0}
    await asyncio.sleep(0.2)
    _record("p2_2_swr_stale_served_ok", 1)
    _record("p2_2_swr_stale_bg_db_fetches", calls)
    _record("p2_2_swr_stale_bg_total_redis_setex", redis.counts["setex"])
    assert calls == 1


# --------------------------------------------------------------------------
# P0-1: cache-bust moves off the request path
# --------------------------------------------------------------------------


async def test_p0_1_bust_is_fire_and_forget():
    if not hasattr(redis_mod, "schedule_product_list_bust"):
        _record("p0_1_schedule_fn_present", 0)
        _record("p0_1_bust_ops_at_return", -1)
        _record("p0_1_bust_scan_after_sleep", -1)
        return
    _record("p0_1_schedule_fn_present", 1)

    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    cache_warmer.rewarm_after_invalidation = _noop

    redis = RecordingRedis()
    now = time.time()
    for i in range(10):
        redis.store[f"products:list:v1:page{i}"] = _wrap({"dummy": i}, now)

    redis_mod.schedule_product_list_bust(redis)
    _record(
        "p0_1_bust_ops_at_return",
        redis.scan_count + redis.counts["get"] + redis.counts["setex"],
    )
    await asyncio.sleep(0.3)
    _record("p0_1_bust_scan_after_sleep", redis.scan_count)
    _record("p0_1_bust_rewrite_gets", redis.counts["get"])
    _record("p0_1_bust_rewrite_setex", redis.counts["setex"])
    assert redis.scan_count >= 1


async def test_p0_1_media_router_bust_callsite():
    import inspect

    src = inspect.getsource(media_router)
    _record(
        "p0_1_media_router_inline_await_bust",
        int("await bust_product_list_cache" in src),
    )
    _record("p0_1_media_router_uses_schedule", int("schedule_product_list_bust" in src))


# --------------------------------------------------------------------------
# P0-2: DISCARD ALL on connection return removed
# --------------------------------------------------------------------------


async def test_p0_2_discard_all_reset_listener():
    listener = getattr(dbmod, "_on_connection_reset", None)
    if listener is None:
        _record("p0_2_reset_listener_present", 0)
        _record("p0_2_discard_all_statements_per_return", 0)
        return
    _record("p0_2_reset_listener_present", 1)

    statements: list[str] = []

    class _FakeCursor:
        def execute(self, sql: str) -> None:
            statements.append(str(sql))

        def close(self) -> None:
            return None

    class _FakeConn:
        def cursor(self) -> _FakeCursor:
            return _FakeCursor()

        def commit(self) -> None:
            return None

    listener(_FakeConn(), None)
    _record("p0_2_discard_all_statements_per_return", len(statements))
    assert all(s.upper().startswith("DISCARD") for s in statements)


# --------------------------------------------------------------------------
# P2-2: route-level PDP cold miss (BEFORE 1x GET vs AFTER 2x GET)
# --------------------------------------------------------------------------


async def test_route_pdp_cold_miss_redis_ops(client, app, monkeypatch):
    session = RecordingSession()
    recording_redis = RecordingRedis()
    monkeypatch.setattr(catalog_router, "AsyncSessionLocal", lambda: session)

    async def _get_db():
        yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_redis] = lambda: recording_redis
    try:
        resp = await client.get("/api/v1/products/slug-that-does-not-exist")
    finally:
        app.dependency_overrides.clear()

    _record("route_pdp_cold_miss_http_status", resp.status_code)
    _record("route_pdp_cold_miss_redis_gets", recording_redis.counts["get"])
    _record("route_pdp_cold_miss_redis_setex", recording_redis.counts["setex"])
    _record("route_pdp_cold_miss_redis_deletes", recording_redis.counts["delete"])
    _record("route_pdp_cold_miss_db_executes", session.executes)
    assert resp.status_code in (200, 404)
    assert recording_redis.counts["get"] in (1, 2)
    assert session.executes >= 1


# --------------------------------------------------------------------------
# PDP success path — cold miss -> DB fetch -> cache populate -> hit -> ETag -> 304
# --------------------------------------------------------------------------


async def test_route_pdp_success_path_miss_hit_etag_304(client, app, monkeypatch):
    """Drive /api/v1/products/{slug} end-to-end through the real route and
    service code against recording stubs.

    Flow asserted:
      1. Cold request -> cache miss -> 1 DB fetch (get_by_slug) + 1 DB fetch
         (get_collections_for_product) -> 200 with product body.
      2. Redis now holds the populated cache entry (SETEX happened).
      3. Second request -> cache hit -> 200, ZERO additional DB executes.
      4. ETag header present on both 200s.
      5. Request with If-None-Match=<etag> -> 304, zero additional DB executes.
    """
    from datetime import datetime

    from app.modules.catalog.models import Product

    now = datetime(2026, 1, 1, 12, 0, 0)
    product = Product(
        id=uuid.uuid4(),
        sku="SKU-E2E-001",
        name="Silver Ring",
        slug="silver-ring-e2e",
        description="A test product",
        short_description=None,
        category_id=None,
        metal_type="silver",
        purity="925",
        base_price=4999.0,
        compare_at_price=5999.0,
        cost_price=2000.0,
        tax_rate=3.0,
        hsn_code="7113",
        track_inventory=True,
        allow_backorder=False,
        low_stock_threshold=5,
        stock_quantity=10,
        reserved_quantity=0,
        sold_quantity=0,
        max_order_quantity=5,
        status="active",
        is_featured=True,
        is_new_arrival=False,
        is_best_seller=False,
        is_customizable=False,
        requires_shipping=True,
        length_cm=None,
        width_cm=None,
        height_cm=None,
        meta_title="Silver Ring",
        meta_description=None,
        meta_keywords=None,
        created_at=now,
        updated_at=now,
        published_at=now,
        average_rating=4.5,
        review_count=3,
    )

    session = RecordingSession()
    # Query order on cold miss: (1) get_by_slug -> scalar_one_or_none(),
    # (2) get_collections_for_product -> scalars().all() (empty).
    session.results.append(RecordingResult(scalar_value=product))
    session.results.append(RecordingResult(scalars_items=[]))

    recording_redis = RecordingRedis()
    monkeypatch.setattr(catalog_router, "AsyncSessionLocal", lambda: session)

    async def _get_db():
        yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_redis] = lambda: recording_redis
    try:
        # 1. Cold request — cache miss.
        resp1 = await client.get("/api/v1/products/silver-ring-e2e")
        assert resp1.status_code == 200, resp1.text
        body1 = resp1.json()
        assert body1["data"]["slug"] == "silver-ring-e2e"
        assert body1["data"]["name"] == "Silver Ring"
        assert body1["data"]["base_price"] == 4999.0
        assert body1["data"]["inventory_status"] == "IN_STOCK"
        assert body1["data"]["can_purchase"] is True
        assert body1["code"] == "PRODUCT_FETCHED"
        # Cold miss must have fetched product + collections = 2 executes.
        assert session.executes == 2
        # Cache populated on the miss.
        assert recording_redis.counts["setex"] >= 1
        assert recording_redis.store
        assert "product:detail:v1:silver-ring-e2e" in recording_redis.store
        etag1 = resp1.headers.get("etag")
        assert etag1, "ETag header must be present on a 200 response"
        cache_control = resp1.headers.get("cache-control", "")
        assert "stale-while-revalidate=600" in cache_control

        # 2. Warm request — cache hit, no additional DB round-trips.
        resp2 = await client.get("/api/v1/products/silver-ring-e2e")
        assert resp2.status_code == 200
        assert resp2.json()["data"]["slug"] == "silver-ring-e2e"
        assert session.executes == 2, "cache hit must not touch the DB"
        etag2 = resp2.headers.get("etag")
        assert etag2 and etag2 == etag1, "ETag must be stable across cache hits"

        # 3. Conditional request — If-None-Match -> 304, still no DB work.
        resp304 = await client.get(
            "/api/v1/products/silver-ring-e2e",
            headers={"If-None-Match": etag2},
        )
        assert resp304.status_code == 304
        assert session.executes == 2, "304 must not touch the DB"
    finally:
        app.dependency_overrides.clear()

    _record("route_pdp_success_200_count", 2)
    _record("route_pdp_success_304_count", 1)
    _record("route_pdp_success_cold_db_executes", 2)
    _record("route_pdp_success_warm_db_executes", 2)
    _record("route_pdp_success_etag_present", 1)
