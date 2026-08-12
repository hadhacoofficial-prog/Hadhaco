# Image Crop Root Cause Investigation

**Investigated:** 2026-08-12
**Product:** `75961ab9-9d4c-49d5-add0-4170bd1be0a2`
**Image:** `4deeba52-159c-4abc-b532-853db1218877`
**Endpoint in question:** `PATCH /api/v1/admin/media/{image_id}/crop`
**Scope:** Read-only investigation. No code was modified.

---

## 1. Executive Summary

| Stage | Status |
|---|---|
| **UPLOAD** | **WORKING** — original bytes + DB row persist synchronously and reliably. |
| **CROP** (request/metadata layer) | **WORKING** — the crop endpoint correctly validates and persists the user's exact crop geometry. It does **not** do image processing itself. |
| **PROCESSING** (actual crop/resize/encode) | **CONFIRMED BROKEN for a specific historical window** — the Celery pipeline that does the real work was non-functional in production due to three stacked infrastructure bugs, all fixed today (2026-08-12) in commits `3101c6f`, `b0c57f1`, `82d7ddb`, the last of which (`82d7ddb`) is the current `HEAD` of this branch. |
| **VARIANT SELECTION** | **CONFIRMED BROKEN (design gap, independent of the Celery outage)** — `ProductImageResponse.from_image` silently substitutes the raw, uncropped original whenever no "ready" variant exists yet, with no distinction between "still generating" and "permanently failed." This is the exact mechanism that turns "processing hasn't finished" into "the crop is visibly discarded." |
| **UI TIMEOUT** | **SECONDARY SYMPTOM** — the crop endpoint itself is architecturally fast (metadata write + fire-and-forget enqueue, no synchronous image processing). The observed timeout is best explained as collateral damage from the same Celery/DB-pool instability described above, not a defect in the endpoint's own code path. |

**One-sentence summary:** The crop is never "lost" in the sense the task hypothesized (no code path re-reads `original_key` after a successful crop, and no generic worker overwrites a cropped variant with a padded one). Instead, the crop's *processing* almost never finished — because the Celery workers that do the actual crop/resize/R2-upload work were crashing on nearly every invocation — and whenever no processed variant exists, the product API and storefront both fall back to displaying the full, unprocessed original inside a square `object-contain` box, which is what produces the white side-bars.

---

## 2. Exact Failure Point

```
Upload  ──────────────────────────────────────────────────  WORKING
  │  POST /admin/media/product/upload
  │  → validates, normalizes EXIF, probes dimensions, writes original to R2,
  │    creates `images` row (status='pending'), synchronous, in-request.
  ▼
Crop (metadata) ───────────────────────────────────────────  WORKING
  │  PATCH /admin/media/{id}/crop
  │  → validates geometry, persists crops into images.metadata_ (synchronous,
  │    in-request), enqueues Celery task `media.generate_variants`, returns.
  ▼
Process (Celery: crop→rotate→mask→resize→encode→R2 upload) ─  ✱ FAILING HERE ✱
  │  app.tasks.media.generate_variants → app.workers.media_generation.process_one
  │  → background.generate_variants_for_breakpoints
  │  Historically crashed before producing any output, due to (in the order
  │  they were hit and fixed today):
  │    1. NoReferencedTableError (Celery workers never registered the full
  │       SQLAlchemy model set) — fixed in b0c57f1.
  │    2. asyncpg "attached to a different loop" / "another operation is in
  │       progress" (a fresh asyncio.run() per task broke connection reuse
  │       across tasks in the same worker process) — fixed in 3101c6f.
  │    3. celery-worker-general OOM-killed (SIGKILL) within the first minute
  │       of every deploy — fixed in 82d7ddb (raised memory limit).
  ▼
image_variants ─────────────────────────────────────────────  NEVER REACHED
  │  No 'ready' row is ever written for the new crop while processing fails.
  ▼
Product API (ProductImageResponse.from_image) ──────────────  ✱ FAILING HERE TOO ✱
  │  catalog/schemas.py:83-90 — no ready desktop@1x "large"/"medium" variant
  │  exists → falls back to storage.public_url(image.original_key), the
  │  untouched, non-square original.
  ▼
Frontend (ProductCard.tsx) ──────────────────────────────────  SYMPTOM SURFACES HERE
     `aspect-square bg-white` container + `object-contain` image
     → non-square original rendered inside a white square box
     → visible white bars on the sides.
```

