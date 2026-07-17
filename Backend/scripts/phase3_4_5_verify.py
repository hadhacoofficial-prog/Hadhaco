"""Phase 3-5: Invalidation proof, SQL profiling, Pool analysis.

Requires: Backend running, admin token available.
"""

import asyncio
import subprocess
import time

import httpx

BASE_URL = "http://localhost:8000"


def _docker_exec(cmd: list[str]) -> str:
    r = subprocess.run(
        ["docker", "exec", "hadha-redis"] + cmd, capture_output=True, text=True, timeout=5
    )
    return r.stdout.strip()


def _redis_keys(pattern: str = "*") -> list[str]:
    raw = _docker_exec(["redis-cli", "KEYS", pattern])
    return [l for l in raw.splitlines() if l]


def _redis_ttl(key: str) -> int:
    raw = _docker_exec(["redis-cli", "TTL", key])
    try:
        return int(raw)
    except ValueError:
        return -1


async def _timed_get(client: httpx.AsyncClient, url: str) -> tuple[httpx.Response, float]:
    t0 = time.perf_counter()
    r = await client.get(url)
    return r, (time.perf_counter() - t0) * 1000


async def load_token() -> str:
    with open(r"C:\Users\Admin\AppData\Local\Temp\k6-token.txt", encoding="utf-8-sig") as f:
        return f.read().strip()


# -- Phase 3: Invalidation Proof --


async def phase3_invalidation_proof(client: httpx.AsyncClient, token: str):
    print("=" * 70)
    print("PHASE 3: Cache Invalidation Proof")
    print("=" * 70)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results = []

    # Test 1: Product list cache bust via admin product touch
    print("\n--- Test 1: Product List invalidation ---")
    r, t1 = await _timed_get(client, f"{BASE_URL}/api/v1/products?page=1&page_size=5")
    print(f"  GET /products (cold): {t1:.1f}ms, status={r.status_code}")

    r, t2 = await _timed_get(client, f"{BASE_URL}/api/v1/products?page=1&page_size=5")
    print(f"  GET /products (warm): {t2:.1f}ms, status={r.status_code}")

    # Admin update to bust cache
    prod_resp = await client.get(f"{BASE_URL}/api/v1/products?page=1&page_size=1")
    if prod_resp.status_code == 200:
        items = prod_resp.json().get("data", {}).get("items", [])
        if items:
            pid = items[0].get("id")
            r = await client.put(
                f"{BASE_URL}/api/v1/admin/products/{pid}",
                headers=headers,
                json={"name": "k6-cache-test-touch"},
            )
            print(f"  PUT /admin/products/{pid}: status={r.status_code} (bust trigger)")

            r, t3 = await _timed_get(client, f"{BASE_URL}/api/v1/products?page=1&page_size=5")
            busted = t3 > t2 * 1.5
            results.append(("Product List", busted, t2, t3))
            print(f"  GET /products (post-bust): {t3:.1f}ms, busted={busted}")

    # Test 2: CMS Home cache check
    print("\n--- Test 2: CMS Home cache ---")
    _, t_warm = await _timed_get(client, f"{BASE_URL}/api/v1/cms/home")
    print(f"  GET /cms/home (warm): {t_warm:.1f}ms")

    # Test 3: Search cache
    print("\n--- Test 3: Search cache ---")
    r, t_s = await _timed_get(client, f"{BASE_URL}/api/v1/search?q=ring&page=1&page_size=10")
    print(f"  GET /search?q=ring: {t_s:.1f}ms")

    # Test 4: Navbar / Navigation HTTP headers
    print("\n--- Test 4: HTTP Cache-Control headers ---")
    r, _ = await _timed_get(client, f"{BASE_URL}/api/v1/categories/navbar")
    cc = r.headers.get("cache-control", "MISSING")
    print(f"  /categories/navbar Cache-Control: {cc}")
    r, _ = await _timed_get(client, f"{BASE_URL}/api/v1/categories/navigation")
    cc = r.headers.get("cache-control", "MISSING")
    print(f"  /categories/navigation Cache-Control: {cc}")
    r, _ = await _timed_get(client, f"{BASE_URL}/api/v1/products?page=1&page_size=5")
    cc = r.headers.get("cache-control", "MISSING")
    print(f"  /products Cache-Control: {cc}")
    r, _ = await _timed_get(client, f"{BASE_URL}/api/v1/cms/home")
    cc = r.headers.get("cache-control", "MISSING")
    print(f"  /cms/home Cache-Control: {cc}")

    # Summary
    print("\n--- Invalidation Summary ---")
    for name, busted, t_before, t_after in results:
        icon = "PASS" if busted else "WARN"
        print(f"  [{icon}] {name}: {t_before:.1f}ms -> {t_after:.1f}ms")
    if not results:
        print("  (No cache bust tests completed)")

    # Redis key inventory
    keys = _redis_keys("*")
    print(f"\n--- Redis Key Inventory ({len(keys)} keys) ---")
    for k in sorted(keys)[:25]:
        ttl = _redis_ttl(k)
        print(f"  TTL={ttl:>6}s  {k}")
    if len(keys) > 25:
        print(f"  ... and {len(keys) - 25} more")


# -- Phase 4: SQL Profiling --


