# Production hit-profile report — 2026-10-10

- **Run**: 2026-10-09T21:07:46.515639+00:00 → 2026-10-09T21:13:22.373067+00:00 (UTC)
- **Method**: single client, one keep-alive connection per host, anonymous read-only GETs, 10 sequential hits per endpoint, 1.2s apart (~50 req/min, under the 60 r/m nginx zone). UA `HadhaLoadTest/1.0 (owner-initiated)`.
- **Metric**: total response time in ms (request sent → body fully read), measured from the test machine through Cloudflare (SIN edge). TCP/TLS was warmed first with a 404, so hit 1 is not handshake time.
- **Network floor**: ~115–125 ms. The fastest endpoints sit at this floor, so anything near 120 ms is effectively ~0 ms of server work.
- **Caveat**: "1st hit" is the first request of this run, not a guaranteed-cold cache — other traffic may have primed some keys. The `cold-key` row uses a never-before-used `page_size` to force a true miss.

## API (`api.hadha.co`)

| Endpoint | 1st | 2nd | 3rd | 4th–10th median | 4th–10th max | 1st÷median | CF status (1st→last) | Bytes (wire) | Status |
|---|--:|--:|--:|--:|--:|--:|---|--:|---|
| `/health` | 125 | 130 | 117 | 120 | 141 | 1.0× | DYNAMIC→DYNAMIC | 33 | 200 |
| `/health/ready` | 109 | 113 | 114 | 111 | 126 | 1.0× | DYNAMIC→DYNAMIC | 106 | 404 |
| `/categories` | 136 | 118 | 118 | 122 | 137 | 1.1× | DYNAMIC→DYNAMIC | 2057 | 200 |
| `/categories/navbar` | 131 | 121 | 127 | 121 | 125 | 1.1× | DYNAMIC→DYNAMIC | 1874 | 200 |
| `/categories/navigation` | 287 | 119 | 127 | 124 | 129 | 2.3× | DYNAMIC→DYNAMIC | 1991 | 200 |
| `/collections` | 131 | 126 | 118 | 125 | 173 | 1.0× | DYNAMIC→DYNAMIC | 2410 | 200 |
| `/products (page_size=20)` | 1481 | 192 | 218 | 198 | 222 | 7.5× | DYNAMIC→DYNAMIC | 19154 | 200 |
| `/products (cold-key page_size=36)` | 2369 | 207 | 205 | 203 | 219 | 11.7× | DYNAMIC→DYNAMIC | 33423 | 200 |
| `/products/facets` | 1739 | 142 | 129 | 122 | 137 | 14.3× | DYNAMIC→DYNAMIC | 1350 | 200 |
| `/search/trending` | 344 | 121 | 118 | 134 | 322 | 2.6× | DYNAMIC→DYNAMIC | 119 | 200 |
| `/search?q=ring` | 1410 | 119 | 122 | 122 | 124 | 11.5× | DYNAMIC→DYNAMIC | 1373 | 200 |
| `/search/autocomplete?q=ri` | 316 | 126 | 119 | 124 | 129 | 2.6× | DYNAMIC→DYNAMIC | 130 | 200 |
| `/cms/home` | 121 | 121 | 120 | 121 | 152 | 1.0× | DYNAMIC→DYNAMIC | 256 | 200 |
| `/cms/homepage` | 122 | 122 | 124 | 124 | 130 | 1.0× | DYNAMIC→DYNAMIC | 3534 | 200 |
| `/company` | 133 | 142 | 128 | 126 | 203 | 1.1× | DYNAMIC→DYNAMIC | 502 | 200 |
| `/sitemap.xml` | 1607 | 142 | 121 | 123 | 127 | 13.0× | DYNAMIC→DYNAMIC | 4367 | 200 |
| `/products/{slug}` | 1055 | 124 | 123 | 122 | 126 | 8.7× | DYNAMIC→DYNAMIC | 1835 | 200 |
| `/collections/{slug}` | 585 | 120 | 122 | 123 | 139 | 4.8× | DYNAMIC→DYNAMIC | 502 | 200 |
| `/reviews/products/{id}` | 1302 | 122 | 123 | 133 | 169 | 9.8× | DYNAMIC→DYNAMIC | 99 | 200 |
| `/reviews/products/{id}/summary` | 1150 | 127 | 124 | 126 | 128 | 9.1× | DYNAMIC→DYNAMIC | 213 | 200 |