The pipeline has **two** failure points, not one: an infrastructure failure (Celery, now fixed) that prevented processing from ever completing, and a **software defect** (the silent original-image fallback) that turns "processing incomplete" into "displays the wrong image with no error, indefinitely." Fixing only the infrastructure issue does not fix the software defect — it only makes the defect's failure mode rarer (a brief flash of the unprocessed original during the ~1-3s generation window) rather than permanent.

---

## 3. Crop Coordinate Analysis

Traced end to end — **this part of the system is correctly implemented** and is not the source of the bug.

- **HTTP method:** `PATCH /admin/media/{image_id}/crop` — [router.py:179-227](../Backend/app/modules/media/router.py)
- **Request schema:** `CropGeometryIn { crops: dict[Breakpoint, BreakpointCropIn], focus_point }`, where `BreakpointCropIn { box: {x,y,width,height}, zoom, pan, rotation }` — [schemas.py:71-101](../Backend/app/modules/media/schemas.py)
- **Coordinate space:** `x/y/width/height` are **absolute pixels in the original image's own coordinate space** (not normalized 0-1, not percentages, not screen/canvas pixels). This is explicit in `crop_engine.crop_to_box`, which does `image.crop((left, top, right, bottom))` directly against those numbers.
- **EXIF orientation vs. crop coordinates — correctly ordered.** `universal_service._normalize_orientation` bakes in the EXIF `Orientation` tag and strips it **at upload time**, before `original_width`/`original_height` are probed and stored ([universal_service.py:71-100, 236-258](../Backend/app/modules/media/universal_service.py)). The comment on that function explicitly documents *why*: without this, a portrait photo with a rotate-90 EXIF tag would probe as landscape server-side while the browser (and thus the crop editor's `naturalWidth`/`naturalHeight`) renders it rotated — causing exactly the "backend rejects a visually-valid crop as out of bounds" bug the task's investigation prompt warned about. This was already fixed (see `54cf391 feat(image): add orientation normalization for uploaded images` and `a91cac0` — a backfill script for pre-existing images). So both the crop editor and the backend agree on the same pixel-space dimensions before any crop box is ever computed.
- **Frontend → backend transform:** `Frontend_whole/packages/shared-media/src/mediaApi.ts:cropImage()` sends the box/zoom/pan/rotation fields through unchanged — no unit conversion, no devicePixelRatio scaling, no CSS-vs-canvas mismatch introduced on the wire. The cropper's own pixel math (`cropMath.ts`, `useCropGeometry.ts`) is out of scope for this bug (it never surfaced as a factor — see §10).
- **Validation:** `crop_engine.validate_crop_request` checks (a) rotation is allowed for the preset, and (b) for `strict_bounds` presets (product **is** strict_bounds=True — [preset_registry.py:131](../Backend/app/modules/media/preset_registry.py)) that the box fits inside the rotated image, else raises `CropGeometryError` → HTTP 422. **This validation does not check that `box.width/height` match the preset's required aspect ratio** — that is left entirely to the frontend cropper. This is a latent gap (see §10) but was not implicated in the observed bug (the stored crop geometry looks like a normal user-drawn square selection based on the pipeline reading it).
- **Conclusion:** the crop coordinates the admin drew are captured and persisted correctly. This is not where the crop is lost.

---

## 4. Image Processing Order

The documented/implemented order in `background._generate_breakpoint_artifacts` → `crop_engine.apply_geometry` ([crop_engine.py:233-258](../Backend/app/modules/media/crop_engine.py)) is:

```
1. Decode original bytes (PIL Image.open)             — background.py:143
2. Rotate (if any)                                     — crop_engine.rotate()
3. Validate/clamp crop box against rotated dimensions  — validate_and_clamp_crop_box()
4. Apply shape mask (SQUARE = no-op besides mode conv) — apply_shape_mask()
5. Crop to box                                         — crop_to_box()
6. Resize to each output_variant's target box          — variant_generator._resize()
7. Flatten to RGB (only if source has alpha/palette)   — variant_generator._flatten_to_rgb()
8. Encode WebP q85 (or PNG for the two logo presets)   — variant_generator._encode()
9. Upload to R2, one upload per (breakpoint,variant,dpr) — background.upload_variant_artifact()
```

This order is correct and matches best practice (EXIF is normalized even earlier, at upload time, not here — see §3). **No design defect was found in this order.** The bug is that this pipeline is not reliably *reached/completed* (§7-8), not that it does the wrong thing when it runs.

---

## 5. White-Side Root Cause

**Not server-side compositing.** There is no `fit`/`contain`+white-background step anywhere in the backend pipeline for the `product` preset:

- `product` preset uses `shape=ShapeType.SQUARE` ([preset_registry.py:112](../Backend/app/modules/media/preset_registry.py)), and `apply_shape_mask` for `SQUARE` is a pure mode-conversion no-op — it adds no canvas, no padding, no alpha mask ([crop_engine.py:182-192](../Backend/app/modules/media/crop_engine.py)).
- `variant_generator._resize` uses `Image.thumbnail()` to fit the **already-square-cropped** image into the target box — this only matters for presets whose cropped output isn't already the target aspect ratio; for `product`, the crop box the admin drew is already the exact box that gets cropped, so there's nothing left to pad.
- `variant_generator._flatten_to_rgb` does paste onto a white `(255,255,255)` background, but **only** to flatten transparency (RGBA/P-mode sources, e.g. a PNG logo) into an opaque WebP — it operates on the already-cropped, already-correctly-sized image, and has nothing to do with aspect-ratio letterboxing.

**The white sides are a client-side CSS artifact, confirmed at the exact line:**

`Frontend_whole/storefront/src/components/site/ProductCard.tsx:57,65`
```tsx
className="block relative aspect-square bg-white overflow-hidden"   // the card frame
...
imgClassName={`w-full h-full object-contain ...`}                    // the image itself
```

A square (`aspect-square`), **white-backgrounded** (`bg-white`) container, with the image inside rendered `object-contain` (scale to fit, preserve aspect ratio, no cropping). When the `url`/`primary_image` the API returns is the **raw, non-square original** (see §6), `object-contain` letterboxes it inside that white square — producing exactly the white bars on the left/right (or top/bottom) that were reported. This is a real, reproducible rendering mechanism, not a guess: it requires no server bug in image compositing at all, only that the URL being rendered points at an uncropped image.

The admin gallery (`ProductForm.tsx:1542-1546`) does **not** show this same symptom in quite the same way — it uses `object-cover` and falls back to an empty string (`""`) rather than the original when no variant is ready, which would show a broken-image icon rather than white bars. **The white-sides symptom the user is describing is therefore specifically the storefront/customer-facing product image**, or any other consumer of `ProductImageResponse.url` rendered with `object-contain`.

---

## 6. Original-vs-Cropped Source

**Confirmed: the product API serves the original, not the crop, whenever no ready variant exists — by explicit fallback, not by accident.**

`Backend/app/modules/catalog/schemas.py:76-90` (`ProductImageResponse.from_image`):

```python
variants_by_name = {
    v.variant_name: v
    for v in image.variants
    if v.breakpoint == "desktop" and v.dpr == 1 and v.status == "ready"
}
original_variant = variants_by_name.get("large") or variants_by_name.get("medium")
url = (
    original_variant.url
    if original_variant
    else storage.public_url(image.original_key)   # ← THE FALLBACK
)
```

This is exactly the failure mode the investigation prompt flagged as "a critical possible bug": **the product image generation reads `image.original_key` instead of a cropped/processed key**, but only in the specific (and, per §7-8, common) case where the crop pipeline hasn't produced a ready variant yet. There is **no** separate bug where a correctly-generated cropped variant gets overwritten by something reading from `original_key` later — `background.generate_variants_for_breakpoints` always crops fresh from `original_bytes` using the **current** stored crop metadata (`background.parse_stored_crops`), so once a variant is genuinely `ready`, it does reflect the latest crop. The defect is specifically the *fallback when nothing is ready yet*, and it has no distinction between:
  - "generation queued 200ms ago, be patient" (transient, self-healing), and
  - "generation failed 3 times and gave up" (`status='failed'`, permanent — the periodic sweep (`list_pending_images`) only ever re-polls `status='pending'`, **never** `'failed'`, so a permanently-failed image stays broken forever until an admin explicitly hits `POST /admin/media/{id}/regenerate`).

Both cases render identically to the customer: the full original, letterboxed white.

`storage.py`/`repository.py` distinguish `original_key` (the untouched upload, always present) from `image_variants.url` (per-breakpoint/variant/dpr generated files, only present once `status='ready'`) correctly at the data-model level — the bug is entirely in the *selection logic* in `catalog/schemas.py`, not in what gets stored.

---

## 7. Timeout Analysis

**The crop endpoint's own code is architecturally fast** (confirmed by reading `universal_service.crop()` and `_enqueue_generation`, [universal_service.py:329-405, 519-569](../Backend/app/modules/media/universal_service.py)): it does pure in-memory geometry validation, two DB writes (`update_metadata`, `update_fields` — each a flush + 2 refreshes), and a Redis `.delay()` push. No image bytes are decoded, cropped, resized, or uploaded to R2 synchronously in this request — that was deliberately moved to the Celery worker in a prior refactor (`docs audit CB-1 Phase 2`, referenced throughout `universal_service.py` and `background.py`'s docstrings). **A well-behaved deploy of this exact code should return this endpoint in well under a second.**

