# Universal Image Management System — Production-Readiness Audit

**Date:** 2026-07-09
**Auditor role:** Principal Architect / Sr FE / Sr BE / Perf / UX / QA / DevOps / R2 Architect (combined)
**Scope:** `Backend/app/modules/media/` + parallel media surfaces, `Frontend_whole/packages/shared-media`, `shared-types`, admin `*Form.tsx` call sites, storefront rendering.
**Method:** Source read of every file in the pipeline. Every claim is cited to `file:line`. Items that cannot be verified from source (live R2 bucket config, CDN edge behavior, running perf) are called out explicitly.

> **Verdict up front:** The *cropping/preview engine* is genuinely well built and the DB/storage model is sound. But the system is **only ~1/3 wired** (5 of 16 presets have a real UI), variant generation is **fully synchronous in-request**, a second **legacy CMS image pipeline still runs in parallel**, product re-crop **silently resets tablet/mobile framing**, and the storefront product grid **bypasses the responsive delivery path entirely**. Production-ready for products/collections/categories/avatars/reviews with fixes; **not** production-ready as the "universal" system it claims to be.

---

## 1. Executive Summary

The Universal Responsive Image System (URIS) centralizes upload → validate → crop (per-breakpoint) → shape-mask → resize → WebP/PNG → R2 → `images`/`image_variants` → API → storefront. The crop editor (`UniversalImageEditor`) is canvas-dominant, has undo/redo, an "All breakpoints" sync mode, and a CSS-transform live preview that correctly avoids canvas cross-origin tainting. Presets are the single source of truth and the backend Pydantic registry and the frontend TS mirror are **in exact sync** (verified field-by-field, §5).

However the migration is **incomplete and uneven**:

- Only **product, collection, category, avatar, review_photo** are actually consumed. The other **11 presets** (hero, promo_banner, gender_section, testimonial_avatar, instagram_tile, footer_logo, company_logo, seo_og, team_member, blog_cover, blog_inline) are defined but have **no upload surface** — CMS/hero/banner images still flow through the **legacy `CmsMediaService`** (`Backend/app/modules/cms/media_service.py`), a second, un-cropped, non-responsive R2 pipeline.
- **Variant generation runs synchronously inside the mutating HTTP request** (`universal_service.py:320-342`, `background.py`). A single product upload encodes+uploads **18 WebP files** (3 variants × 2 DPR × 3 breakpoints) before the response returns.
- **Product re-crop is lossy**: `ProductForm` only restores the *desktop* crop box on re-edit and reseeds tablet/mobile to centered defaults, which then overwrite the stored crops on save (§4, Critical Bug CB-2). It also diverges from Collection/Category which fetch fresh originals via `getImage` (§4).
- **Storefront product cards bypass `ResponsiveImage`** and render a single 1200px desktop variant via a raw `<img>` (`storefront/.../ProductCard.tsx:37`).

**Findings tally:** Critical **3**, High **7**, Medium **12**, Low **9**, Missing Features **8**.
**Production-Readiness Score: 6.1 / 10** (breakdown §30).

---

## 2. Overall Architecture

```
Admin UI (*Form.tsx)                     Backend (FastAPI)                    R2 + Postgres
──────────────────                       ─────────────────                    ─────────────
UniversalImageEditor ──uploadImage──►  POST /admin/media/{preset}/upload
  (react-easy-crop)                        UniversalImageService.upload
  useCropGeometry  ──cropImage──────►    PATCH /admin/media/{id}/crop           images (JSONB metadata)
  CroppedImageView (live preview)          .crop / .replace / .regenerate       image_variants (1 row/file)
                                           ↳ validation.validate_upload
                                           ↳ crop_engine.apply_geometry         R2: images/{module}/{owner_type}/
                                           ↳ variant_generator (WebP q85)           {owner_id}/{image_id}/...
                                           ↳ storage.put_* (asyncio.to_thread)
Storefront                               GET (catalog/categories/collections)  Cloudflare CDN (R2 public URL)
  ResponsiveImage (srcset)  ◄─ ImageBundle / primary_image / image_url
  ProductCard (raw <img>)   ◄─ ProductListItem.primary_image (desktop large only)
```

**Two coexisting systems (architectural smell):**
1. **URIS** — `app/modules/media/*` (products, collections, categories, avatars, reviews).
2. **Legacy CMS media** — `app/modules/cms/media_service.py` + `cms_media` table (banners, hero, sections, media library). Own boto3 client, own key scheme, no presets, no crop, one 400×400 thumbnail, **no Cache-Control** (§17).

The design doc's own §17 "Phase 3 cutover" (migration `0035`) explicitly deferred CMS ("entangles with `landing_sections.config` JSONB"). So the split is intentional-but-unfinished, not accidental. It remains a real production risk: two code paths, two validation regimes, two cache policies.

---

## 3. Upload Matrix (every entry point discovered)

| # | Surface | File | Preset / path | Cropped? | Responsive variants? | System |
|---|---------|------|---------------|----------|----------------------|--------|
| 1 | Product images (gallery, multi) | `admin/.../products/ProductForm.tsx` | `product` | ✅ | ✅ (desktop consumed only) | URIS |
| 2 | Collection cover | `admin/.../collections/CollectionForm.tsx` | `collection` | ✅ | ✅ | URIS |
| 3 | Category cover | `admin/.../categories/CategoryForm.tsx` | `category` | ✅ | ✅ | URIS |
| 4 | Customer avatar | `Backend/.../profiles/router.py:96` `PATCH /me/avatar` | `avatar` | ❌ (no crop UI; upload only) | ✅ | URIS |
| 5 | Review photos (customer) | `Backend/.../reviews/router.py:88` + `reviews/service.py:287` | `review_photo` (max 5) | ❌ (no crop UI) | ✅ | URIS |
| 6 | CMS media library | `admin/.../cms/ImageUploadField.tsx:35` → `POST /cms/admin/media/upload` | none (raw + thumb) | ❌ | ❌ | **Legacy** |
| 7 | CMS banners | `cms/router.py:101` `create_banner` (URL field) | none | ❌ | ❌ | **Legacy** |

