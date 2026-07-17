"""Phase 2: Redis cache verification — cold vs warm latency, hit ratios."""

import asyncio
import subprocess
import httpx
import time
import json

BASE_URL = "http://localhost:8000"

# All cacheable GET endpoints (no auth required)
ENDPOINTS = [
    ("CMS Home", "/api/v1/cms/home"),
    ("CMS Homepage", "/api/v1/cms/homepage"),
    ("Product List", "/api/v1/products?page=1&page_size=10"),
    ("Product List (pg2)", "/api/v1/products?page=2&page_size=10"),
    ("Product Detail", "/api/v1/products/elegant-925-sterling-silver-cz-link-bracelet-for-women-premium-sparkling-everyday-luxury"),
    ("Categories", "/api/v1/categories"),
    ("Navbar Categories", "/api/v1/categories/navbar"),
    ("Navigation Categories", "/api/v1/categories/navigation"),
    ("Collection List", "/api/v1/collections"),
    ("Collection Detail", "/api/v1/collections/women-collection"),
    ("Search", "/api/v1/search?q=ring&page=1&page_size=10"),
    ("Search Autocomplete", "/api/v1/search/autocomplete?q=ri&limit=10"),
    ("Search Trending", "/api/v1/search/trending"),
    ("Sitemap XML", "/api/v1/sitemap.xml"),
]


async def hit_endpoint(client: httpx.AsyncClient, name: str, path: str) -> dict:
    """Hit endpoint once, return timing info."""
    start = time.perf_counter()
    resp = await client.get(f"{BASE_URL}{path}")
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "name": name,
        "path": path,
        "status": resp.status_code,
        "latency_ms": round(elapsed_ms, 1),
    }


async def get_redis_stats(client: httpx.AsyncClient) -> dict:
    """Get Redis INFO stats via docker exec (not httpx)."""
    result = subprocess.run(
        ["docker", "exec", "hadha-redis", "redis-cli", "INFO", "stats"],
        capture_output=True, text=True, timeout=5
    )
    stats = {}
    for line in result.stdout.splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            stats[k.strip()] = v.strip()
    return stats


async def get_redis_memory(client: httpx.AsyncClient) -> dict:
    result = subprocess.run(
        ["docker", "exec", "hadha-redis", "redis-cli", "INFO", "memory"],
        capture_output=True, text=True, timeout=5
    )
    stats = {}
    for line in result.stdout.splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            stats[k.strip()] = v.strip()
    return stats


async def get_profiler_stats(client: httpx.AsyncClient) -> dict:
    resp = await client.get(f"{BASE_URL}/health/metrics")
    return resp.json()


async def count_redis_keys() -> int:
    result = subprocess.run(
        ["docker", "exec", "hadha-redis", "redis-cli", "DBSIZE"],
        capture_output=True, text=True, timeout=5
    )
    # DBSIZE returns "N\r\n"
    output = result.stdout.strip()
    for part in output.split():
        if part.isdigit():
            return int(part)
    return 0


async def run():
    print("=" * 70)
    print("PHASE 2: Redis Cache Verification")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=15) as client:
        # --- Profiler baseline ---
        profiler_before = await get_profiler_stats(client)

        # --- Cold pass (populate cache) ---
        print("\n--- COLD PASS (first hit -> DB -> cache) ---")
        cold_results = []
        for name, path in ENDPOINTS:
            r = await hit_endpoint(client, name, path)
            cold_results.append(r)
            status_icon = "OK" if r["status"] == 200 else f"ERR({r['status']})"
            print(f"  {status_icon} {r['name']:30s} {r['latency_ms']:7.1f}ms")

        # --- Collect post-cold profiler ---
        profiler_after_cold = await get_profiler_stats(client)

        # --- Warm pass (all from cache) ---
        print("\n--- WARM PASS (all served from cache) ---")
        warm_results = []
        for name, path in ENDPOINTS:
            r = await hit_endpoint(client, name, path)
            warm_results.append(r)
            status_icon = "OK" if r["status"] == 200 else f"ERR({r['status']})"
            print(f"  {status_icon} {r['name']:30s} {r['latency_ms']:7.1f}ms")

        # --- Post-warm profiler ---
        profiler_after_warm = await get_profiler_stats(client)

        # --- Redis stats ---
        redis_stats = await get_redis_stats(client)
        redis_mem = await get_redis_memory(client)
        key_count = await count_redis_keys()

        # --- Summary ---
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)

        # Latency comparison
        print("\n--- Latency: Cold vs Warm ---")
        print(f"  {'Endpoint':30s} {'Cold (ms)':>10s} {'Warm (ms)':>10s} {'Speedup':>8s}")
        print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*8}")
        cold_total = 0
        warm_total = 0
        for cold, warm in zip(cold_results, warm_results):
            if cold["status"] == 200:
                speedup = f"{cold['latency_ms'] / max(warm['latency_ms'], 0.1):.1f}x" if warm["latency_ms"] > 0 else "∞"
                print(f"  {cold['name']:30s} {cold['latency_ms']:10.1f} {warm['latency_ms']:10.1f} {speedup:>8s}")
                cold_total += cold["latency_ms"]
                warm_total += warm["latency_ms"]
        total_speedup = f"{cold_total / max(warm_total, 0.1):.1f}x"
        print(f"  {'TOTAL':30s} {cold_total:10.1f} {warm_total:10.1f} {total_speedup:>8s}")

        # Redis hit ratio
        hits = int(redis_stats.get("keyspace_hits", 0))
        misses = int(redis_stats.get("keyspace_misses", 0))
        total = hits + misses
        hit_ratio = (hits / total * 100) if total > 0 else 0
        print(f"\n--- Redis Hit Ratio ---")
        print(f"  Hits: {hits}  |  Misses: {misses}  |  Total: {total}")
        print(f"  Hit ratio: {hit_ratio:.1f}%")

        # Redis memory
        print(f"\n--- Redis Memory ---")
        print(f"  Used: {redis_mem.get('used_memory_human', '?')} / {redis_mem.get('maxmemory_human', '?')}")
        print(f"  Keys in DB: {key_count}")

        # Profiler delta
        print(f"\n--- Profiler (from /health/metrics) ---")
        p_before = profiler_before
        p_after = profiler_after_warm
        delta_queries = p_after["sql"]["total_queries"] - p_before["sql"]["total_queries"]
        delta_sql_ms = p_after["sql"]["total_ms"] - p_before["sql"]["total_ms"]
        delta_redis = p_after["redis"]["total_calls"] - p_before["redis"]["total_calls"]
        print(f"  SQL queries executed: {delta_queries}")
        print(f"  SQL total time: {delta_sql_ms:.1f}ms")
        print(f"  Redis calls (profiler): {delta_redis}")
        print(f"  Pool peak: {p_after['pool']['peak_checked_out']}/{p_after['pool']['capacity']} ({p_after['pool']['peak_utilization_pct']}%)")

        # Verdict
        print(f"\n--- VERDICT ---")
        if hit_ratio >= 95:
            print(f"  PASS: Redis hit ratio {hit_ratio:.1f}% >= 95%")
        elif hit_ratio >= 80:
            print(f"  WARN: Redis hit ratio {hit_ratio:.1f}% — below 95% target")
        else:
            print(f"  FAIL: Redis hit ratio {hit_ratio:.1f}% — significantly below target")

        if warm_total > 0 and cold_total / max(warm_total, 0.1) >= 2.0:
            print(f"  PASS: Warm latency {total_speedup} faster than cold")
        else:
            print(f"  WARN: Speedup {total_speedup} — cache may not be effective")


if __name__ == "__main__":
    asyncio.run(run())