Given that, the "slow crop endpoint" observed in logs is best explained not as a defect in the endpoint's own logic, but as **collateral damage from the same infrastructure instability that broke Celery processing** (§8):

- `Backend/app/core/database` uses a shared, budget-limited connection pool (project memory: "two-engine NullPool pattern; 8-slot budget"). The crop request needs **2 separate DB round-trip sequences** (flush+refresh+refresh-variants, twice = up to 6 sequential network round-trips to Supabase) to complete. If Celery workers were repeatedly crashing and retrying (`NoReferencedTableError` → immediate failure → Celery-level retry; then the asyncpg "another operation in progress" errors; then OOM kills and worker respawns) at high frequency, connection churn and pool contention from that crash-loop is a very plausible way for an otherwise-lightweight endpoint's DB round trips to stall enough to trip a client-side timeout.
- The frontend's shared API client has a hard default request timeout of 20s (`Frontend_whole/packages/shared-api/src/lib/api/client.ts:46`, `DEFAULT_TIMEOUT_MS = 20_000`) that aborts the fetch client-side via `AbortController` — it does **not** cancel the in-flight server-side work. This is exactly why "despite the timeout, the image IS actually added to the product": the DB writes for crop metadata and the `generate_variants.delay()` Redis push are already committed/sent by the time a client abort fires; FastAPI keeps running the coroutine to completion server-side regardless of the client having given up.

