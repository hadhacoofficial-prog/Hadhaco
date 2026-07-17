"""Precise Phase 2 query count measurement — single request, clean profiling."""
import time
import urllib.request
import json

BASE = "http://localhost:8000/api/v1"

def api_get(path: str) -> dict:
    url = f"{BASE}{path}" if path.startswith("/") else f"{BASE}/{path}"
    if path.startswith("http"):
        url = path
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

def flush_redis():
    import subprocess
    subprocess.run(["docker", "exec", "hadha-redis", "redis-cli", "FLUSHDB"], capture_output=True)

# Step 1: flush Redis to force cold DB path
flush_redis()
time.sleep(0.5)

# Step 2: Hit product list (cold miss → DB queries)
start = time.perf_counter()
r1 = api_get("/products?page=1&page_size=20")
elapsed_ms = (time.perf_counter() - start) * 1000
items = r1["data"]["items"]
print(f"Cold product list: {elapsed_ms:.1f}ms, {len(items)} items, total={r1['data']['total']}")

# Step 3: Check profiling metrics
metrics = api_get("http://localhost:8000/health/metrics")
sql = metrics["sql"]
pool = metrics["pool"]
redis_m = metrics["redis"]
print(f"\nProfiling after single cold product list request:")
print(f"  SQL queries: {sql['total_queries']}")
print(f"  SQL total:   {sql['total_ms']:.1f}ms")
print(f"  SQL avg:     {sql['avg_ms']:.1f}ms")
print(f"  Redis calls: {redis_m['total_calls']}")
print(f"  Redis errors:{redis_m['errors']}")
print(f"  Pool peak:   {pool['peak_utilization_pct']:.0f}%")

# Step 4: Warm hit
start = time.perf_counter()
r2 = api_get("/products?page=1&page_size=20")
elapsed_warm = (time.perf_counter() - start) * 1000
print(f"\nWarm product list: {elapsed_warm:.1f}ms (Redis hit)")

# Step 5: Check if profiling was reset or if it accumulates
# Try a fresh endpoint to see per-request count
print(f"\n--- Expected queries per product list (cold, with include_collections=True) ---")
print(f"  1. Product data + count (window function)")
print(f"  2. Image IDs via CTE (primary+secondary per product)")
print(f"  3. Full Image objects (batch by IDs)")
print(f"  4. Image variants (batch for fetched images)")
print(f"  5. Product variants (selectinload for available_stock)")
print(f"  6. Collections batch")
print(f"  = 6 queries total (BEFORE was 6+ = count + images + image_variants + variants + collections)")
print(f"  BUT: count is merged into query 1, images are limited to 2/product")