async def phase4_sql_profiling(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("PHASE 4: SQL + Redis Profiling")
    print("=" * 70)

    endpoints_to_profile = [
        "/api/v1/products?page=1&page_size=20",
        "/api/v1/collections",
        "/api/v1/categories/navbar",
        "/api/v1/categories/navigation",
        "/api/v1/search?q=ring&page=1&page_size=10",
        "/api/v1/cms/home",
        "/api/v1/cms/homepage",
        "/api/v1/search/trending",
    ]

    # N+1 detection: queries per endpoint
    print("\n--- N+1 Detection (queries per endpoint, warm) ---")
    for ep in endpoints_to_profile:
        r_before = await client.get(f"{BASE_URL}/health/metrics")
        q_before = r_before.json()["sql"]["total_queries"]
        _, elapsed = await _timed_get(client, f"{BASE_URL}{ep}")
        r_after = await client.get(f"{BASE_URL}/health/metrics")
        after = r_after.json()
        q_after = after["sql"]["total_queries"]
        q_count = q_after - q_before
        icon = "WARN" if q_count > 5 else "OK"
        print(f"  [{icon}] {ep}: {q_count} queries ({elapsed:.1f}ms)")

    # Final profiler snapshot
    r = await client.get(f"{BASE_URL}/health/metrics")
    final = r.json()

    print(f"\n--- Pool Status ---")
    print(f"  Capacity: {final['pool']['capacity']}")
    print(f"  Peak checked out: {final['pool']['peak_checked_out']}")
    print(f"  Peak utilization: {final['pool']['peak_utilization_pct']}%")
    print(f"  Total checkout waits: {final['pool']['total_checkout_waits']}")
    print(f"  Max wait time: {final['pool']['max_wait_ms']:.1f}ms")
    print(f"  Avg wait time: {final['pool']['avg_wait_ms']:.1f}ms")

    print(f"\n--- Redis Profiling ---")
    print(f"  Total calls: {final['redis']['total_calls']}")
    print(f"  Total time: {final['redis']['total_ms']:.1f}ms")
    print(f"  Max single call: {final['redis']['max_ms']:.1f}ms")
    redis_avg = final["redis"]["total_ms"] / max(final["redis"]["total_calls"], 1)
    print(f"  Average call: {redis_avg:.1f}ms")
    print(f"  Errors: {final['redis']['errors']}")


# -- Phase 5: Pool Under Load --


async def phase5_pool_load(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("PHASE 5: Pool Under Concurrent Load")
    print("=" * 70)

    r = await client.get(f"{BASE_URL}/health/metrics")
    before = r.json()

    print("\n--- 10 concurrent requests ---")
    endpoints = [
        "/api/v1/products?page=1&page_size=5",
        "/api/v1/collections",
        "/api/v1/categories/navbar",
        "/api/v1/cms/home",
        "/api/v1/search?q=ring",
        "/api/v1/products?page=2&page_size=5",
        "/api/v1/categories/navigation",
        "/api/v1/search/trending",
        "/api/v1/collections/women-collection",
        "/api/v1/cms/homepage",
    ]

    start = time.perf_counter()
    tasks = [client.get(f"{BASE_URL}{ep}") for ep in endpoints]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    total_time = (time.perf_counter() - start) * 1000

    print(f"\n  Wall-clock time: {total_time:.1f}ms")
    success = 0
    for i, (ep, resp) in enumerate(zip(endpoints, responses)):
        if isinstance(resp, Exception):
            print(f"  [{i+1}] {ep}: ERROR - {resp}")
        else:
            print(f"  [{i+1}] {ep}: {resp.status_code}")
            success += 1
    print(f"  Success: {success}/{len(endpoints)}")

    r = await client.get(f"{BASE_URL}/health/metrics")
    after = r.json()

    print(f"\n--- Post-Load Pool Stats ---")
    print(f"  Peak checked out: {after['pool']['peak_checked_out']}/{after['pool']['capacity']}")
    print(f"  Peak utilization: {after['pool']['peak_utilization_pct']}%")
    print(f"  Total checkout waits: {after['pool']['total_checkout_waits']}")
    print(f"  Max wait time: {after['pool']['max_wait_ms']:.1f}ms")
    print(f"  Avg wait time: {after['pool']['avg_wait_ms']:.1f}ms")

    delta_queries = after["sql"]["total_queries"] - before["sql"]["total_queries"]
    delta_ms = after["sql"]["total_ms"] - before["sql"]["total_ms"]
    print(f"\n--- SQL During Load ---")
    print(f"  Queries: {delta_queries}")
    print(f"  Total time: {delta_ms:.1f}ms")

    print(f"\n--- POOL VERDICT ---")
    pct = after["pool"]["peak_utilization_pct"]
    if pct <= 75:
        print(f"  PASS: Peak {pct}% <= 75% -- no pressure")
    elif pct <= 100:
        print(f"  WARN: Peak {pct}% -- approaching capacity")
    else:
        print(f"  FAIL: Peak {pct}% -- EXCEEDED capacity")

    max_wait = after["pool"]["max_wait_ms"]
    if max_wait < 100:
        print(f"  PASS: Max checkout wait {max_wait:.1f}ms < 100ms")
    elif max_wait < 1000:
        print(f"  WARN: Max checkout wait {max_wait:.1f}ms -- detectable latency")
    else:
        print(f"  FAIL: Max checkout wait {max_wait:.1f}ms -- severe bottleneck")


# -- Main --


async def main():
    token = await load_token()
    async with httpx.AsyncClient(timeout=15) as client:
        await phase3_invalidation_proof(client, token)
        await phase4_sql_profiling(client)
        await phase5_pool_load(client)


if __name__ == "__main__":
    asyncio.run(main())