**Defined but NOT wired anywhere (dead presets):** `hero`, `promo_banner`, `gender_section`, `testimonial_avatar`, `instagram_tile`, `footer_logo`, `company_logo`, `seo_og`, `team_member`, `blog_cover`, `blog_inline`. Verified by exhaustive grep for `UniversalImageEditor`, `presetId:`, `uploadImage` across `Frontend_whole/admin` — only `product`, `collection`, `category` appear as editor presets; `avatar`/`review_photo` are backend-driven uploads with no editor. (Finding **HP-1 / MF-1**.)

**Customer-facing uploads exist** (avatar, review photos) — both go through URIS `validate_upload`, so size/mime/min-resolution are enforced. Neither offers a crop UI (acceptable for avatar/review but note `avatar` uses centered default crop only).

---

## 4. Crop Workflow Analysis

**Architecture rules and whether they hold:**

| Rule | Holds? | Evidence |
|------|--------|----------|
| Original never modified | ✅ | `put_original` writes `original.{ext}` once; crop/regenerate re-read it via `get_object_bytes(image.original_key)` (`universal_service.py:234, 313`). `replace` overwrites the same key intentionally. |
| Editor always loads the **original**, never a variant | ⚠️ **Partly** | Collection/Category fetch fresh via `getImage` → `raw.original_url` (`CollectionForm.tsx:177-181`, `CategoryForm.tsx:180-184`). **ProductForm uses `img.original_url` from local state without re-fetch** (`ProductForm.tsx:2679`) — correct URL, but stale-state risk after replace. |
| Only variants render elsewhere | ⚠️ | True in storefront/admin lists, but `CategoryForm`/`CollectionForm` preview thumbnail uses `pickPreviewUrl` (a variant) — fine. |
| Re-edit restores crop/zoom/pan/rotation/focus | ⚠️ **Product loses tablet/mobile** | Collection/Category: `parseStoredCrops` restores **all** breakpoints (`CollectionForm.tsx:44-71`). **Product only restores `desktop`** from `crop_x/y/...` (`ProductForm.tsx:2657-2673`). |
| User can always zoom out past previous crop | ✅ | Editor always seeds from the **original** natural dimensions; `minZoom={1}`, `restrictPosition={false}` (`CropCanvas.tsx:62-69`). |

**The CategoryForm fix mentioned in the brief is complete and correct.** `CategoryForm` now mirrors `CollectionForm` exactly: fetches `getImage` on editor-open, uses `editorOriginalUrl` (never `imageUrl`), passes `initialCrops` from `parseStoredCrops` (`CategoryForm.tsx:176-197, 517-532`). No residual "loads a variant" bug in Category/Collection.

**But the same class of bug survives in ProductForm** in a subtler form (see Critical Bug **CB-2**): product images have **3 breakpoints**, yet re-edit seeds only `desktop`. `useCropGeometry.initialize` with a partial `initialCrops` reseeds every breakpoint to a **centered default**, then overrides only the provided ones (`useCropGeometry.ts:150-172`). On save, `cropImage` sends `geometry.crops` for **all** breakpoints (`mediaApi.ts:87-100`), so the previously-stored tablet/mobile crops are **overwritten with defaults**. This is invisible today only because the storefront reads desktop-only variants (§11) — a latent data-loss bug that becomes visible the moment product mobile variants are consumed.

**Call-site drift between the three forms (verified):**
- Collection ≡ Category: identical structure (fresh `getImage`, all-breakpoint restore, `imageOpInFlight` ref lock, `imageBusy` gate, `onDelete` wired). Good.
- Product: different model (multi-image gallery + crop **queue** `cropQueue`, per-image `busyImageIds` lock, `replaceImage`, `setPrimarySaved`, reorder-absent). It **does not** re-fetch originals via `getImage`, and restores desktop-only. Divergence is partly justified (gallery vs single-cover) but the original-refresh and all-breakpoint-restore omissions are genuine gaps.

**Concurrency guards:** All three forms use a synchronous ref lock (`imageOpInFlight` / `busyImageIdsRef`) to prevent double-submit races, with a `useState` mirror for disabled UI (`CategoryForm.tsx:149`, `ProductForm.tsx:2535-2548`). Well done. No backend row-lock, but the frontend guard + per-breakpoint `replace_variants` scoping (`repository.py:107-123`) keeps this safe in practice.

---

## 5. Preset Analysis — Backend vs TS Mirror

Verified all 16 presets field-by-field between `Backend/app/modules/media/preset_registry.py` and `Frontend_whole/packages/shared-types/src/imagePresets.ts`. **They are in exact sync** (id, label, shape, aspectRatio per breakpoint, safeArea, minResolution, maxZoom, rotation policy, breakpoints, outputVariants incl. dprs & format, storageRules). Spot-checks: `product` maxZoom 5 + free rotation both sides; `hero` desktop `1920/700` both sides; logo `print` variant `format:"png"` both sides; `footer_logo`/`company_logo` allow `image/svg+xml` both sides.

**Sync mechanism is also correct:** `presetClient.fetchPresets` pulls live `GET /admin/media/presets` and falls back to the bundled registry (`presetClient.ts:60-69`); `PresetOut.from_preset` serializes every field (`schemas.py:30-48`). So even if the mirror drifts, the runtime prefers the backend. Good defense.

**Preset design observations:**
- `product` declares **3 identical square breakpoints** (all aspect 1.0, all min 800×800) → generates 3× the variants for zero rendering benefit (§6, §12). This is the root of the CB-2 amplification.
- Rotation is **only enabled for `product`** (`RotationMode.FREE`); every other preset is `NONE`. `apply_geometry` hard-rejects rotation on NONE presets (`crop_engine.py:203`), consistent with `BottomToolbar` hiding the control (`UniversalImageEditor.tsx:397`).
- `footer_logo`/`company_logo` allow SVG but the pipeline **cannot process SVG** (§ CB-3).
- `min_resolution` upload gate uses the **smallest** breakpoint floor (`validation.py:74-87`) — a hero image passing the mobile 390×600 floor can still fail the desktop 1920×700 crop later. Acceptable (documented in code) but worth a clearer upload-time message.