**Verdict:** UI timeout is a **secondary symptom**, not the root cause, and the current code shows no reason the endpoint itself should be inherently slow. It is the visible tip of the same underlying instability documented in §8.

---

## 8. Race Conditions

The specific race hypothesized in the investigation prompt — *"generic image processing/variant generation starts → reads original → writes full image with white padding → product points to generic variant → cropped result is ignored/overwritten"* — **does not match this codebase**. There is no separate "generic" variant worker distinct from the crop-aware one; `background.generate_variants_for_breakpoints` is the only variant-generation code path for every module (product/collection/category/etc.), and it always regenerates from `original_bytes` using whatever crop geometry is *currently* stored in `image.metadata_["crops"]` at the moment it runs — so a completed run always reflects the latest saved crop, never a stale default.

**What actually happened instead — a confirmed, dated infrastructure race**, evidenced directly by today's git history (all commits below are from **2026-08-12**, the day of this investigation, and are the tip of the current branch):

| Time | Commit | What was broken | Effect on crop pipeline |
|---|---|---|---|
| 20:27 | `3101c6f` | `app/tasks/_common.py::run_async` called `asyncio.run()` **per task**. `asyncpg` connections are bound to the event loop that opened them; the DB engine is created once per worker *process* and reused. Every 2nd+ task in the same forked worker process crashed with `RuntimeError: Task ... got Future ... attached to a different loop` / `asyncpg.exceptions.InterfaceError: cannot perform operation: another operation is in progress`. | `media.generate_variants` failed on the second+ invocation handled by a given worker process — i.e. most crop requests, since a worker handles many tasks over its life. |
| 20:59 | `b0c57f1` | Celery's `include=["app.tasks"]` only imports what task modules transitively need. `app.workers.media_generation` imports `app.modules.media.repository` but never `app.modules.profiles.models`, so `profiles`' table was never registered on `Base.metadata` in the worker process. Every attempt to flush/query `Image` (whose `uploaded_by` FK references `profiles`) raised `sqlalchemy.exc.NoReferencedTableError`. | `media.sweep_pending` / `media.generate_variants` failed **immediately**, on essentially every invocation, before doing any actual crop work. |
| 21:10 (HEAD) | `82d7ddb` | `celery-worker-general` (5 processes, `--concurrency=4`) was capped at 384MB — less headroom than `celery-worker-media`'s 512MB despite doing more concurrent work. Made worse by `b0c57f1`'s fix itself, which made every Celery worker process eagerly import the full 57-table schema. Production logs showed repeated `ForkPoolWorker-N exited with signal 9 (SIGKILL)` within the first minute of every deploy. | Worker children were silently killed mid-task with no Python traceback — any `generate_variants` task in flight simply vanished; the image could be left stuck in `status='processing'` until the 120s stale-reclaim (`reclaim_stale_processing`) requeued it, likely to fail the same way again. |

