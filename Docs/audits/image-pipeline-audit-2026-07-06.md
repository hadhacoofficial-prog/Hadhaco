# Hadha.co Product Image Pipeline Audit — Phase 1 (Read-Only)

**Date:** 2026-07-06
**Scope:** Full image lifecycle — upload → storage → CDN → database → backend API → frontend render — across `Backend/app/modules/media`, `Backend/app/modules/catalog`, `Backend/app/core/config.py`, `deploy/nginx/`, and `Frontend_whole/{storefront,admin,packages}`.
**Method:** Static code audit (two independent passes, cross-checked) + live verification against the running dev stack (FastAPI on :8000, storefront Vite dev server on :8080, real Cloudflare R2/`cdn.hadha.co` CDN — not mocked). No code was modified.

---

## Executive summary

**The blurry-thumbnail complaint has a confirmed, single, mechanical root cause:** the backend deliberately serves a 200×200px thumbnail for every product-listing context (grid cards, wishlist, cart, checkout), and the frontend stretches that 200px image across a CSS box that measures 289–325px wide in the live grid (confirmed by direct DOM measurement) — before even accounting for device pixel ratio. The Product Detail Page, by contrast, uses the 600×600 `medium` variant for its ~564px display box, which is almost a 1:1 match. This is not a CDN or compression bug — it is one code comment away from being intentional:

> `Backend/app/modules/catalog/service.py:114-115` — *"Product listing (cards, wishlist, cart, checkout) always uses the generated thumbnail, never the full-resolution original."*

The image-processing pipeline itself (Pillow → WebP, three fixed sizes, Cloudflare R2 storage) is well-built. The gap is entirely in **which pre-generated size gets selected for which context**, combined with **zero responsive-image mechanism** (`srcset`/`sizes`/DPR) to adapt to different screen densities or grid breakpoints.

| Area | Verdict |
|---|---|
| Upload/compression pipeline | Solid — Pillow, WebP q85, 3 fixed sizes + original, admin-only, size/type validated |
| Storage (Cloudflare R2) | Solid — clean key layout, in-place overwrite with correct cache-busting |
| CDN delivery | Functional but no on-the-fly transforms; cache headers come from R2/Cloudflare defaults, not app config |
| DB schema | Adequate but missing `width`/`height`/`file_size`; `alt_text` write-only (never populated) |
| Backend image selection | **Root cause lives here** — listing forces `thumbnail_url` (200px) unconditionally |
| Frontend responsive images | Absent — no `srcset`/`sizes`/DPR anywhere in the monorepo |
| Frontend component consistency | Storefront never uses the shared `ImageWithFallback` component; admin's preview copy of `ProductCard` visually diverges from the real one |

---

## 1. Image Upload Pipeline

**Endpoints** (`Backend/app/modules/media/router.py`), all `Depends(require_admin)`:
- `POST /admin/products/{product_id}/images` (62-111), `DELETE .../images/{image_id}` (114-134), `PATCH .../primary` (137-154), `PATCH .../crop` (157-208), `PUT .../replace` (211-261).
- Parallel single-cover-image endpoints for collections (269-338) and categories (346-415).
- A **second, independent** upload pipeline exists for CMS content media: `Backend/app/modules/cms/media_service.py` (`CmsMediaService`) — duplicates the Pillow/R2 logic with its own constants, backed by a separate `cms_media` table that (unlike `ProductImage`) *does* store `width`/`height`/`file_size`.

**Validation** (`media/router.py:26-27,48-54`):
```python
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
```
Based purely on the client-supplied `Content-Type` header — no magic-byte/content sniffing. The original file's stored `ContentType` is derived from the filename extension (`.rsplit(".", 1)[-1]`, defaulting to `jpg`), not from the validated MIME type. nginx separately caps `/api/v1/media/` at `client_max_body_size 20m` (looser than the 10 MB app check, so it never actually triggers).