---

## 6. Variant Analysis

**Naming/paths** (`storage.build_variant_key`, `storage.py:68-84`):
`images/{module}/{owner_type}/{owner_id}/{image_id}/{breakpoint}/{variant_name}@{dpr}x.{fmt}` — deterministic, collision-free (image_id is a UUID), human-navigable. Originals: `.../{image_id}/original.{ext}`.

**Generation** (`variant_generator.py`): WebP q85 method 4 for photography; PNG only for the logo `print` variant. DPR handled by multiplying spec width/height (`generate_variants_for_breakpoint:117-125`). `_resize` supports `height=0` (proportional, for CONTAIN logos). Alpha flattened to white for WebP (`_flatten_to_rgb`), preserved for PNG. All correct.

**Does the backend generate what each preset declares?** ✅ `generate_variants_for_breakpoints` iterates `preset.output_variants` × `spec.dprs` × requested breakpoints (`background.py:47-118`). Per-variant upload failures are recorded as `status='failed'` rows rather than aborting the batch (`background.py:87-116`) — good resilience.

**Issues:**
- **Product over-generation** (MP-1): 3 breakpoints × {thumbnail,medium,large} × {1×,2×} = **18 files** per product image; storefront consumes only **desktop** (`catalog/schemas.py:70-72`). ~12 of 18 are never served.
- **`regenerate` re-derives from stored crops for all breakpoints** (`universal_service.py:311-318`) — correct, and it's exported in `mediaApi.ts` but **not called by any UI** (MF-4).
- Variant rows carry `width/height/size_bytes/status/error_message` — good observability.

---

## 7. Storage Analysis (R2)

`storage.py` is the single URIS R2 layer. Strengths:
- One cached boto3 client (`@lru_cache`, `storage.py:37-49`); all calls off-loaded via `asyncio.to_thread` so the event loop isn't blocked on network (but see §12 re: thread-pool saturation).
- **Cache-Control is explicit and correct**: originals `private, max-age=0, must-revalidate`; variants `public, max-age=31536000, immutable` (`storage.py:24-25`). Variants are safe to cache forever because a new crop writes to a *new* image or re-uses the key + `?v=version` cache-bust.
- Folder delete is scoped to the image's own prefix and returns success/failure rather than swallowing (`storage.py:128-160`).

**Issues:**
- **Duplicate-key on `replace`** is intentional (`put_original(image.original_key, ...)`, `universal_service.py:258`) — overwrites bytes at the same key. `original` Cache-Control is `must-revalidate` so the editor won't serve stale bytes; but any external consumer of `original_url` without revalidation could. Low risk given originals aren't public-facing.
- **`original_url` is NOT `?v`-versioned** in `ImageOut` (`schemas.py:149`) though `updated_at`/`version` bump on replace. Combined with `must-revalidate` it's fine, but relies on R2 honoring revalidation. (LP-2)
- **CORS / bucket policy unverifiable from source** — no `cors.json`/wrangler config in repo. The CSS-transform preview (§10) sidesteps the need for permissive CORS on the editor, but any future canvas export would need it. **Explicitly unverifiable.**
- **Second R2 client in `cms/media_service.py:26-34`** duplicates credentials/config and omits Cache-Control entirely (`put_object` calls at `media_service.py:98, 116` have no `CacheControl`). CMS images are therefore not immutably cached. (MP-3)

---

## 8. Database Analysis

**Tables** (`models.py`): `images` (canonical asset) + `image_variants` (1 row/file). Polymorphic via `owner_type`/`owner_id`. `images.metadata_` JSONB stores `preset_id`, `shape`, `focus_point`, `safe_area`, `original_dimensions`, and per-breakpoint `crops{box,zoom,pan,rotation,aspect_ratio}` (`universal_service.py:104-127`). `version` + `updated_at` drive cache-busting. Soft-delete via `deleted_at` + `status='archived'`.

**Constraints/indexes:** `image_variants` has a `UniqueConstraint(image_id, breakpoint, variant_name, dpr)` (`models.py:95-103`) — prevents duplicate variant rows. Variants cascade-delete with the image. `uploaded_by` FK → profiles `ON DELETE SET NULL`.

**Migration history (media-relevant):**
- `0031` add crop columns to legacy `product_images`; `0032` add `large_url`+`updated_at` (cache-bust rationale documented).
- `0034` create `images`/`image_variants` (additive, no legacy touch).
- `0035` Phase-3 cutover: drop `product_images`/`review_images`; add `primary_image_id` to collections/categories/profiles; drop `collections.image_url`/`categories.image_url`/`profiles.avatar_url`.

**Inconsistency found (MP-4):** Migration `0035` adds and backfills `primary_image_id` FK columns on collections/categories/profiles, **but the runtime never maintains them.** `set_primary`/`attach`/`upload` only touch the `images` table (`repository.py:83-102`), and the read path deliberately ignores the denormalized column, resolving via `get_primary_image_ids` against `images` instead (`repository.py:175-203`, comment: *"Those columns … are never written by the generic … flow … so trusting them silently hides a perfectly valid primary image"*). Net: the `primary_image_id` columns are **dead/decaying** after their initial backfill. `CategoryForm`/`CollectionForm` still *seed* local `imageId` from `category?.primary_image_id` (`CategoryForm.tsx:130`) — correct at backfill time, stale if primary ever changes server-side by any path other than the initial one. Recommend dropping the columns or wiring them.

---

## 9. API Analysis (`media/router.py`)

All endpoints are `Depends(require_admin)` **except** the two customer surfaces (avatar in profiles, review photos in reviews).