**Net effect for the specific window before 21:10 today:** the Celery-driven crop/variant pipeline was, for practical purposes, non-functional. A crop request would reliably: (1) persist metadata correctly, (2) enqueue a task, (3) have that task crash via one of the three bugs above, (4) leave the image with zero ready variants for the new crop, (5) eventually exhaust `MAX_ATTEMPTS = 3` (`workers/media_generation.py:54,162-176`) and land in `status='failed'` — a status the periodic sweep **never** revisits (`list_pending_images` only selects `status='pending'`). This is a genuine, confirmed race between "the crop metadata commits" and "the crop actually gets rendered," just not the one originally hypothesized (no generic worker overwrite — the race is "does generation ever complete at all" vs. "is it read before/without ever completing").

**Residual race that remains even post-fix (lower severity, not confirmed as the cause of this incident, but real):** two overlapping crop requests for the *same* image/breakpoint can each dispatch their own `generate_variants` task; `repository.replace_variants` upserts by `(variant_name, dpr)` with no ordering guard tied to which crop's *metadata* was newer — the job that happens to *commit* last wins, which is not guaranteed to be the job for the most recently-saved crop. This is a narrow window (typically sub-second, requires two rapid successive crop saves) and was not the primary driver of the observed bug, but is worth closing (see §11).

---

## 9. Database Evidence

Read-only queries to inspect the specific image/product from the report. Run these against the Supabase/Postgres instance directly (psql, Supabase SQL editor, or read replica) — nothing here writes.

