"""Phase 2 live measurement — compare product list API latency."""
import time
import urllib.request
import json

BASE = "http://localhost:8000/api/v1"

# Flush Redis cache first
import subprocess
subprocess.run(
    ["docker", "exec", "hadha-redis", "redis-cli", "FLUSHDB"],
    capture_output=True,
)
print("Redis cache flushed.\n")


def get(path: str, label: str) -> float:
    url = f"{BASE}{path}"
    times = []
    for i in range(5):
        start = time.perf_counter()
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req)
        _ = resp.read()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)
    print(f"  {label:50s} avg={avg:7.1f}ms  min={mn:7.1f}ms  max={mx:7.1f}ms")
    return avg


print("=== Product List (cold miss — hits DB) ===")
t1 = get("/products?page=1&page_size=20", "GET /products?page=1&page_size=20")

print("\n=== Product List (warm — hits Redis) ===")
t2 = get("/products?page=1&page_size=20", "GET /products?page=1&page_size=20")

print("\n=== Product List with filters (cold miss) ===")
# Flush again for cold measurement
subprocess.run(
    ["docker", "exec", "hadha-redis", "redis-cli", "FLUSHDB"],
    capture_output=True,
)
time.sleep(0.5)
t3 = get("/products?page=1&page_size=10&gender=unisex", "GET /products?gender=unisex")
t4 = get("/products?page=1&page_size=10&gender=unisex", "GET /products?gender=unisex (warm)")

print("\n=== Category-filtered products (cold) ===")
subprocess.run(
    ["docker", "exec", "hadha-redis", "redis-cli", "FLUSHDB"],
    capture_output=True,
)
time.sleep(0.5)
# First get a real category_id
req = urllib.request.Request(f"{BASE}/categories/navigation")
resp = urllib.request.urlopen(req)
cats = json.loads(resp.read())
data = json.loads(cats.get("data", "{}") if isinstance(cats.get("data"), str) else json.dumps(cats.get("data", {})))
nav = data if isinstance(data, list) else data.get("categories", [])
if nav and len(nav) > 0:
    cat_id = nav[0].get("id", "")
    if cat_id:
        t5 = get(f"/products?page=1&page_size=10&category_id={cat_id}", "GET /products?category_id=...")
    else:
        print("  No category_id found, skipping")
else:
    print("  No categories found, skipping")


# Summary
print(f"\n{'='*70}")
print(f"  SUMMARY")
print(f"{'='*70}")
print(f"  Product list cold DB query (after optimization): {t1:.1f}ms avg")
print(f"  Product list warm Redis hit:                     {t2:.1f}ms avg")
print(f"  Cold-to-warm speedup:                            {t1/t2:.1f}x")