| Method | Path | Notes |
|--------|------|-------|
| GET | `/admin/media/presets` | Lists presets. |
| GET | `/admin/media/{id}` | Full `ImageOut` — the re-edit source of truth. |
| POST | `/admin/media/{preset}/upload` | `owner_type`/`owner_id` are **query params**, client-controlled. |
| PATCH | `/admin/media/{id}/crop` | Body `CropGeometryIn`. |
| PUT | `/admin/media/{id}/replace` | |
| PATCH | `/admin/media/{id}/attach` / `reorder` / `set-primary` | |
| DELETE | `/admin/media/{id}` | Soft-delete + R2 folder purge. |
| POST | `/admin/media/{id}/regenerate` | Not called by any UI. |

**Issues:**
- **HP-3 — over-broad exception mapping:** the crop endpoint wraps the whole call in `except Exception → 422` (`router.py:148-151`). A genuine 500 (R2 outage, DB error, PIL crash) is reported to the admin as a validation error. Mask hides real failures.
- **MP-5 — `owner_type` is an untyped free-string query param** (`router.py:100`) with no allow-list; an admin can attach an image to any `owner_type`, and `_bust_cache_for` only special-cases `"product"` (`router.py:45-53`), so a typo'd owner_type silently skips cache invalidation.
- **No ETag/`If-None-Match`**; cache-busting is entirely `?v=version` query-string based (works, but not conditional-GET friendly).
- **N+1 risk handled well:** `get_image`/`list_for_owner` use `selectinload(Image.variants)` (`repository.py:24, 37`); bulk list URL resolution is a single joined query (`get_primary_variant_urls`, `repository.py:160-173`). No N+1 in the read path.
- `upload_universal_image` passes `uploaded_by=None` always (`router.py:117`) — loses the audit trail of who uploaded (the admin identity is available via `require_admin` but discarded). (LP-3)

---

## 10. Live Preview System

Verified against actual current code. **It is fully synchronous, no debounce, no server round-trip, no canvas.**
- `CroppedImageView.tsx` renders the crop via a **pure CSS transform** (`translate(%) rotate(deg)` on a wrapper sized as a % of the box), driven entirely by `geometry.box + rotation` derived from state, not measured from the DOM (`CroppedImageView.tsx:52-77`). This correctly avoids `toDataURL` cross-origin tainting on CDN images (documented at :20-33).
- `PreviewFrame.tsx` wraps that in per-`referenceUi` chrome (ProductCard/CollectionTile/HeroFullBleed/etc.), "purely a function of the current in-memory geometry … updates on every drag/zoom/rotate tick" (`PreviewFrame.tsx:31-37`).
- `CropCanvas` feeds `onChange` on every react-easy-crop tick and `onCropComplete` for the box (`CropCanvas.tsx:71-85`); `useCropGeometry.updateBreakpoint` applies it immediately with NaN/Infinity guards (`useCropGeometry.ts:197-214`).

This is the strongest part of the system. One nit: `PreviewFrame` is exported but `RightPreviewPanel` is what the editor actually mounts (`UniversalImageEditor.tsx:338`) — verify no dead duplication (both exist; `RightPreviewPanel` composes `PreviewFrame` per breakpoint — fine).

---

## 11. Responsive Analysis (storefront delivery)

`ResponsiveImage.tsx` builds a proper `srcSet` (sorted by effective pixel width `width*dpr`) + `sizes`, sets `objectPosition` from `focusPoint`, and forwards `loading`/`fetchPriority` (`ResponsiveImage.tsx:32-52`). `ImageWithFallback` **does forward** these via `{...props}` spread (`ImageWithFallback.tsx:46`) — so `srcSet`/`sizes`/`fetchPriority`/`style` reach the real `<img>`. Responsive delivery works **where `ResponsiveImage` is used** (FeaturedCollection, ShopByGender, InstagramSection, account avatar — per grep).

**But the main product grid does not use it (HP-4).** `storefront/.../ProductCard.tsx:37-44` renders a raw `<img src={p.image}>` where `p.image` is `ProductListItem.primary_image` — the single **desktop `large` (1200px)** variant (`catalog/schemas.py:70-81`, `mappers.ts:13`). No `srcSet`, no `sizes`. Mobile users download a 1200px image for a ~180px card. It *is* `loading="lazy"` with intrinsic `width/height` (good for CLS), but this is the highest-traffic image surface and the biggest LCP/bandwidth miss.

**Root cause:** product images only ever expose desktop-breakpoint variants through the API (`from_image` filters `breakpoint=="desktop"`), so even if `ProductCard` wanted a bundle, the tablet/mobile product variants (which *are* generated) aren't surfaced. The generation and the delivery are misaligned.

---

## 12. Performance Analysis

- **Format:** WebP q85 everywhere (photography); no AVIF. Reasonable default; AVIF would cut ~20-30% more but adds encode cost. (LP-4)
- **CB-1 (Critical) — synchronous in-request generation.** `_generate` is deliberately synchronous (`universal_service.py:320-342`, with a long comment defending it). Each variant does a PIL encode + an `asyncio.to_thread` R2 PUT. A product upload = ~18 encodes + 18 PUTs **inside** the POST. `asyncio.to_thread` uses the default `ThreadPoolExecutor` (typically `min(32, cpu+4)` threads shared process-wide); a few concurrent uploads can **saturate the pool and stall unrelated request I/O**. The "Saving…" UX masks latency for the uploader but not the throughput ceiling for everyone else. For 10× traffic this is the first thing that falls over.
- **Duplicate work:** product generates 12 unused variants (§6). Hero/blog `2×` DPR only matters once those are wired.
- **No image dedup:** identical re-uploads create new image_ids/objects. Acceptable.
- **Re-render hygiene (frontend):** `useCropGeometry` uses refs for history/burst timers and `useCallback` throughout; `CropCanvas.initialAreaPixels` is memoized (`CropCanvas.tsx:46-54`). The editor is reasonably tight. The live preview re-renders on every tick by design (cheap CSS transform).
- **LCP:** storefront hero/featured use `ResponsiveImage` (good); product cards don't (bad, §11).

---

## 13. Cache Analysis

