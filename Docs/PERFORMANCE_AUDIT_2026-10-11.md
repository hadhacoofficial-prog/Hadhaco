# Hadha.co Performance Audit — 2026-10-11

Scope: backend (FastAPI/SQLAlchemy/Redis), production Supabase DB (read-only
stats), storefront (TanStack Start SSR + Vite build output). Method: static
review + `pg_stat_statements`/`pg_stat_user_tables`/advisors on the live DB +
build-artifact inspection + the existing 2026-10-10 prod hit profile
(`k6/reports/prod-hit-profile-2026-10-10.md`).

**Not measured (be honest about limits):** no new load test was run; no Lighthouse /
real-user Web Vitals were captured (no RUM in the app); the local `:8000` was
another project so no live local timings. Frontend numbers are from the
build output in `Frontend_whole/storefront/.output` (built 2026-10-10), not a
fresh build. Items marked *hypothesis* need a measurement before fixing.

## Scorecard vs. budgets

| Metric | Measured | Budget | Verdict |
|---|---|---|---|
| API warm latency (ex. network) | ~0–10 ms; `/products` ~75 ms | P95 < 300 ms | OK |
| API cold-key `/products` | 1.5–2.4 s | < 1 s | **Fail** |
| DB query time (product list) | 17–38 ms mean | — | OK (not the cause) |
| Main JS entry (`index-*.js`) | 1,006 KB raw / **302 KB gz** | < 200 KB gz | **Fail** |
| Logo/icon payload per page | ~2.0 MB PNG (see F1) | — | **Fail** |
| SSR HTML for home / list | ~1.7 KB (empty shell) | content in HTML | **Fail** (F3) |

---

## P0

### F1. Logos/favicon are 5760×3240 / 3241×3241 PNGs (≈0.65 MB each) shipped on every page
- `src/assets/hadha-logo.png` 668 KB (5760×3240), `hadha-logo-w.png` 656 KB
  (5761×3240), `hadha-mark.png` 683 KB (3241×3241). Build output keeps them
  uncompressed (PNG, gzip gains ~0%).
- Header renders the logo at `h-16 md:h-28` (≈64–112 px tall)
  (`components/site/Header.tsx:133-137`) — a >30× oversample.
- `routes/__root.tsx:18,126` uses the 3241 px mark as `rel=icon` **and**
  `apple-touch-icon` → 683 KB downloaded for a 32 px favicon, in the `<head>`
  on every route.
- Footer logo (656 KB) is in the DOM on every page.
- Also: `banner.jpg` 442 KB (used by FeaturedCollection/PromoBanner/About).
- **Impact:** ~2 MB of critical-path-adjacent bytes per cold page view; on mid-tier
  mobile 4G (≈1.6 Mbps) that is ≈10 s of transfer competing with the LCP image.
- **Fix:** export logos as SVG (preferred) or WebP/AVIF at 2× display size
  (≈440×224 → <20 KB); favicon 32/180/512 px PNG (<10 KB each); banner → AVIF/WebP
  at ≤1600 px with `srcset`. Expected: −1.9 MB per page, no code risk.

### F2. `/products` cache-miss path: 1.5–2.4 s with a 38 ms query (cold-key + SSR first hit)
- Prod profile: first hit 1481 ms / new-key 2369 ms vs 198 ms warm. DB stats show
  the main list statement at 17–38 ms mean (max 121 ms) — so ~1.4–2.3 s is **not**
  SQL. Remaining miss-path work (`catalog/router.py:178`, `service.py:~105-230`,
  `repository.py:577`) is: 3 sequential DB round trips (list → images →
  collections) each paying WAN latency to Supabase (ap-southeast-1) + pool
  checkout, then Pydantic build of N items + `model_dump` + JSON + gzip.