## Storefront SSR (`hadha.co`)

| Endpoint | 1st | 2nd | 3rd | 4th–10th median | 4th–10th max | 1st÷median | CF status (1st→last) | Bytes (wire) | Status |
|---|--:|--:|--:|--:|--:|--:|---|--:|---|
| `/ (SSR home)` | 291 | 153 | 156 | 154 | 160 | 1.9× | DYNAMIC→DYNAMIC | 1725 | 200 |
| `/products (SSR)` | 1271 | 173 | 166 | 184 | 199 | 6.9× | DYNAMIC→DYNAMIC | 1784 | 200 |
| `/collections (SSR)` | 151 | 142 | 140 | 144 | 152 | 1.0× | DYNAMIC→DYNAMIC | 1555 | 200 |
| `/products/{slug} (SSR)` | 1143 | 178 | 172 | 188 | 204 | 6.1× | DYNAMIC→DYNAMIC | 4391 | 200 |

## Findings

1. **First-hit penalty is concentrated in a few endpoints**: `/products (cold-key page_size=36)` 2369 ms vs 203 ms warm; `/products/facets` 1739 ms vs 122 ms warm; `/sitemap.xml` 1607 ms vs 123 ms warm; `/products (page_size=20)` 1481 ms vs 198 ms warm; `/search?q=ring` 1410 ms vs 122 ms warm; `/reviews/products/{id}` 1302 ms vs 133 ms warm; `/products (SSR)` 1271 ms vs 184 ms warm; `/reviews/products/{id}/summary` 1150 ms vs 126 ms warm; `/products/{slug} (SSR)` 1143 ms vs 188 ms warm; `/products/{slug}` 1055 ms vs 122 ms warm; `/collections/{slug}` 585 ms vs 123 ms warm.
2. **Warm hits are fast**: from the 2nd hit on, nearly every endpoint is at the ~120 ms network floor; the heaviest warm endpoint is `/products` at ~200 ms. The backend cache layer works; the cost is the miss path.
3. **`/products` miss path is the worst** (1.5 s for the standard key; 2.4 s for the new key, which also returns a larger 36-item payload, so the two aren't strictly like-for-like). Every new filter/page-size combination is a full miss, so real users with varied filters pay this repeatedly. Consistent with the 02:09 ramp test where `/products` p95 reached 15 s at 100 VUs.
4. **Cloudflare is not caching API responses**: responses are `cf-cache-status: DYNAMIC` even where the backend sends `Cache-Control: public, max-age=3600` (e.g. `/categories`). All caching happens at Redis/app level, so every request still reaches origin. An edge cache rule for public GETs (or finding why CF bypasses) would cut origin load.
5. **`/sitemap.xml` (1.6 s) and reviews (1.1–1.3 s) first hits** are cacheable, rarely-changing data — candidates for pre-warming.
6. **`/health/ready` returns 404 on the public host** (only `/health` is exposed). Fine if intentional, but readiness cannot be probed externally.
7. **No 429s, 5xx or timeouts** across 240 requests at ~50 req/min. The only non-200 is the `/health/ready` 404 above.

## Not measured / limits
- Single client, single region; not concurrency (see `k6/prod-readonly` for the 100-VU ramp).
- Authenticated, cart, checkout and write endpoints were excluded (production, read-only).
- `/cms/pages/{slug}`, `/seo/page`, `/shipping/rates`, `/settings/flags/{key}` need known params and were skipped.
- Raw per-hit data (TTFB, bytes, CF headers): `prod-hit-profile-2026-10-10.json`.