**Redis (`core/redis.py`):** circuit-breaker + hard-timeout wrappers, per-worker state. Only **one** URIS-relevant invalidation: `bust_product_list_cache` scans+deletes `products:list:v1:*` (`redis.py:81-104`), called from `_bust_cache_for` **only when `owner_type=="product"`** (`router.py:45-53`). Collections/categories storefront lists are **not** Redis-cached (verified: `collections/service.py`, `categories/service.py` resolve image URLs live, no `setex`), so no stale-image risk there. Profile avatar edits bust `profile_cache_key` (`profiles/router.py:45-46`). Product detail cache: relies on catalog service invalidation (not re-verified here, but list cache is covered).

**React Query cache:**
- Product crop save invalidates `product(id)` **and** `["admin","products"]` (`ProductForm.tsx:2710-2711`) — scoped, no over-invalidation.
- Collection/Category **image** save handlers (`handleImageSave`) update only local state and **do not invalidate any query** (`CategoryForm.tsx:247-256`); the list thumbnail refresh depends on the *form-submit* mutation's `onSuccess` invalidating `admin.categories`/`admin.collections`. If an admin crops then navigates away without saving the form, the list can show a stale thumbnail until next fetch. (LP-5)
- No evidence of editing one product over-invalidating homepage/collections. Invalidation is appropriately narrow.

**CDN/browser:** variants `immutable` 1yr; originals revalidate. Correct, contingent on R2 honoring the headers (unverifiable live).

---

## 14. UX Review (editor)

**Strengths:** canvas-dominant layout with segmented breakpoint control, collapsible preview, sticky bottom toolbar (`UniversalImageEditor.tsx`); undo/redo with burst-coalescing (400ms) history (`useCropGeometry.ts:120-135`); keyboard: Ctrl/Cmd-Z / Shift-Z / Ctrl-Y, arrow-nudge (±10/±40), ± zoom (`UniversalImageEditor.tsx:197-267`); "All breakpoints" sync with copy-from/reset (`SyncControls`, `useCropGeometry.copyAllFrom/resetAllToShared`); Fit/Actual-size; grid + safe-area toggles; `DialogTitle` sr-only for AT (`UniversalImageEditor.tsx:275`).

**Gaps:**
- **MP-6 — no alt-text editing.** `alt_text` is a first-class column and drives `ResponsiveImage` `alt` (`ResponsiveImage.tsx:47`), but the editor never sets it and no form field exists → every URIS image ships `alt=""`. Accessibility + SEO miss.
- **MP-7 — arrow-key nudge fires globally on the dialog** (`onKeyDown` on `DialogContent`, `UniversalImageEditor.tsx:272`); typing in any future text field inside the dialog would pan the crop. No `event.target` guard.
- **LP-6 — no focus trap verification**; relies on the shared `Dialog` (Radix) — likely fine but unverified for the custom fixed-inset layout.
- **Consistency:** Collection ≡ Category editors are pixel-consistent; Product differs (queue-based, `Replace` action, no all-breakpoint restore). Delete confirm uses `window.confirm` in all three (`CategoryForm.tsx:288`, `ProductForm.tsx:1487`) — functional but not on-brand.
- **Loading state:** Category/Collection show a dedicated "Loading original image…" dialog while `getImage` runs (`CategoryForm.tsx:506-516`); Product has none (uses local state, no fetch).

---

## 15. Security Review

- **AuthZ:** admin endpoints gated by `require_admin`; customer endpoints (avatar, review) gated by `get_current_user`. Correct.
- **MP-8 — SVG upload is unsanitized.** `footer_logo`/`company_logo` allow `image/svg+xml` (`preset_registry.py:279, 299`); `validate_upload` **skips all verification for SVG** (`validation.py:49-51`) and stores the raw bytes. An SVG can carry `<script>`. Served from the R2 public domain (separate origin from the app), navigating to it directly executes script in the R2 origin — limited blast radius but still stored-XSS-adjacent. Since logos have no UI, this is latent. Recommend SVG sanitization (svg-hush/DOMPurify server-side) before enabling logo uploads.
- **Client-supplied `content_type` is trusted** for the mime allow-list (`validation.py:43`); PIL `verify()` catches non-images for raster types, but the mime string itself isn't sniffed. Low risk for raster, real risk for the SVG path above.
- **No file-size streaming:** `file.read()` loads the whole upload into memory (`router.py:107`), bounded only by preset `max_file_mb` (5-15MB) checked **after** full read. A malicious large body is read before rejection. With admin-only endpoints this is low; the customer review/avatar endpoints (5MB/8MB presets) are the exposure. (LP-7)
- **`owner_id` not ownership-checked:** an admin uploading with `owner_type=product&owner_id=<any>` can attach to any product. Admin-trust model makes this acceptable. (LP-8)

---

## 16. Cloudflare R2 Review