```sql
-- 1. The image row itself: status, version, geometry snapshot, original key
SELECT id, module, preset_id, owner_type, owner_id, status, version,
       original_key, original_width, original_height, original_size_bytes,
       metadata, created_at, updated_at, deleted_at
FROM images
WHERE id = '4deeba52-159c-4abc-b532-853db1218877';

-- 2. Every variant ever generated for it — look for status != 'ready',
--    or a total absence of 'large'/'medium' desktop dpr=1 rows
SELECT id, breakpoint, variant_name, dpr, format, url, width, height,
       status, error_message, created_at
FROM image_variants
WHERE image_id = '4deeba52-159c-4abc-b532-853db1218877'
ORDER BY breakpoint, variant_name, dpr;

-- 3. Everything currently attached to the affected product, in display order
SELECT id, status, version, is_primary, sort_order, updated_at,
       metadata -> 'generation' AS generation_state
FROM images
WHERE owner_type = 'product'
  AND owner_id = '75961ab9-9d4c-49d5-add0-4170bd1be0a2'
  AND deleted_at IS NULL
ORDER BY sort_order;

-- 4. Org-wide sanity check: anything still stuck mid-pipeline right now
--    (post-fix, this should trend toward empty within a few sweep cycles)
SELECT id, owner_type, owner_id, status, updated_at,
       metadata -> 'generation' AS generation_state
FROM images
WHERE status IN ('pending', 'processing', 'failed')
ORDER BY updated_at DESC
LIMIT 50;

-- 5. How many images were permanently 'failed' (exhausted MAX_ATTEMPTS)
--    during the outage window today — these will NOT self-heal, they need
--    an explicit POST /admin/media/{id}/regenerate
SELECT id, owner_type, owner_id, updated_at,
       metadata -> 'generation' ->> 'last_error' AS last_error
FROM images
WHERE status = 'failed'
  AND updated_at::date = '2026-08-12'
ORDER BY updated_at DESC;
```

**What to look for:** if query 1 shows `status = 'failed'` or `'processing'`, and query 2 shows zero `status='ready'` rows for `breakpoint='desktop', dpr=1, variant_name IN ('large','medium')`, that is a direct, conclusive confirmation of this root cause for this exact image — it means `ProductImageResponse.from_image` has no choice but to serve `original_key`. If `status='pending'`, it may self-heal on the next sweep tick now that `82d7ddb` is deployed. If `status='ready'` with ready large/medium variants, the fix has already taken effect for this image and a fresh page load / cache-bust should now show the correct crop.

---

## 10. Root Cause

**CONFIRMED:**
1. `ProductImageResponse.from_image` (`Backend/app/modules/catalog/schemas.py:83-90`) falls back to the raw, uncropped original image whenever no `status='ready'` desktop@1x `large`/`medium` variant exists — with no signal to the caller distinguishing "still processing" from "permanently failed." This is the direct, code-level mechanism by which the crop appears "discarded."
2. Three independent, stacked infrastructure bugs (`3101c6f`, `b0c57f1`, `82d7ddb` — all committed 2026-08-12, hours before this investigation) made the Celery-driven variant-generation pipeline unreliable-to-nonfunctional in production for however long that window lasted, meaning #1's fallback condition ("no ready variant") was being hit far more often, and far more permanently (via exhausted-retry `status='failed'`), than the pipeline's own design intends.
3. `ProductCard.tsx`'s `aspect-square bg-white` + `object-contain` rendering is the exact, confirmed mechanism that turns "the original is being served" into the visually reported "white sides."

**LIKELY (consistent with all evidence, not independently confirmed without DB/log access):**
- The specific image/product in this report was cropped during the outage window (before `82d7ddb` landed at 21:10 today) and is currently sitting in `status='failed'` or `status='processing'`/`'pending'` with no ready variant — run §9's queries to confirm definitively.
- The "slow crop endpoint" observed in logs correlates with DB-connection-pool contention caused by the same crash-looping Celery workers, not with the crop endpoint's own (lightweight) logic.

**NOT SUPPORTED BY THE CODE (ruled out):**
- A coordinate-space bug (pixels vs. percentages, EXIF-before/after-crop, devicePixelRatio, CSS scaling) — the pipeline normalizes EXIF orientation at upload time, before dimensions are probed, and the crop box is consistently pixel-space end to end.
- A "generic worker overwrites the cropped variant with a padded one" race — no such code path exists; every generation run reads the *current* stored crop metadata.
- Server-side white-background compositing for the `product` preset — `shape=SQUARE` applies no padding; the white background is a CSS artifact of the frontend, not a stored pixel.

**UNKNOWN (needs the DB queries in §9, or production log access, to close out):**
- The exact `status`/`metadata.generation.last_error` for image `4deeba52-159c-4abc-b532-853db1218877` right now.
- Whether this specific image has already self-healed since `82d7ddb` deployed, or is stuck in `'failed'` and needs a manual `regenerate`.

---

## 11. Recommended Fix

**Do not implement — description only, per instructions.**