**Compression/resize** (`media/service.py`) — YES, and this part is well engineered:
- `Pillow==12.2.0` (`requirements.txt:45`), `boto3==1.35.93` for R2.
- `_normalize_image` (33-51): flattens RGBA/P to RGB on a white canvas, pads to square (~12.5%/side) — never crops or stretches the source.
- `_resize_to_webp` (98-114): `Image.LANCZOS` resize into a fixed box, re-encoded as WebP `quality=85, method=4`.
- Three fixed variants generated at upload: **thumbnail 200×200, medium 600×600, large 1200×1200** (`_SIZES`, 13-17) — always WebP.
- The **original** upload bytes are stored completely untouched (no resize, no re-encode, no compression) alongside the three derived variants.
- Crop (`apply_crop_to_product_image`, 243-275) and replace (`replace_product_image`, 277-296) both re-derive thumbnail/medium/large from the untouched original — never re-touching it.

**EXIF metadata** — not explicitly stripped anywhere (zero references to `exif`/`EXIF` in the codebase). The three derived WebP variants lose EXIF as an *incidental* side effect of Pillow re-encoding, but the **original** file — which is stored at a public, unauthenticated R2 URL — retains any EXIF (including GPS) the source file had.

**Multiple sizes at upload** — confirmed: original + thumbnail + medium + large, every time.

---

## 2. Storage Layer

**Provider:** Cloudflare R2 via `boto3`'s S3-compatible client (`media/service.py:22-30`) — **not** Supabase Storage, **not** local disk. Config: `CLOUDFLARE_ACCOUNT_ID/R2_BUCKET/R2_ACCESS_KEY/R2_SECRET_KEY/R2_PUBLIC_URL/R2_ENDPOINT` (`core/config.py:111-117`), aliased as `R2_*` (170-187).

**Folder structure** (`media/service.py:138-153`):
```
products/{product_id}/{image_uuid}/original.{ext}
products/{product_id}/{image_uuid}/thumbnail.webp
products/{product_id}/{image_uuid}/medium.webp
products/{product_id}/{image_uuid}/large.webp

collections/{collection_id}/{image_uuid}/{original|thumbnail|medium|large}...
categories/{category_id}/{image_uuid}/{original|thumbnail|medium|large}...
avatars/{user_id}/avatar.webp   ← deterministic key, no uuid
```
Confirmed live via a real product's R2 keys during this audit:
`https://cdn.hadha.co/products/1a3e0b0e-449d-4622-b08c-086d9eda29f8/6f9475c4-60fa-47b6-a3eb-fc3e6f7e582b/{thumbnail,medium,large}.webp`

**Versioning:** Product images: each new upload gets a fresh `image_uuid` (never overwritten); crop/replace overwrite the *same* key in place (by design, so re-cropping starts from the same stable original). Collections/categories: old image folder is explicitly deleted before the new one uploads — no history retained. Avatars: deterministic key, silent overwrite every time. **No versioning/history of prior image bytes exists anywhere** — R2 holds only current state.

**Originals preserved:** Yes, for products (crop/replace never touch `original.{ext}`). For collections/categories, the entire folder (including any "original") is deleted on replacement.

---

## 3. CDN / Delivery Pipeline

**CDN:** Cloudflare, fronting the R2 bucket at the custom domain `cdn.hadha.co` (confirmed via nginx CSP: `img-src 'self' data: https://cdn.hadha.co blob:` in `deploy/nginx/conf.d/hadha.conf:47` and `admin.hadha.co.conf:33`, and directly via live fetches during this audit).

**Transformation:** **No on-the-fly transform layer.** No `?width=`, `?quality=`, Supabase image-render, imgproxy, or Cloudflare Images (`/cdn-cgi/image/`) anywhere. All resizing is pre-baked at upload/crop time into the three fixed WebP sizes; the frontend just picks which pre-generated URL to request.