- Likely contributors (*hypothesis — profile with `PROFILING_ENABLED` per-span
  timings or py-spy before changing*): (a) connection (re)establishment on pool
  growth/recycle through PgBouncer, (b) serial `images` → `collections` queries
  that are independent and can be `asyncio.gather`ed (needs two sessions —
  AsyncSession can't run concurrent statements) or merged into one CTE, (c)
  pool wait under concurrency (k6 ramp reached p95 15 s @100 VUs).
- Every distinct filter/page_size combination is a full miss, and filter
  combinations are user-controlled → low hit rate by construction.
- **Fix options, in order of leverage:**
  1. Cache the *full unfiltered active catalog* (220 products) once and
     filter/sort/paginate in-process or in Redis; trivial at this size and
     eliminates the miss path for all filter combos. (Largest win.)
  2. Normalise `page_size` to a small set (12/24/36/48) so keys collide.
  3. Merge images + collections hydration into the list statement (LATERAL /
     `json_agg`) → 1 round trip instead of 3.
  4. Warm top-N combos in `cache_warmer` (already exists; add `page_size`
     variants used by the storefront).

### F3. SSR returns an empty shell for home and listing pages (LCP + SEO)
- Prod profile: `/` SSR = 1,725 B, `/products` = 1,784 B, `/products/{slug}` = 4,391 B
  on the wire. The home route (`routes/index.tsx`) has **no `loader`**; data comes
  from `useHomepage()` after hydration. Only `products.index`, `products.$slug`,
  `collections.$slug` have loaders.
- Consequence: LCP waits for HTML → 300 KB gz JS parse → API call → render. Crawlers
  that don't execute JS see no content. Hero image `fetchPriority` logic
  (`Hero.tsx:363`) can't help because the URL isn't known until the API returns.
- **Fix:** add `loader: ({context:{queryClient}}) => queryClient.ensureQueryData(homepageQuery)`
  to `/` (same idiom as `products.index.tsx:51`), emit `<link rel=preload as=image>`
  for the first hero slide from loader data. Verify with `curl | wc -c` that HTML
  grows to include section markup.

---

## P1

### F4. Main bundle 302 KB gz; zero `React.lazy`
- `grep "lazy("` → 0 hits. Route chunks exist (router auto-splitting) but the
  entry still carries: root-level overlays (`CartDrawer`, `SearchOverlay`,
  `WelcomeOfferModal`, `WhatsAppFab`, `MobileBottomNav`, `ScrollProgress`),
  Sentry, supabase-js, and shared state stores.
- `recharts`, `swiper`, `socket.io-client` are declared deps; **no imports found
  in storefront/src** → remove from `package.json` (they cost install/CI time and
  risk accidental bundling).
- **Fix:** `lazy()` + `Suspense` for CartDrawer/SearchOverlay/WelcomeOfferModal
  (all interaction-gated); defer Sentry/GA init to `requestIdleCallback`; add a
  `size-limit`/bundlesize CI gate at 220 KB gz for the entry. Target ≤ 200 KB.
  Run `npx vite-bundle-visualizer` first to confirm what the 1 MB actually is.

### F5. Fonts: render-blocking Google Fonts CSS, 3 families, 11 weights
- `routes/__root.tsx:127-133`: Cormorant Garamond (4 weights) + Inter (3) + Noto
  Serif (2) via `fonts.googleapis.com` stylesheet (render-blocking; extra DNS+TLS
  to two origins).
- **Fix:** self-host subsetted WOFF2 (latin), `font-display: swap`, preload the
  2 above-the-fold faces, drop unused weights (check usage first).

### F6. 5.7 MB Pexels video with `preload="auto"` ... (`CraftsmanshipVideo.tsx:6,46`)
- Default `mp4_url` is a 1080p Pexels file (5.7 MB). `preload="auto"` makes the
  browser fetch it eagerly even far below the fold; also a third-party
  dependency on the render path.
- **Fix:** `preload="none"` (or `metadata`) + poster, start loading via
  IntersectionObserver when within ~1 viewport; host a 720p/≤1.5 MB H.264/AV1
  rendition on own CDN.

### F7. Four stacked `BaseHTTPMiddleware` on every API request (`main.py:229-246`)
- `AuditMiddleware`, `SecurityHeadersMiddleware`, `RequestIDMiddleware`,
  `RequestLoggingMiddleware` all subclass `BaseHTTPMiddleware` (each wraps the
  response in a task + memory-stream; known per-layer overhead, breaks
  contextvar propagation edge cases, and buffers streamed bodies — relevant to
  the SSE endpoints). `AuditMiddleware` is a no-op for ~all GETs but still pays
  the layer.
- **Fix:** convert to pure ASGI middlewares (single class doing request-id,
  security headers, logging; audit only for mutating admin/auth). Expect a
  measurable p50 drop (low single-digit ms/req) and lower CPU at high RPS.
  *Measure with the existing k6 ramp before/after.*

### F8. Hot-row lock wait on inventory reservation (`reservation_service.py:137`)
- `SELECT … FROM product_variants … FOR UPDATE OF v`: 147 calls, **mean 661 ms,
  max 5.7 s** (0 blocks read → pure lock wait, not I/O). Serializes concurrent
  checkouts of the same variant — correct for oversell protection, but latency
  grows linearly with contention (flash-sale/launch scenario).
- Likely inflated by k6 contention tests, but it is the structural ceiling for
  per-variant checkout throughput.
- **Fix options:** keep transactions that hold the lock minimal (move SSE/event
  publish, cache bust, notification work strictly after COMMIT); consider an
  atomic conditional `UPDATE … SET reserved = reserved + :q WHERE stock-reserved-sold >= :q`
  (no explicit `FOR UPDATE`, single statement) — verify against the existing
  reservation state machine tests before adopting.

### F9. Cloudflare is not caching API/SSR responses (`cf-cache-status: DYNAMIC`)
- Already noted in the 2026-10-10 profile (finding 4); every request hits origin
  even for `public, max-age` responses. A Cloudflare Cache Rule for
  `api.hadha.co/api/v1/{categories,collections,products,cms,company,search/trending}`
  (respect origin `Cache-Control`, key on query string, bypass if
  `Authorization`/cookie present) would remove most origin traffic. Note `Vary:
  Accept, Authorization` in `add_cache_headers` makes CF treat variants
  separately — drop `Authorization` from `Vary` on genuinely public endpoints.

---

## P2

- **F10. Double JSON round-trip on cached hits** — `categories/router.py:~82-95`,
  `search/router.py:112-114,149-151,190-192`, `cms/router.py:83,117,151`:
  `model_dump_json()` → `json.loads()` → `JSONResponse` re-dumps. Return
  `Response(content=bytes, media_type="application/json")` straight from the
  cached string; also lets ETag be computed from the cached bytes. Small CPU win
  per hit, multiplied by RPS. Same for `/products` (`ok(result).model_dump()`
  re-validates a dict the cache already holds in final shape).
- **F11. Event-loop CPU in `GZipMiddleware`** — default `compresslevel=9` on 20–35 KB
  JSON bodies. Set `compresslevel=4–5`; or let nginx/Cloudflare compress and
  remove it from the app.
- **F12. Worker polling** — `reclaim_stale_processing` + `list_pending_images`
  ran 1.36 M times each (≈every 5 s; 0.0–0.1 ms each, 3 s total CPU — cheap, but
  constant). `idx_images_status_updated_at` is flagged "unused" by the advisor
  (planner prefers seq scan on 557 rows). Back the interval off to 15–30 s or
  switch to LISTEN/NOTIFY; not urgent.
- **F13. `notification_rules` upsert on every process start** — 22,626 calls ×
  7.3 ms = 165 s cumulative (`pg_stat_statements`). It runs once per worker boot
  (`main.py` lifespan → `sync_notification_rules`) with one INSERT per rule.
  Batch into a single `INSERT … ON CONFLICT DO NOTHING` and skip when a hash of
  the registry matches a stored value.
- **F14. Admin session writes** — `UPDATE admin_sessions SET last_activity_at…`
  mean 124 ms (478 calls). Already throttled (`auth/service.py:42`); the cost is
  per-statement latency, not frequency. Fire-and-forget after response.
- **F15. Startup blocks on Resend probe** (`main.py:42-72`, up to 5 s) before the
  app accepts traffic — move into a background task; only the 401 hard-abort
  needs to remain, and it can run post-bind.
- **F16. Unused indexes** (advisor): `idx_products_live_*`, `idx_images_status_updated_at`,
  etc. At 220 products the planner won't use them; they are harmless now but
  add write cost and will matter as the catalog grows. Re-evaluate at ≥5k
  products — do **not** drop on this evidence alone.
- **F17. RLS advisors** (`auth_rls_initplan`, `multiple_permissive_policies`):
  only relevant for PostgREST/Supabase-client access; the FastAPI backend uses a
  direct pooled connection. Wrap `auth.uid()` as `(select auth.uid())` the next
  time policies are touched (`profiles_*`, `orders_*`).
- **F18. N+1 style loops** (admin/cancel paths, low frequency):
  `orders/service.py:1139` (`record_return` per item),
  `reservation_service.py:232` (`get_available_stock` per product, fallback),
  `catalog/service.py:313` (variant SKU check per variant). Batch with
  `IN (...)` if these become hot.
- **F19. Stale docs**: memory/DB-architecture notes (two-engine NullPool) no
  longer match `core/database.py`, which now aliases
  `AsyncWorkerSessionLocal = AsyncSessionLocal` over one pool (size 6+4 default).
  The pgbouncer `DISCARD ALL`/`get_auth` counters in `pg_stat_statements`
  (≈870k/582k) are cumulative from the old NullPool era, not current churn.

---

## What is already good (don't touch)

- List query: window `COUNT(*) OVER()`, stable ordering, partial "live" indexes,
  2-image-per-product hydration — well designed.
- SWR cache with request coalescing and stale serving; Redis circuit-breaker with
  local fallback.
- No sequential-scan pathologies at current volume; worst `seq_scan` tables are
  ≤ 220 rows.
- Event-loop lag monitor + profiler already in place — use them for F2/F7
  measurement.

## Suggested order of work

1. **F1** (assets) — hours, biggest user-visible win, zero risk.
2. **F3** (home loader + hero preload) and **F6** (video preload) — half a day.
3. **F4/F5** (lazy overlays, self-host fonts, remove dead deps, size gate).
4. **F2** (catalog snapshot cache) after a py-spy/profiler capture of the miss
   path to confirm the cause; then re-run `k6/prod-readonly/storefront-ramp.js`.
5. **F7/F9/F10/F11** backend + edge tuning, measured with the same ramp.
6. Add RUM (`web-vitals` → `/analytics`) and Lighthouse CI so LCP/INP/CLS stop
   being guesses.