- Key scheme, immutability, and single-client reuse are correct (§7).
- **Unverifiable from source:** bucket CORS, public-access policy, custom-domain/CDN cache rules, lifecycle rules for orphaned objects. No wrangler/terraform/`cors.json` in repo. **Flagged as unverifiable.**
- **Orphan risk:** soft-delete purges the R2 folder synchronously (`universal_service.delete`), but if `delete_image_folder` returns `False` (logged, not raised — `storage.py:151-158`) the DB row is still soft-deleted → **orphaned R2 objects with no retry/reconciliation** (the code comment at `storage.py:133-135` says callers own retry policy, but `universal_service.delete:306-309` doesn't check the return value). (MP-9)
- CMS media (`media_service.py`) never sets Cache-Control and has no delete-from-R2 on `delete_media` (only DB row) — orphans by design. (Legacy, MP-3.)

---

## 17. React Rendering Review

- Editor components are memo-friendly (`useCallback`/`useMemo`/refs). No obvious wasted renders beyond the intentional per-tick preview.
- `UniversalImageEditor` reuses one instance across open/close and re-syncs image state on `open` change (`UniversalImageEditor.tsx:103-129`) with an `img.onload` cancellation guard — correct handling of stale async loads.
- `ProductForm` is a **3175-line monolith** mixing 8+ sub-components, SEO generation, variant cartesian logic, and image handling. Maintainability risk; not a rendering bug. (MP-10)
- `URL.createObjectURL` is revoked for pending product images (`ProductForm.tsx:2570`) but **not** in the single-cover forms — `handleFileSelected` in the editor creates an object URL (`UniversalImageEditor.tsx:133`) that is **never revoked** (minor leak per upload session). (LP-9)

---

## 18. React Query Cache Review

Covered in §13. Summary: invalidation is correctly **narrow** (no homepage-over-invalidation). The gap is the opposite — Collection/Category image edits **under-invalidate** (local-state only until form submit). Query keys are centralized in `queryKeys` (`admin.product`, `admin.categories`, etc.) — good hygiene.

---

## 19. Redis Cache Review

Covered in §13. `redis.py` is production-grade (circuit breaker, timeouts, fire-and-forget). The only URIS coupling (`bust_product_list_cache`) is correct but **product-only**; if any other owner_type ever feeds a cached storefront list, invalidation must be extended. `RedisCache.delete_pattern` uses `KEYS` (blocking) vs the safer `scan_iter` used by `bust_product_list_cache` — prefer the latter everywhere. (LP-10)

---

## 20. Component Inventory (frontend URIS)

| Component | Purpose |
|-----------|---------|
| `UniversalImageEditor.tsx` | Dialog shell; owns file input, keyboard, save intents, orchestrates canvas+preview+toolbar. |
| `CropCanvas.tsx` | react-easy-crop wrapper (pan/zoom/rotate) + shape/safe-area overlays + mini-navigator. |
| `useCropGeometry.ts` | Per-breakpoint crop state, undo/redo history, "All" sync framing, link/unlink logic. |
| `CroppedImageView.tsx` | Pure-CSS-transform live crop renderer (no canvas). |
| `PreviewFrame.tsx` | Maps `referenceUi` → chrome component; wraps one breakpoint's preview. |
| `RightPreviewPanel.tsx` | Mounts `PreviewFrame` per breakpoint in the side panel. |
| `previewChrome/*` | 8 UI replicas (ProductCard, CollectionTile, CategoryTile, GenderCircle, HeroFullBleed, LogoHeader, LogoFooter, Generic). |
| `TopBar / BottomToolbar / BreakpointTabs / SyncControls` | Controls. |
| `ShapeMaskOverlay / SafeAreaOverlay / MiniNavigator / ImageInfoPopover` | Canvas overlays/HUD. |
| `cropMath.ts` | Clamp/default/rotatedBounds/computeSyncedCropBox/focusPointFromBox (mirrors backend `crop_engine`). |
| `mediaApi.ts` | REST client + `toImageBundle`. |
| `presetClient.ts` | Live preset fetch + bundled fallback. |
| `ResponsiveImage.tsx` | srcset/sizes renderer (the sanctioned render path). |

---

## 21. Image Flow Diagram

```
UPLOAD
  file ─► validate_upload(size, mime, min-res) ─► PIL probe (w,h)
       ─► build_original_key ─► put_original(original.ext, must-revalidate)
       ─► create_image(status=pending, metadata=default centered crops)
       ─► _generate(ALL breakpoints)  ── SYNCHRONOUS, IN-REQUEST ──►
             for bp: apply_geometry(original) ─► generate_variants (WebP×dpr)
                     ─► put_variant(immutable) ─► replace_variants(bp)
             ─► set image.status = ready|failed
       ─► ImageOut (original_url + variants[?v=version])

RE-CROP
  PATCH crop {crops, focus_point}
       ─► parse stored crops ─► merge with payload
       ─► diff → changed_breakpoints (tolerance compare)
       ─► update_metadata (version++)
       ─► if changed: get_object_bytes(original) ─► _generate(changed only)
       ─► bust_product_list_cache (product only)
```

---

## 22. Sequence Diagram — Upload

```
Admin        Editor            Form              media API           Service          R2      DB
 │  pick file  │                │                   │                  │              │       │
 │────────────►│ createObjectURL│                   │                  │              │       │
 │  crop/zoom  │ (live preview) │                   │                  │              │       │
 │────────────►│                │                   │                  │              │       │
 │  Save       │──onSave(file,geom)──►              │                  │              │       │
 │             │                │ uploadImage()      │                  │              │       │
 │             │                │───────────────────►│ upload()         │              │       │
 │             │                │                    │ validate         │              │       │
 │             │                │                    │ put_original ───────────────────►       │
 │             │                │                    │ create_image ─────────────────────────► │
 │             │                │                    │ _generate (18 files, blocking)          │
 │             │                │                    │   put_variant ×N ───────────────►       │
 │             │                │                    │   replace_variants ───────────────────► │
 │             │                │◄──ImageOut─────────│ status=ready     │              │       │
 │             │                │ cropImage(geom) [redundant on fresh]  │              │       │
 │             │                │ setPrimaryImage()  │                  │              │       │
 │  toast ◄────│◄───────────────│                    │                  │              │       │
```
Note the double server hit on fresh upload: `upload()` already generates from the default centered crop, then the form immediately calls `cropImage()` with the editor geometry (`CategoryForm.tsx:234-241`), triggering a **second** generation pass. For a single-cover image the first pass is wasted work.

## 23. Sequence Diagram — Re-edit Crop

```
Admin     Form               media API         Service            R2         DB
 │ Edit crop │                  │                 │                │          │
 │──────────►│ getImage(id) ────►│ get_universal_image             │          │
 │           │                  │ ImageOut(original_url, crops) ◄──── selectinload variants
 │           │◄─original+crops───│                 │                │          │
 │  (editor seeds from original + parseStoredCrops)                 │          │
 │ adjust    │                  │                 │                │          │
 │ Save      │ cropImage(geom) ─►│ crop()          │                │          │
 │           │                  │ diff changed bps │                │          │
 │           │                  │ get_object_bytes(original) ◄──────│          │
 │           │                  │ _generate(changed) ─ put_variant ─►          │
 │           │                  │ update_metadata (v++) ─────────────────────► │
 │           │◄──ImageOut────────│ bust product cache               │          │
```
Collection/Category follow this exactly. **Product skips the `getImage` step** (uses local `original_url`) and seeds desktop-only (CB-2).

---

## 24. Complete File Inventory

**Backend — `app/modules/media/`**
| File | Purpose |
|------|---------|
| `models.py` | `Image` + `ImageVariant` ORM (polymorphic, JSONB metadata, soft-delete). |
| `preset_registry.py` | 16-preset source of truth (shape/aspect/min-res/zoom/rotation/variants/storage). |
| `schemas.py` | `PresetOut`, `CropGeometryIn`, `ImageOut`, `ImageVariantOut` (+ `?v=` cache-bust). |
| `validation.py` | Size/mime/min-res gate; SVG bypass; ext resolution. |
| `crop_engine.py` | Pure geometry: rotate/clamp/crop/shape-mask; `apply_geometry` pipeline. |
| `variant_generator.py` | Crop→WebP/PNG encode per variant×dpr; alpha flatten. |
| `background.py` | Orchestrates crop→generate→put→persist per breakpoint; per-variant failure isolation; live-check before final status. |
| `storage.py` | R2 client, key builders, put/get/delete, Cache-Control policy. |
| `universal_service.py` | Upload/crop/replace/attach/reorder/set-primary/delete/regenerate orchestration; crop diffing. |
| `repository.py` | CRUD + bulk primary-URL/id resolution (no N+1). |
| `router.py` | 9 admin endpoints + cache-bust hook. |

**Backend — other media surfaces**
| File | Purpose |
|------|---------|
| `catalog/schemas.py` | `ProductImageResponse.from_image` (desktop-only variant projection, crop columns, cache-bust). |
| `catalog/service.py`,`repository.py` | Product image serving + `primary_image` for lists. |
| `categories/service.py`,`collections/service.py` | Resolve `image_url` via `get_primary_variant_urls`. |
| `profiles/router.py` | `PATCH /me/avatar` → URIS `avatar` preset. |
| `reviews/router.py`,`service.py` | Review photo upload → URIS `review_photo` (max 5). |
| `cms/media_service.py` | **Legacy** parallel R2 upload (raw + 400px thumb, no presets/crop/cache-control). |
| `cms/router.py` | CMS media library + banner endpoints (legacy path). |
| `core/redis.py` | Cache wrappers + `bust_product_list_cache`. |
| `alembic/versions/0031,0032,0034,0035*` | Crop-metadata → URIS schema → Phase-3 cutover. |

**Frontend — `packages/shared-media` & `shared-types`**: see §20 + `imagePresets.ts` (TS preset mirror), `media.ts` (types).
**Frontend — call sites:** `admin/.../{products,collections,categories}/*Form.tsx`; `storefront/.../site/{ProductCard,FeaturedCollection,ShopByGender,InstagramSection}.tsx`, `account.index.tsx`, `lib/api/mappers.ts`.

---

## 25. Critical Bugs

**CB-1 — Variant generation is fully synchronous in-request (scalability ceiling).**
- Severity: **Critical** (throughput) · Root cause: `_generate` intentionally synchronous (`universal_service.py:320-342`) → 18 encodes+PUTs per product image inside the POST, on the shared `asyncio.to_thread` pool.
- Affected: `universal_service.py`, `background.py`, `storage.py`; every upload/crop/replace/regenerate; all mutating media APIs.
- Impact: a handful of concurrent uploads saturate the default thread pool and stall unrelated request I/O; blocks 10× traffic.
- Recommended architecture: enqueue generation to a task queue (Celery/RQ/arq) or a dedicated bounded `ProcessPoolExecutor`; return `status=pending` immediately and let the client poll `GET /admin/media/{id}` (the endpoint already exists and the UI already tolerates pending variants). Keep the *default centered* variants synchronous-only if a first paint is needed; do the full matrix async.
- Recommended fix (interim): move generation to `BackgroundTasks` **with** the existing status/poll UX, and cap concurrency with a semaphore around `to_thread`.
- Future risk: hard failure mode under launch/marketing traffic spikes.

**CB-2 — Product re-crop silently resets tablet/mobile framing (data loss).**
- Severity: **Critical** (correctness/data-loss, currently masked) · Root cause: `ProductForm` seeds `initialCrops` with **desktop only** (`ProductForm.tsx:2657-2673`); `useCropGeometry.initialize` reseeds all breakpoints to centered defaults then overrides only provided ones (`useCropGeometry.ts:150-172`); `cropImage` PATCHes **all** breakpoints (`mediaApi.ts:87-100`), overwriting stored tablet/mobile crops with defaults.
- Affected: `ProductForm.tsx`, `useCropGeometry.ts`, product `images.metadata_.crops`.
- Impact: every "Edit crop" on a product image discards its non-desktop crops. Invisible only because the storefront reads desktop-only variants (HP-4) — becomes visible data loss the moment product mobile variants are consumed.
- Recommended fix: fetch fresh state via `getImage` (like Collection/Category) and build `initialCrops` from **all** breakpoints via a `parseStoredCrops` equivalent; or, on the server, only regenerate breakpoints actually present in the payload.
- Future risk: permanent loss of admin crop work across breakpoints.

**CB-3 — SVG logo upload crashes variant generation.**
- Severity: **Critical for the logo presets** (but latent — no UI yet) · Root cause: `footer_logo`/`company_logo` allow `image/svg+xml`; `validate_upload` skips SVG dimension checks and stores it (`validation.py:49-51`); on generation `PILImage.open(svg_bytes)` raises `UnidentifiedImageError` **outside** the per-variant try/except (`background.py:52`), 500-ing the request; `upload()` sets width/height=0 and seeds a 1×1 crop (`universal_service.py:158-170`).
- Affected: `validation.py`, `background.py`, `universal_service.py`, logo presets.
- Impact: any SVG logo upload fails with a 500 and leaves a `pending` image row.
- Recommended fix: either drop SVG from logo `allowed_mime`, or special-case SVG (store as-is, skip raster generation, expose original as the variant) + sanitize (§ MP-8).

---

## 26. High-Priority Improvements

- **HP-1 — 11 of 16 presets are dead.** Wire hero/promo_banner/gender_section/instagram_tile/testimonial_avatar/logos/seo_og/team/blog to the editor, or remove them from the registry until built. Current state advertises capability that doesn't exist. (`preset_registry.py` vs admin grep.)
- **HP-2 — Retire or converge the legacy CMS media pipeline** (`cms/media_service.py`). Two R2 clients, two validation regimes, no Cache-Control on CMS objects, no crop/responsive. Migrate CMS to URIS presets (hero/promo_banner already exist).
- **HP-3 — Stop mapping all crop errors to 422** (`router.py:148-151`). Catch specific `CropGeometryError`/`ImageValidationError` → 422; let everything else 500 so real outages are visible/alertable.
- **HP-4 — Product grid must use `ResponsiveImage`.** Surface product tablet/mobile variants in the API and render an `ImageBundle` in `storefront/.../ProductCard.tsx`. Biggest LCP/bandwidth win.
- **HP-5 — Eliminate the double-generation on fresh upload** (`upload()` generates, then form calls `cropImage()` again). Either upload with the chosen geometry in one call, or skip the initial generation when the client will immediately crop.
- **HP-6 — Restore all breakpoints on product re-edit** (part of CB-2 fix) and make ProductForm fetch the original via `getImage` for parity with the other two forms.
- **HP-7 — Reconcile R2-delete failures** (`universal_service.delete` ignores `delete_image_folder`'s `False` return, `storage.py:151-158`) — track/retry orphans or use an R2 lifecycle rule.

## 27. Medium-Priority Improvements

- **MP-1** Product generates 12 unused variants; either collapse product to one breakpoint or consume the others.
- **MP-3** CMS media has no Cache-Control and no R2 cleanup on delete.
- **MP-4** Dead `primary_image_id` columns (never maintained) — drop or wire.
- **MP-5** `owner_type` free-string query param; add an allow-list and extend `_bust_cache_for` accordingly.
- **MP-6** No alt-text editing anywhere → `alt=""` on all URIS images (a11y/SEO).
- **MP-7** Dialog-level arrow-key handler will hijack future in-dialog inputs; guard on `event.target`.
- **MP-8** Sanitize SVG before enabling logo uploads (stored-XSS-adjacent).
- **MP-9** R2 orphan reconciliation (see HP-7).
- **MP-10** `ProductForm.tsx` (3175 lines) — extract image handling into a hook/module.
- **MP-11** Collection/Category image edits under-invalidate React Query (local-state-only until form submit).
- **MP-12** `focus_point` is stored/rendered (`ResponsiveImage` objectPosition) but the editor has no explicit focus-point control — it's only inferred from the box center; product cards (raw img) ignore it entirely.

## 28. Low-Priority Improvements

- **LP-2** `?v=` originals for extra safety.  **LP-3** capture `uploaded_by` for admin uploads.  **LP-4** consider AVIF.  **LP-5** invalidate list queries on image save.  **LP-6** verify dialog focus trap.  **LP-7** stream/limit upload body before full read on customer endpoints.  **LP-8** ownership checks on attach (admin-trust makes optional).  **LP-9** revoke object URLs in single-cover editors.  **LP-10** replace `RedisCache.delete_pattern` `KEYS` with `scan_iter`.

## 29. Missing Features

- **MF-1** Upload surfaces for 11 presets (hero, banners, gender, instagram, testimonials, logos, SEO/OG, team, blog).
- **MF-2** Crop UI for avatar and review photos (currently upload-only, centered default).
- **MF-3** Gallery reorder UI (`reorderImages` API exists, no drag-reorder in ProductForm).
- **MF-4** "Regenerate variants" admin action (`regenerateImage` API exists, unused).
- **MF-5** Alt-text management.
- **MF-6** Async generation status/progress UI (needed with CB-1 fix).
- **MF-7** Bulk upload/crop across products.
- **MF-8** Orphaned-object cleanup job / R2 lifecycle policy.

---

## 30. Production-Readiness Score

| Category | Score /10 | Rationale |
|----------|-----------|-----------|
| Crop engine & geometry correctness | 9 | Backend/frontend math mirrored; original-preserving; zoom-out unrestricted; NaN guards. |
| Live preview | 9.5 | Pure-CSS, no debounce, no canvas taint. Best-in-class here. |
| Preset system & sync | 9 | 16 presets exact-sync + live fetch fallback. |
| DB schema & migrations | 8 | Clean polymorphic model; only blemish is dead `primary_image_id` columns. |
| Storage/R2 layer | 7.5 | Correct keys + Cache-Control; orphan-on-delete gap; CORS unverifiable; 2nd CMS client. |
| API design | 7 | selectinload (no N+1), good cache-bust; over-broad 422 mapping; free-string owner_type. |
| Variant generation | 6 | Correct output + failure isolation, but synchronous-in-request (CB-1) + product over-generation. |
| Frontend call-site consistency | 6 | Collection≡Category solid; Product diverges + CB-2 data loss. |
| Responsive delivery (storefront) | 5 | `ResponsiveImage` is good but product grid bypasses it (HP-4). |
| Completeness / "universal" claim | 3 | Only 5/16 presets wired; legacy CMS pipeline still primary for hero/banners. |
| Security | 6.5 | Sound authZ; SVG unsanitized; client mime trusted; unbounded read on customer endpoints. |
| UX / a11y | 6.5 | Strong editor UX; no alt-text; minor keyboard/focus gaps. |

**Weighted overall: 6.1 / 10.**

**Bottom line:** Ship-ready for **products, collections, categories, avatars, reviews** after fixing **CB-1** (async generation), **CB-2** (product re-crop data loss), **HP-3** (error mapping), and **HP-4** (product responsive delivery). It is **not** yet the "universal" system its naming and registry imply — 11 presets and the entire CMS/hero/banner surface remain unbuilt or on the legacy path. Treat "universal" as aspirational until HP-1/HP-2 land.

---
*All findings verified against source at the paths/lines cited. Items marked "unverifiable from source" (R2 bucket CORS/lifecycle, live CDN behavior, running performance) require infra access or load testing to confirm.*