**Cache headers — live-measured** (this audit fetched the real CDN URLs directly, superseding the "not found in app config" observation from static analysis — the header exists, it's just not something this repo configures):
```
Cache-Control: max-age=14400        (4 hours — R2/Cloudflare's bucket default, not set in app code)
Content-Type: image/webp
Content-Encoding: (none)
```
No `put_object` call anywhere in `media/service.py` passes a `CacheControl` parameter — the 4-hour value is R2/Cloudflare's own default for a public bucket, not a deliberate choice recorded in this codebase. nginx's `expires 1y; Cache-Control: public, immutable` only applies to the storefront/admin's *own* static JS/CSS bundles, not to `cdn.hadha.co` (a separate origin entirely, never proxied through this nginx).

**Signed URLs:** None — all image URLs are plain public R2 URLs. A presigned-upload helper (`get_presigned_upload_url`, `media/service.py:376-389`) exists but has zero call sites — dead code.

**Sample URLs captured live during this audit** (real product: "92.5 Sterling Silver Evil Eye Beaded Bracelet"):

| Context | URL pattern used | Actual resolution | Actual size |
|---|---|---|---|
| Product Listing / Wishlist / Cart / Checkout | `.../{image_uuid}/thumbnail.webp?v=<ts>` | 200×200 | 7.7 KB |
| Product Detail (gallery/main) | `.../{image_uuid}/medium.webp?v=<ts>` | 600×600 | 48.6 KB |
| Product Detail (hover/pinch zoom only) | `.../{image_uuid}/large.webp?v=<ts>` | 1018×1018 | 100.6 KB |

The `?v=<unix_timestamp>` suffix (`cache_busted_url`, `catalog/schemas.py:17-33`) is a cache-busting version tag keyed off the row's `updated_at` — it exists because crop/replace overwrite the same R2 key in place, so without it the CDN/browser would keep serving stale bytes after an edit (confirmed by the migration that added it, `alembic/versions/0032_product_image_large_url_and_version.py`).

---

## 4. Database

**`product_images` table** (`Backend/app/modules/catalog/models.py:273-314`, one row per image, FK to `products.id ON DELETE CASCADE`):

```python
id, product_id,
url, thumbnail_url, medium_url, large_url,   # 4 separate URL columns
alt_text,               # always NULL — see below
is_primary, sort_order,
created_at, updated_at, # updated_at drives the ?v= cache-bust
crop_x, crop_y, crop_width, crop_height, crop_zoom, crop_rotation
```
Base schema originates from raw SQL (`supabase/sql/002_catalog.sql:163-184`), with `large_url`/`updated_at` added later via a real Alembic migration (`0031`/`0032`).

**Missing:** no `width`, `height`, or `file_size` columns — pixel dimensions and byte size of any stored image are not persisted anywhere (the separate CMS media table *does* track these, so the omission on `ProductImage` is an inconsistency between the two parallel systems, not a technical limitation).

**`alt_text` is dead-write:** every upload sets it to `None` (`media/router.py:97`); no endpoint anywhere updates it afterward. It exists in the schema and the API response but can never be populated through any code path.

**Collections/categories:** single `image_url` column each (Text), no per-size variants persisted at the DB level — only the "large" WebP URL is kept.

**Product deletion:** cascades to delete `ProductImage` rows at the DB level, but nothing calls `MediaService.delete_entity_folder` for products on delete — the R2 objects for a deleted product's images are never cleaned up (collections/categories, by contrast, do explicitly purge their R2 folder on replace/delete).

---

## 5. Backend Image APIs

**`ProductImageResponse`** (`catalog/schemas.py:36-61`) — returned for the full product-detail image list — carries all four URLs plus crop metadata, and a `model_validator` (`_bust_cache`) appends the `?v=` cache-bust param to all four URLs on every serialization. This is the **only** dynamic URL transform anywhere in the API layer — no CDN base-URL switching, no resize-param injection.

**The root cause, in the service layer** (`Backend/app/modules/catalog/service.py:106-129`):
```python
# Product listing (cards, wishlist, cart, checkout) always uses the
# generated thumbnail, never the full-resolution original.
primary_img = cache_busted_url(
    primary.thumbnail_url or primary.url, primary.updated_at
) if primary else None
```
`ProductListItem.primary_image`/`secondary_image` (flat strings, not full image objects) are computed here and **unconditionally** resolve to `thumbnail_url` (200×200) for every list-type response — this is the single code path that determines the image resolution for the Product Listing grid, Wishlist, Cart, and Checkout order summary alike.

**Middleware:** none specific to images. `rate_limit_upload` (`app/middleware/rate_limit.py:97-106`) is defined but never wired to any route (`Depends(rate_limit_upload)` appears nowhere) — the actual protection for the upload endpoint is nginx's `limit_req zone=upload burst=5 nodelay` (`deploy/nginx/conf.d/api.hadha.co.conf:43`), not the app-level dependency.

---

## 6. Frontend Image Flow (page by page)

Confirmed by static analysis + live network capture. Framework: **Vite + React 19 SPA on TanStack Router/Start** (not Next.js — no `next/image` equivalent exists anywhere).

| Page | Renderer | Image field used |
|---|---|---|
| Homepage — Hero/Featured/Promo/Instagram sections | raw `<img>` per-component (`Hero.tsx`, `FeaturedCollection.tsx`, etc.) | CMS `*_image_url` fields, local asset fallback |
| Category Listing (`/collections/$slug`) banner | raw `<img fetchPriority="high">` (`collections.$slug.tsx:104-110`) | `CollectionDto.image_url` |
| Product Listing / Search grid | `ProductCard.tsx` → raw `<img>` (front+back 3D-flip faces) | `ProductListItem.primary_image` / `secondary_image` (= **thumbnail_url**, 200×200) |
| Product Detail — gallery/main viewer | inline `ProductImageViewer` in `products.$slug.tsx:934-1278` | `gallery[i]` = **medium_url** (600×600); `galleryLarge[i]` = **large_url** (1200×1200, zoom only) |
| Cart drawer / Cart page / Checkout summary | raw `<img>` (no shared component) | `line.snapshot.image` (captured at add-to-cart time from `product.image` = thumbnail) |
| Wishlist | raw `<img>` | `item.image` (thumbnail) |
| Recently Viewed | **not rendered at all** — hardcoded to `[]` in `products.$slug.tsx:198`; the persisted-IDs store (`stores/recentlyViewed.ts`) is never hydrated into full products |
| Related Products | not separately identified as a distinct section in the current storefront routes reviewed |

Live-measured confirmation (desktop viewport 1440×900, `Evil Eye Beaded Bracelet`):
- Listing grid card: rendered **289–325 CSS px** square, source = **200×200** thumbnail → upscaled.
- Product Detail main image: rendered **564 CSS px** square, source = **600×600** medium → near-exact match, sharp.

---

## 7. Image Component Audit

**`ImageWithFallback`** (`Frontend_whole/packages/shared-ui/src/common/ImageWithFallback.tsx`) — the *only* reusable image component in the monorepo:
- Props: `src, alt, className, imgClassName, fallback, loading="lazy"` + passthrough.
- `decoding="async"`, skeleton shown while loading, `onError` swaps to a fallback node or a default `ImageOff` icon, opacity fade-in on load.
- **No `srcset`/`sizes` support at all.**
- **Used only in the admin panel** (13 files, all `admin/src/routes/admin.*`). **The storefront never imports it** — every storefront image is a hand-rolled `<img>` with no shared skeleton/error-fallback behavior, and behavior is inconsistent across pages (`loading="lazy"` present on most product-grid/search images, missing on cart-drawer, checkout-summary, and wishlist images).
- Admin additionally maintains its **own separately-coded copy** of `ProductCard` (`admin/src/components/site/ProductCard.tsx`) for CMS live-preview purposes, which uses `object-cover` + `scale-110` on hover — a visually different treatment from the real storefront card (`object-contain` + 3D flip). These two are not shared via `packages/shared-ui` and have drifted.

---

## 8. CSS Rendering Audit

**Product Listing card** (`storefront/src/components/site/ProductCard.tsx:34-62`):
- Container: `relative aspect-square bg-white [perspective:900px]` — sized by the CSS grid parent (`grid-cols-2 md:grid-cols-3 lg:grid-cols-4`), no `overflow-hidden` on the outer element.
- `<img>`: `w-full h-full object-contain`, explicit (but functionally inert) `width={800} height={800}` attributes — the actual `src` served is the 200×200 thumbnail, so these attributes don't reflect delivered resolution.
- `object-fit: contain` (not `cover`); `object-position`: default; no `image-rendering`, no `filter`; hover effect is a 3D `rotateY(180deg)` flip of the *container*, not a scale/blur on the image itself.

**Product Detail main viewer** (`products.$slug.tsx`, `ProductImageViewer`, 934-1278):
- Container: `relative aspect-square bg-white overflow-hidden ... select-none`, with an inline `touchAction` style (the recent touch-fix commit).
- `<img>`: `absolute inset-0 w-full h-full object-contain pointer-events-none`, inline `transform: scale(${effectiveDesktopScale})` (base 2.5× on hover, cursor-following `transformOrigin`), `will-change: transform`, and an explicit `imageRendering: "auto"` — i.e., set but effectively a no-op default (worth flagging given the audit's sharpness focus: someone may have intended a sharper mode here and it silently does nothing).
- No `filter`, no `border-radius`, no CSS `scale-*` utility classes (the zoom is entirely inline-style-driven, not Tailwind).

---

## 9. Responsive Images

**Not implemented anywhere in the monorepo.** Zero matches for `srcSet`, `sizes=`, or `devicePixelRatio` across storefront, admin, and all shared packages. The only concession to "different sizes for different purposes" is the manual, server-curated two/three-tier system described in Sections 5–6 (thumbnail for lists, medium for detail display, large for zoom) — chosen once at the data-mapping layer (`storefront/src/lib/api/mappers.ts`), never negotiated by the browser via `srcset`/`sizes` or DPR. The `thumbnail_url` field is fetched by the API but **never read** in the product-detail mapper (only `medium_url`/`large_url`/`url` are consumed there).

---

## 10. Performance Optimization

- **Native `loading="lazy"`**: used widely but inconsistently — present on most homepage sections, product grid, and search; **missing** on cart drawer, checkout order-summary thumbnails, and wishlist grid images.
- **`fetchPriority`**: used in exactly two places (`Hero.tsx` first slide, `collections.$slug.tsx` banner) — not used on the Product Detail Page's main image, which is a strong LCP candidate on that route.
- **IntersectionObserver-based lazy loading**: not found — relies solely on the native attribute.
- **`<link rel="preload">` / router prefetch**: not found anywhere.
- **Targeted JS preload**: one instance — `products.$slug.tsx:982-986` preloads the zoom/large variant of the active gallery image via `new Image()` so hover-zoom feels instant. Manual, single-purpose, not a general strategy.
- **Blur-up / LQIP placeholders**: not found — the only "loading" visual is a generic skeleton block (admin only, via `ImageWithFallback`) or the list-level `ProductCardSkeleton` shown before data arrives (not per-image).
- **Image caching strategy**: none beyond default browser HTTP caching against R2/Cloudflare's `max-age=14400` response header; no service worker.

---

## 11. Thumbnail vs. Product Detail — Direct Comparison

**Product used:** "92.5 Sterling Silver Evil Eye Beaded Bracelet for Women & Men" (`product_id=1a3e0b0e-449d-4622-b08c-086d9eda29f8`), captured live from the running dev stack at 1440×900 viewport, DPR 1.25.

| Metric | Product Listing card | Product Detail main image |
|---|---|---|
| URL | `.../thumbnail.webp?v=1783249400` | `.../medium.webp?v=1783249400` |
| Natural (source) resolution | **200 × 200 px** | **600 × 600 px** |
| Transfer size | 7.7 KB | 48.6 KB |
| Compression | WebP q=85 | WebP q=85 (same pipeline) |
| Rendered CSS size (measured) | 289–325 px square (grid-dependent) | 564 px square |
| DPR-adjusted pixels needed | ~360–406 px (at DPR 1.25) | ~705 px (at DPR 1.25) |
| Upscale factor (source vs. needed) | **~1.8–2.0× upscaled** | ~1.18× upscaled (mild, sharp in practice) |
| Zoom variant available | No (thumbnail is the only size ever sent to this view) | Yes — `large.webp`, 1018×1018, 100.6 KB, swapped in on hover/pinch |

**Why the Product Detail image looks sharper:** it isn't a CDN, compression, or format difference — both are WebP at the same quality setting through the same Pillow pipeline. The difference is purely **which pre-generated size the backend decided to hand back for each context** (Section 5's `service.py:114-118`), combined with the frontend having no `srcset`/DPR mechanism to compensate. The listing thumbnail is source-limited to 200px and is being stretched roughly 1.8–2× beyond its native resolution in a normal desktop grid, before DPR is even considered (a 2×/3× retina phone would need 578–1218px of source and still only gets 200px). The detail page's medium image is close enough to its display size that the mismatch isn't visually obvious, and the further zoom-in swap to the 1200px `large` variant makes the interactive zoom sharp regardless.

---

## 12. Browser Network Analysis (live capture)

Captured directly against the running dev stack (`cdn.hadha.co` is a real, non-mocked Cloudflare/R2 origin):

```
GET https://cdn.hadha.co/products/.../thumbnail.webp
  200 OK · image/webp · 7,758 bytes · Cache-Control: max-age=14400 · no content-encoding

GET https://cdn.hadha.co/products/.../medium.webp
  200 OK · image/webp · 48,614 bytes · Cache-Control: max-age=14400 · no content-encoding

GET https://cdn.hadha.co/products/.../large.webp
  200 OK · image/webp · 100,618 bytes · Cache-Control: max-age=14400 · no content-encoding
```
No `ETag` returned on any of the three (worth noting — without it, once the 4-hour `max-age` lapses the browser can't send a conditional `If-None-Match` revalidation and must do a full re-fetch).

**Separately discovered bug during live capture:** at least one real product in the current catalog (`92.5 Sterling Silver Angel Wing Stud Earrings`, API response confirms `"primary_image": null`) has no primary image at all, and the storefront renders an `<img src="">` for it — the browser console logs React's warning verbatim: *"An empty string ("") was passed to the src attribute... this may cause the browser to download the whole page again over the network."* This reproduces on the live `/products` listing today and is a genuine, verifiable frontend defect (missing a guard for `image: null`/`""` before rendering the `<img>`), not a hypothetical.

---

## 13. Deliverables — Consolidated

### Architecture diagram (text form)

```
Admin uploads file (jpg/png/webp, ≤10MB, admin-only)
        │
        ▼
FastAPI /admin/products/{id}/images  →  MediaService (Pillow)
        │                                    │
        │                       ┌────────────┼────────────┬─────────────┐
        │                    original     thumbnail      medium        large
        │                   (untouched)   200×200 webp  600×600 webp  1200×1200 webp
        ▼                       ▼             ▼             ▼             ▼
   Cloudflare R2  ──  products/{product_id}/{image_uuid}/{original|thumbnail|medium|large}
        │
        ▼
   cdn.hadha.co (Cloudflare edge cache, max-age=14400, R2 default — not app-configured)
        │
        ▼
   product_images row: url, thumbnail_url, medium_url, large_url  (Postgres)
        │
        ▼
   Backend serialization
     • ProductListItem.primary_image  = thumbnail_url  (+?v= cache-bust)   ← used everywhere in "list" contexts
     • ProductImageResponse.{url,thumbnail_url,medium_url,large_url}      ← used on Product Detail
        │
        ▼
   Frontend (no srcset/sizes/DPR anywhere)
     • ProductCard, Wishlist, Cart, Checkout  → <img src=thumbnail_url>   (200px, stretched to 289–325px+)
     • Product Detail gallery                 → <img src=medium_url>     (600px, ~564px display)
     • Product Detail zoom (hover/pinch only) → <img src=large_url>      (1200px)
```

### Component hierarchy (storefront image-rendering paths)
```
ProductGrid → ProductCard → raw <img> ×2 (front/back 3D flip faces)         [thumbnail_url]
products.$slug.tsx → ProductImageViewer → raw <img> ×2 (desktop/mobile)     [medium_url / large_url on zoom]
                    → thumbnail strip → raw <img>                          [medium_url]
CartDrawer / cart.tsx / checkout.tsx → raw <img>                           [snapshot.image = thumbnail_url]
wishlist.tsx → raw <img>                                                   [item.image = thumbnail_url]
(admin only) ImageWithFallback (packages/shared-ui) → used across admin.*.tsx CMS/product/collection screens
```

### Existing optimization techniques
`loading="lazy"` (inconsistent coverage), `decoding="async"` (partial), one targeted `fetchPriority="high"` use, one targeted JS preload of the zoom image, WebP re-encoding at q85, fixed 3-tier pre-generated sizes.

### Issues / inconsistencies identified (no fixes applied — audit only)
1. **Root cause**: listing/cart/wishlist/checkout unconditionally use the 200×200 thumbnail regardless of actual display size, with no responsive-image mechanism to compensate (`catalog/service.py:114-118`; Sections 5, 6, 11).
2. No `srcset`/`sizes`/DPR support anywhere — the medium/large split for Product Detail is manually curated, not browser-negotiated.
3. `<img src="">` renders for any product with no primary image (`primary_image: null`), triggering a real React console warning and confirmed live on `/products` today.
4. Storefront never uses the shared `ImageWithFallback` component — no per-image skeleton/error-fallback on the storefront, only on admin.
5. Admin's preview `ProductCard` and the real storefront `ProductCard` have visually diverged (`object-cover`+`scale-110` vs. `object-contain`+3D-flip) despite both claiming to represent the same UI.
6. `thumbnail_url` is fetched by the frontend product-detail mapper type but never actually used there.
7. `alt_text` column exists, is always written as `NULL`, and has no update path — accessibility metadata is structurally impossible to populate today.
8. No `width`/`height`/`file_size` persisted on `product_images` (present on the parallel CMS media table, so this is an inconsistency, not a limitation of the approach).
9. Cache-Control on CDN images (`max-age=14400`, no `ETag`) is an R2/Cloudflare default, not a deliberate app-level choice — and the lack of `ETag` means a cold revalidation is a full re-fetch every 4 hours.
10. Product deletion doesn't clean up its R2 image folder (collections/categories do); this is a storage-hygiene gap, not a rendering bug.
11. `rate_limit_upload` and `get_presigned_upload_url` are both fully implemented but never wired to anything — dead code, not a bug, but worth knowing before building on top of either.
12. Two independent, duplicated image-processing pipelines exist (`media/service.py` vs. `cms/media_service.py`) with separate constants and no shared code.

### Root cause of blurry thumbnails
Confirmed and quantified in Section 11: the listing/grid/cart/wishlist/checkout image is source-limited to 200×200px by explicit backend design, then stretched ~1.8–2× (before DPR) to fill its actual CSS box in the live storefront grid. This is a resolution-selection problem at the backend service layer, not a compression, format, or CDN configuration problem.

### Prioritized improvement list (documentation only — not implemented)
1. **Highest impact / lowest risk**: stop forcing `thumbnail_url` for listing contexts — serve `medium_url` (or a new appropriately-sized variant) as `primary_image`/`secondary_image`, sized to the grid's actual rendered box at common breakpoints × DPR.
2. Add `srcset`/`sizes` (or at minimum a 1x/2x pair) wherever product images render, so the browser — not a hardcoded mapper choice — picks the right variant for the viewport/DPR.
3. Fix the `<img src="">` case for products with no image (render a placeholder/fallback instead of an empty `src`).
4. Bring the storefront onto the shared `ImageWithFallback` component (or an equivalent) for consistent skeleton/error handling, instead of hand-rolled `<img>` tags per page.
5. Reconcile admin's preview `ProductCard` with the real storefront one (share one implementation via `packages/shared-ui`) so CMS previews stop lying about what customers see.
6. Add a `width`/`height`/`file_size` (and populate `alt_text` via a real endpoint) to `product_images`, matching what the CMS media table already does.
7. Decide deliberately on CDN cache policy (explicit `Cache-Control` + `ETag` at upload time) rather than inheriting R2's default.
8. Clean up R2 objects on product deletion, matching the collections/categories pattern already in place.
9. Consider consolidating the two parallel media-processing pipelines, or at least sharing the resize/WebP helper code between them.