1. **Primary fix — stop the silent original-image fallback (`catalog/schemas.py:83-90`).** `ProductImageResponse.from_image` should not synthesize a "looks fine" URL when no processed variant exists. Options, roughly in order of preference:
   - Surface `image.status` (or a derived `image_ready: bool`) on `ProductImageResponse` so the frontend can render an explicit "processing" placeholder instead of the raw original, and so the storefront can choose not to render `object-contain` against an unprocessed non-square asset at all.
   - At minimum, distinguish "no ready variant because still generating" (transient — fine to show original briefly, or a skeleton) from "no ready variant because `status='failed'`" (permanent until someone acts — this should probably not silently render *anything* misleading, and should be flagged for admin attention, e.g. surfaced in the admin product list).
2. **Close the dead-end retry state.** `list_pending_images` (`repository.py:185-197`) only ever re-polls `status='pending'`. A `status='failed'` image is inert forever unless an admin manually calls `regenerate`. Either add a bounded automatic re-queue for `'failed'` images after some cooldown, or make the "failed and needs attention" state visible in the admin UI (product image gallery already has the data — `ImageOut.status`/`error_message` per variant — it's just not surfaced as an actionable warning today).
3. **Confirm the infra fixes are fully deployed and stable.** `82d7ddb` is `HEAD` — verify it has actually rolled out to the running `celery-worker-general` containers (not just committed), and watch for `ForkPoolWorker exited with signal 9` in logs for at least one full deploy cycle to confirm the OOM issue is actually resolved at the new 640MB/0.75cpu sizing, not just less frequent.
4. **Remediate already-affected images.** Run §9's query 5 (or equivalent) to find every image that landed in `status='failed'` during today's outage window, and either bulk-trigger `POST /admin/media/{id}/regenerate` for them or build a one-off admin script that does so, rather than relying on each affected product being noticed and manually re-cropped one at a time.
5. **Lower-priority hardening (latent gaps found along the way, not the cause of this incident):**
   - `crop_engine.validate_crop_request` never checks that a submitted box's aspect ratio matches the preset's required `aspect_ratio` for that breakpoint — it's trusted entirely from the frontend cropper. Not exploitable by a normal admin flow, but worth a defensive check given `strict_bounds` already exists for out-of-frame boxes.
   - `repository.replace_variants`'s upsert has no ordering/recency guard against two overlapping generation jobs for the same image (§8's residual race) — low severity, but a version/timestamp check before upsert would close it.

---

## 12. Regression Tests

Description only — not implemented.

