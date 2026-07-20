import asyncio
import time

import httpx


async def main():
    async with httpx.AsyncClient(timeout=15) as client:
        endpoints = [
            "/api/v1/products?page=1&page_size=5",
            "/api/v1/collections",
            "/api/v1/categories/navbar",
            "/api/v1/cms/home",
            "/api/v1/search?q=ring",
            "/api/v1/categories/navigation",
            "/api/v1/search/trending",
            "/api/v1/cms/homepage",
        ]
        start = time.perf_counter()
        tasks = [client.get(f"http://localhost:8000{ep}") for ep in endpoints]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        wall = (time.perf_counter() - start) * 1000

        ok = sum(
            1
            for r in responses
            if not isinstance(r, Exception) and r.status_code == 200
        )
        print(f"8 concurrent: {wall:.0f}ms wall-clock, {ok}/8 success")

        r = await client.get("http://localhost:8000/health/metrics")
        m = r.json()
        p = m["pool"]
        print(
            f"Pool peak: {p['peak_checked_out']}/{p['capacity']} "
            f"({p['peak_utilization_pct']}%)"
        )
        print(f"Pool max wait: {p['max_wait_ms']:.1f}ms")
        print(f"Pool avg wait: {p['avg_wait_ms']:.1f}ms")


if __name__ == "__main__":
    asyncio.run(main())