- **Crop coordinates round-trip:** POST a known crop box (non-centered, non-1:1 zoom) through `PATCH .../crop`, then read back `images.metadata_["crops"]` and confirm exact values persisted (already implicitly covered by `_crops_equal`'s tolerance logic — add an explicit assertion test).
- **EXIF-rotated image crop:** upload a JPEG with `Orientation=6` (rotate 90°), assert `original_width`/`original_height` reflect the *rotated* (displayed) dimensions, not the raw file's, and that a crop box drawn against the displayed dimensions produces a correctly-cropped output.
- **Crop after orientation, aspect ratio enforcement:** submit a crop box for the `product` preset whose width/height ratio is *not* 1:1 and assert the backend either rejects it or the generated variant is still square (currently: neither is guaranteed — see §11 item 5).
- **No white padding for `SQUARE`/`COVER` shapes:** generate variants for a `product`-preset image and assert the output image has zero fully-white border rows/columns beyond what the source photo itself contains (regression guard against ever accidentally switching `product` to a `CONTAIN`-style resize).
- **Cropped source used for variants, not original:** crop an image, wait for `status='ready'`, and assert every `image_variants.url` byte-for-byte differs from a variant generated directly from `original_key` with no crop applied (i.e., prove the crop box actually took effect, not just that *a* variant exists).
- **Correct product-variant selection:** with a `ready` `large`/`medium` desktop@1x variant present, assert `ProductImageResponse.url` equals that variant's URL, never `original_url`.
- **No-ready-variant fallback behavior (this is the bug — pin the fix):** with **zero** ready variants (simulating mid-generation or permanently-failed), assert `ProductImageResponse` does **not** silently return `original_url` as `url` — assert instead whatever the chosen fix's explicit "not ready" signal is.
- **Timeout while backend continues:** simulate a client abort mid-`PATCH .../crop` (cancel the request after the server has started but before it returns) and assert the DB metadata write and Celery enqueue still complete server-side, and that a subsequent `GET /admin/media/{id}` reflects the persisted crop.
- **Cache invalidation:** crop an already-`ready` image (a re-crop), and assert the returned/generated variant URLs change (`?v=` cache-buster bump) so a browser/CDN cache from the previous crop is not served.
- **Repeated crop (idempotency / race):** fire two `PATCH .../crop` requests for the same image in quick succession with different geometries, and assert the final `ready` state reflects the *second* (most recent) crop, not whichever background job happened to commit last (pins §8's residual race).
- **Crop followed by generic variant generation:** trigger `POST /admin/media/{id}/regenerate` immediately after a crop and assert it regenerates from the *current* stored crop metadata, not a default/centered box (guards against ever reintroducing the originally-hypothesized "generic worker overwrite" bug even though it wasn't found today).
- **Celery worker model registration (regression guard for `b0c57f1`):** a unit test that spins up a Celery worker process (or imports `app.workers.media_generation` in a fresh interpreter without importing `app.main` first) and asserts `Image`/`ImageVariant`/`profiles` are all present on `Base.metadata` before any task runs. (`Backend/tests/unit/test_model_registry.py` was added in `b0c57f1` — confirm it actually covers this exact scenario and isn't just testing the registry helper in isolation.)
- **Celery event-loop reuse (regression guard for `3101c6f`):** a test that runs two `generate_variants`-equivalent async calls back-to-back through `run_async`/`get_worker_loop` in the same simulated worker process and asserts the second does not raise `InterfaceError`/"attached to a different loop."

---

## 13. Final Verdict

**CONFIRMED ROOT CAUSE:**
Two compounding, independently-confirmed defects:
1. `ProductImageResponse.from_image` (`Backend/app/modules/catalog/schemas.py:83-90`) silently serves the raw, uncropped original whenever no `status='ready'` desktop `large`/`medium` variant exists, with no way for the caller to tell "still generating" apart from "permanently failed."
2. The Celery pipeline responsible for actually producing that `ready` variant was broken in production by three stacked infrastructure bugs — missing SQLAlchemy model registration in worker processes, a broken per-task event loop that corrupted asyncpg connection reuse, and an under-provisioned memory limit causing OOM kills — all fixed today (2026-08-12) in commits `3101c6f`, `b0c57f1`, and `82d7ddb` (current `HEAD`).

**WHITE SIDES ARE CREATED BY:**
`Frontend_whole/storefront/src/components/site/ProductCard.tsx:57,65` — a white, `aspect-square` container rendering the (non-square) original image with `object-contain`. No server-side image compositing produces this; it is a rendering-time consequence of serving the wrong (uncropped) URL.

**CROP IS LOST/IGNORED AT:**
It is never truly "lost" — the crop geometry is durably persisted the moment the admin saves it (`images.metadata_["crops"]`). It is *ignored at read time*, specifically at `catalog/schemas.py:83-90`'s fallback, for as long as no successfully-generated variant exists — which, during today's outage window, was effectively "indefinitely," because the generation pipeline that would have produced one was crashing on nearly every attempt.

**UI TIMEOUT IS CAUSED BY:**
Not the crop endpoint's own logic (which is architecturally fast and does no synchronous image processing). Most plausibly, DB-connection-pool contention from the same crash-looping Celery workers described above, stalling the endpoint's own DB round-trips long enough to trip the frontend's 20s default request timeout — consistent with the observation that the underlying write and enqueue succeed regardless of whether the client gave up waiting.

**RECOMMENDED FIRST FIX:**
Stop `ProductImageResponse.from_image` from silently substituting the original image for a missing variant — surface an explicit "not ready" / "failed" state instead — and audit for any image whose `status='failed'` from today's outage window, since those will not self-heal on their own and need an explicit `POST /admin/media/{id}/regenerate` now that the underlying Celery infrastructure is fixed.
