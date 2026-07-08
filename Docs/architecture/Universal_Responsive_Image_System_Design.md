# Universal Responsive Image Management System — Architecture Design (v2, Clean-Slate Replacement)

**Status:** Proposed | **Author:** Lead Software Architect | **Date:** 2026-07-08
**Source of truth:** `docs/audits/universal-image-pipeline-analysis.md` (referenced throughout as "the Audit"; gap numbers `G1`–`G17` refer to its §13 Gap Analysis)
**Supersedes:** v1 of this document, which was written as a gradual, backward-compatible *migration* (dual-write periods, retained legacy tables, hedged format decisions). Hadha.co is **pre-production** — there are no live customers, no production data, and no external readers to protect. This revision throws out every migration compromise and specifies a **complete replacement**: one system, built once, cut over to atomically, with the old system deleted in the same release.

---

## 1. Executive Summary

Hadha.co currently runs **four parallel, hand-built image pipelines** (Product/Collection/Category via `MediaService`, CMS via `CmsMediaService`, Avatar via a fixed-key one-off, Review images completely unprocessed) plus **two modules with no upload path at all** (Company logo, SEO OG image pasted as raw strings). Each pipeline reimplements validation, storage, and variant generation slightly differently, and none of them give the admin a WYSIWYG, viewport-accurate preview of how a crop will actually render.

This document defines a **single Universal Responsive Image Management System (URIS)**: one backend service, one storage convention, one metadata schema, and one frontend crop/upload component, parameterized entirely by a **Crop Preset Registry**. Every module — existing (Product, Collection, Category, Hero, Banners, Instagram, Footer/Company logo, SEO OG, Avatar, Reviews, Testimonials) and future (Team, Blog, About) — becomes a **thin preset definition** that plugs into this shared pipeline instead of writing its own upload/crop/storage code.

**This is a replacement, not a migration.** Because the project has no production traffic and no data that must survive with zero-downtime guarantees, the design commits to the following, stated up front so every later section can be read without hedging:

- **No dual-running.** `MediaService`, `CmsMediaService`, `profiles.upload_avatar`, and `reviews._attach_images`'s image handling are deleted in the same release that ships `UniversalImageService`. There is no period where both the old and new pipeline serve traffic.
- **No legacy tables survive.** `product_images` and `cms_media` are dropped, not kept as read-only views or "temporarily retained" compatibility tables. `collections.image_url`, `categories.image_url`, `banners.desktop_image_url`/`mobile_image_url`, `profiles.avatar_url`, `review_images`, and the raw-string `company_config`/`seo_pages` image columns are all dropped in the same migration that introduces `images`/`image_variants`.
- **No generated/denormalized backward-compat columns.** There is no `image_url` kept in sync via a DB trigger "for old readers" — there are no old readers, because the only readers (this codebase's own frontend) are updated in the same change.
- **No soft/lossy backfill.** Existing dev-seed images are **not** migrated pixel-for-pixel from derived `large.webp` files pretending to be originals. They are re-uploaded and re-cropped once, by hand, during cutover, because this is seed/test data, not customer data, and re-uploading is materially simpler and higher-quality than writing and maintaining a lossy backfill script for data nobody needs to keep.
- **One canonical image format, not a flag.** WebP q85 is the only output format the system generates, for every module, from day one. There is no "AVIF behind a flag for MVP" — AVIF encoding is deferred to Future Extensions (§19) as a genuine future enhancement, not a hedge shipped-but-disabled.
- **One database schema.** Two tables — `images` and `image_variants` — model every image in the system. No module gets its own image table, ever, including ones not yet built (Team/Blog/About).
- **One frontend component.** `<UniversalImageEditor>` is the only upload/crop component in the entire monorepo, from the first commit that introduces it. No module-specific crop component is ever built, not even temporarily during rollout.

The architecture closes all 17 gaps identified in the Audit: it introduces real responsive delivery (`srcset`/`sizes`, closing G1/G16), reads and generates true desktop/tablet/mobile variants (closing G2), unifies validation (G3), gives every module a crop UI including Collections/Categories (G4), removes the raw-URL-paste escape hatch (G5), implements drag-to-reorder (G6), processes Review images through the same pipeline (G7), adds `Cache-Control` + deterministic versioning everywhere (G8/G9), gives Company logo and SEO OG a real upload+crop flow (G10), collapses the four backend pipelines into one shared core (G11), replaces silent `except: pass` with structured error handling and a status/retry model (G12), formally decides and either keeps or deletes the presigned-upload path (G13), adds server-side crop geometry validation against real image bounds (G14), makes `ImageWithFallback`'s successor mandatory storefront-wide (G15), and defines a first-class preset for future Team/Blog/About modules (G17). It closes them once, cleanly — not through a transitional state that itself needs to be unwound later.

---

## 2. Current Problems (synthesized from the Audit)

**Fragmentation.** Four independent code paths (`MediaService`, `CmsMediaService`, `profiles.upload_avatar`, `reviews._attach_images`) each re-implement R2 client construction, public-URL building, and validation with different limits (10 MB vs 50 MB), different MIME allow-lists, and — in the Review path — no validation whatsoever (Audit G3, G7).

**No true responsiveness.** The backend already produces thumbnail/medium/large tiers for Products/Collections/Categories, yet the frontend picks a single URL *per context* (card vs. zoom), never *per viewport* — no `srcset`, `sizes`, or `<picture>` anywhere in either app (G1, G16). CMS-driven imagery (Hero, Banners, Instagram) has only one size tier total, meaning the storefront can serve an arbitrarily large uncompressed original to a 390px-wide phone.

**Captured-but-unused data.** `banners.mobile_image_url` is populated by admins and never read by `Hero.tsx` (G2) — a working feature invisible to customers because the storefront component was never wired to it.

**No crop control where it matters most.** Collections and Categories run through the exact same square-normalizing backend pipeline as Products but have zero crop UI — admins cannot choose framing for two of the highest-traffic surfaces in the storefront (G4).

**Validation bypass.** `ImageUploadField.tsx` exposes a raw URL text input alongside the upload button for every CMS-managed image, letting an admin paste any external URL and skip upload, resizing, and CDN entirely (G5).

**Unimplemented features backed by working schema.** `product_images.sort_order` is indexed and drives `ORDER BY` but has no reorder UI/endpoint (G6).

**Unsafe/unprocessed paths.** Review images are stored with a client-supplied, unsanitized filename and zero Pillow processing — a path-injection and key-collision risk unique to this module (G7).

**No cache policy.** No `put_object` call in either service sets `CacheControl`; only Products get cache-busting via `?v=<updated_at>` (added by the newest migration in the set) — Avatars use a fixed key that never busts (G8/G9).

**Indirect, guardrail-free workflows.** Company logo and SEO OG image have no upload endpoint at all — an admin must round-trip through the CMS media library to get a URL and paste it into an unrelated form (G10).

**Duplicated infrastructure.** `_get_r2_client()`/`_public_url()` exist twice, near-verbatim, with no shared base (G11).

**Silent failures.** Five call sites wrap R2 deletes in bare `try/except: pass`; CMS thumbnail generation failures are swallowed the same way, leaving `NULL` metadata with no signal (G12).

**Dead/unaudited surface.** `get_presigned_upload_url` exists with no confirmed caller (G13). Crop geometry is only Pydantic-validated for non-negativity, not against the real original's pixel bounds server-side (G14, currently soft-mitigated by PIL's own clamping).

**Dead component.** `ImageWithFallback` (skeleton/error-fallback wrapper) is imported only by the admin app; the storefront hand-rolls inconsistent (often absent) error handling per component (G15).

**No home for future modules.** Team/About/Blog have no dedicated schema today; if built, they would inherit every gap above by default unless architected against this system from day one (G17).

---

## 3. New Architecture (high-level)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     packages/shared-media: <UniversalImageEditor>        │
│   Upload → Locked Preset → Crop+Zoom+Pan+Rotate →                        │
│   Preview(Desktop|Tablet|Mobile) → Save                                  │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 │ used identically by admin & (where relevant) storefront
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    packages/shared-types: CropPreset, ImageAsset,        │
│                    ImageVariant, CropGeometry, FocusPoint (contracts)    │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 │ HTTP (multipart + JSON PATCH)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              Backend/app/modules/media (the ONLY image module —          │
│              media/, cms/media_service.py, profiles' avatar handling,    │
│              and reviews' image handling do not exist as separate code)  │
│                                                                            │
│  router.py        — one set of REST endpoints, preset-parameterized      │
│  service.py        — UniversalImageService (orchestration)               │
│  crop_engine.py    — pure-function crop/pan/zoom/rotate/mask math        │
│  preset_registry.py— PRESET_REGISTRY: Dict[str, CropPreset]              │
│  variant_generator.py — Pillow-based, driven by preset.output_variants   │
│  storage.py        — single R2 client, key builder, Cache-Control, dedupe│
│  validation.py      — one MIME/size/dimension policy per preset class    │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────┐   ┌───────────────────────────────────────────┐
│ images / image_variants│   │  Cloudflare R2                            │
│  (the only image tables│   │  images/{module}/{owner_type}/{owner_id}/ │
│  in the entire schema, │   │    {image_id}/original.{ext},             │
│  see §9)                │   │    {variant}.webp                         │
└───────────────────────┘   └───────────────────────────────────────────┘
```

Key architectural shift: **modules stop owning image logic, permanently, not just during a transition**. A module (Product, Hero, Category, …) owns only a `CropPreset` definition and a nullable FK to the universal `images` table (`primary_image_id`, or a many-image relationship via `images.owner_type`/`owner_id` for galleries). There is no direct URL string column on any owner table — `collections.image_url`, `categories.image_url`, `banners.desktop_image_url`, `profiles.avatar_url`, and every other one-off image column the Audit catalogued are removed, not deprecated. The single exception, discussed in §16, is `order_items.image_url`, which is an intentional **immutable snapshot** written once at order-creation time by copying a resolved variant URL — it is not a live pipeline and is out of scope for this replacement.

---

## 4. Universal Crop Engine

The Crop Engine is a **pure, preset-driven transformation pipeline**, implemented once, called by every module.

**Inputs:** original image bytes (never mutated), a `CropPreset`, and a `CropGeometry` (per breakpoint) consisting of:
- `focus_point`: `{x: float 0-1, y: float 0-1}` — normalized center of interest, independent of any specific crop box (used as a sane default when a breakpoint hasn't been explicitly cropped yet, and for `object-position` fallback in the browser).
- `zoom`: float, bounded by `preset.max_zoom`.
- `pan`: `{x, y}` in the zoomed image's coordinate space.
- `rotation`: degrees, bounded by `preset.rotation.allowed` (`0`, `90-step`, or `free ±180°`, per preset).
- `crop_box`: `{x, y, width, height}` in **original pixel space**, one **per responsive breakpoint** the preset defines (desktop/tablet/mobile), each independently adjustable but seeded from the same focus point.

**Pipeline stages (server-side, `crop_engine.py` + `variant_generator.py`):**
1. **Fetch original** — always the untouched R2 object; never read from a previously-derived variant.
2. **Rotate** — apply `rotation` in the original's own pixel space using Pillow `Image.rotate(expand=True)`.
3. **Geometry validation** (closes G14) — server recomputes `crop_box` bounds against the *actual* rotated image dimensions (not just Pydantic non-negativity); a box that doesn't fit is clamped and the clamp is logged, or rejected with `422` if `preset.strict_bounds=True` (default for presets with `min_resolution` requirements, e.g. Hero).
4. **Shape mask apply** — per `preset.shape` (Rectangle/Square/Circle/RoundedRect/Contain/Cover/custom SVG mask path). Circle/RoundedRect produce a WebP with alpha channel; Rectangle/Square/Contain/Cover do not.
5. **Per-breakpoint crop** — for each entry in `preset.breakpoints` (e.g. desktop/tablet/mobile for Hero; single entry for Product), crop to that breakpoint's `crop_box`, then resize to that breakpoint's `output_variants` (e.g. desktop → 1x/2x @ preset target width).
6. **Variant generation** — WebP q85 for every `(breakpoint × variant × DPR)` combination defined in `preset.output_variants`. This is the only format the pipeline produces (§8) — there is no per-preset format flag to branch on.
7. **Persist** — write all variant objects to R2 under the deterministic key scheme (§12), write one `images` row + one `image_variants` row per generated file, write the full `CropGeometry` + preset id into `images.metadata` JSONB (§13).
8. **Cache-bust** — every write bumps `images.version`; all served URLs are `?v={version}`.

**Re-edit flow:** re-opening the editor always starts stage 1 from the stored `original.{ext}` key, never from a derived variant — guaranteeing no generational quality loss and satisfying "original never modified."

---

## 5. Crop Preset Registry

`Backend/app/modules/media/preset_registry.py` (mirrored in TS as `packages/shared-types/src/imagePresets.ts` for the frontend, generated from a shared JSON Schema at build time — see §18 tooling note — to guarantee the two never drift):

```python
class CropPreset(BaseModel):
    id: str                          # "product", "hero", "category", ...
    label: str                       # admin-facing name
    shape: ShapeType                 # RECTANGLE | SQUARE | CIRCLE | ROUNDED_RECT | CONTAIN | COVER | CUSTOM_MASK
    mask_svg: str | None             # required if shape == CUSTOM_MASK
    aspect_ratio: dict[Breakpoint, float | None]   # None = free-form per breakpoint
    safe_area: SafeArea              # {top, right, bottom, left} as % — text/logo overlay avoidance
    min_resolution: dict[Breakpoint, Resolution]    # reject uploads below this at that breakpoint's crop
    max_zoom: float
    rotation: RotationPolicy         # {allowed: NONE|90_STEP|FREE, range: (-180,180)}
    breakpoints: list[Breakpoint]    # which of [desktop, tablet, mobile, all] this preset previews/crops independently
    output_variants: list[VariantSpec]  # e.g. [{name:"thumbnail", w:200,h:200}, {name:"medium", w:600,h:600}, {name:"large", w:1200,h:1200}]
    storage_rules: StorageRules      # {folder: "products", max_file_mb: 10, allowed_mime: [...], strict_bounds: bool}
    reference_ui: str                # short description used to render the "Preview" pane's chrome (e.g. "product-card", "hero-full-bleed")
```

`storage_rules` no longer carries a `formats` list — format is a single global constant (`WEBP`, q85), defined once in `variant_generator.py`, not a per-preset choice (see §8). `PRESET_REGISTRY: dict[str, CropPreset]` is the single source of truth, loaded once at startup, exposed read-only via `GET /admin/media/presets` so the frontend never hardcodes preset shape logic — it renders whatever the registry returns. Adding a new module = adding one entry to this registry + wiring one FK; no new crop code, ever — not "no new crop code after the migration window."

---

## 6. Module-wise Crop Presets

For every module the preset fields are given as `{aspect_ratio, shape, safe_area, min_resolution, max_zoom, rotation, breakpoints, output_variants, storage_rules}`.

### 6.1 Product (`product`)
- aspect_ratio: `{all: 1:1}`
- shape: SQUARE
- safe_area: none (product photography assumed pre-composed)
- min_resolution: `{all: 800x800}` (headroom for `large` 1200×1200 tier without upscaling)
- max_zoom: 5.0 (matches current `ImageCropModal`)
- rotation: FREE ±180°, 1° step
- breakpoints: `[desktop, tablet, mobile]` — same square crop box shared across breakpoints by default, but preview simultaneously so a photographer can sanity-check how a phone grid tile looks vs desktop PDP zoom
- output_variants: `thumbnail 200×200`, `medium 600×600`, `large 1200×1200`, each at 1x and 2x DPR (2x replaces v1's separately-flagged "retina" tier — it is simply always generated, not an optional extra)
- storage_rules: `products/`, 10 MB, `{jpeg,png,webp}`, strict_bounds=true

### 6.2 Collection (`collection`)
- aspect_ratio: desktop `1:1`, mobile `1:1` (closes G4 — was aspect-video mismatch)
- shape: SQUARE
- safe_area: `{bottom: 20%}` (space reserved for title overlay text seen on collection tiles)
- min_resolution: `{desktop: 1200x1200, mobile: 600x600}`
- max_zoom: 4.0
- rotation: NONE (cover photography, rotation rarely needed; can be relaxed later)
- breakpoints: `[desktop, mobile]`
- output_variants: `thumbnail 200×200`, `medium 600×600`, `large 1200×1200` (all three persisted and served — v1 flagged Collections as discarding two of three generated tiers; that inconsistency does not exist in this design because there is no "discard" behavior anywhere in the pipeline)
- storage_rules: `collections/`, 10 MB, `{jpeg,png,webp}`

### 6.3 Category (`category`)
Identical shape/fields to Collection, separate `id` and `storage_rules.folder = "categories/"` for isolation and independent tuning later.

### 6.4 Hero (`hero`)
- aspect_ratio: `{desktop: 1920/700, tablet: 1024/700, mobile: 390/600}`
- shape: RECTANGLE
- safe_area: `{left: 45%}` on desktop (protects space for hero copy/CTA overlay), `{top: 15%, bottom: 20%}` on mobile (protects header/CTA)
- min_resolution: `{desktop: 1920x700, tablet: 1024x700, mobile: 390x600}`
- max_zoom: 3.0
- rotation: NONE
- breakpoints: `[desktop, tablet, mobile]` — all three previewed and cropped simultaneously, closing G2 for good: the mobile crop is mandatory before save, not merely "captured but unread"
- output_variants: per breakpoint, 1x + 2x DPR (`hero-desktop@1x/2x`, `hero-tablet@1x/2x`, `hero-mobile@1x/2x`)
- storage_rules: `hero/`, 15 MB, `{jpeg,png,webp}`, strict_bounds=true

### 6.5 Homepage / Promo Banners (`promo_banner`)
The Audit flags two structurally divergent banner mechanisms today: the `banners` DB table (with real `desktop_image_url`/`mobile_image_url` columns) and a `landing_sections`-JSONB-backed CMS section whose TS config type only defines `desktop_image_url`. **This design does not carry that duality forward.** Both mechanisms become the same thing: `owner_type='banner'` rows in `images`, referenced by ID from wherever the banner is configured (a `banners` table row or a `landing_sections.config` JSONB blob) — the storage/crop/variant model is identical either way, so the duality becomes purely "which entity owns the FK," not "which of two incompatible image pipelines runs."
- aspect_ratio: `{desktop: 1920/720, mobile: 750/1000}`
- shape: RECTANGLE
- safe_area: `{right: 40%}` desktop, `{bottom: 25%}` mobile
- min_resolution: `{desktop: 1920x720, mobile: 750x1000}`
- max_zoom: 3.0, rotation NONE
- breakpoints: `[desktop, mobile]`
- output_variants: 1x/2x per breakpoint
- storage_rules: `banners/`, 15 MB, `{jpeg,png,webp}`

### 6.6 CMS Sections — Gender Section (`gender_section`)
- aspect_ratio: `{all: 1:1}` (bounding box for the circular mask)
- shape: CIRCLE
- safe_area: none (circular framing itself is the safe area)
- min_resolution: `{desktop: 600x600, mobile: 400x400}`
- max_zoom: 4.0, rotation NONE
- breakpoints: `[desktop, mobile]`
- output_variants: `thumb 200×200`, `medium 500×500` (both WebP with alpha)
- storage_rules: `gender-section/`, 8 MB, `{jpeg,png,webp}`

### 6.7 Testimonials (`testimonial_avatar`)
- aspect_ratio: `1:1`, shape CIRCLE, safe_area none
- min_resolution: `{all: 300x300}`, max_zoom 5.0, rotation NONE
- breakpoints: `[all]` (single, non-viewport-dependent — small avatar-class asset)
- output_variants: `avatar 200×200`
- storage_rules: `testimonials/`, 5 MB, `{jpeg,png,webp}`

### 6.8 Instagram Gallery (`instagram_tile`)
- aspect_ratio: `1:1`, shape SQUARE, safe_area none
- min_resolution: `{all: 500x500}`, max_zoom 3.0, rotation NONE
- breakpoints: `[desktop, mobile]` (grid tile can crop tighter on mobile 2-col vs desktop 4-col)
- output_variants: `thumb 250×250`, `medium 500×500`
- storage_rules: `instagram/`, 10 MB, `{jpeg,png,webp}`

### 6.9 Footer Logo (`footer_logo`) / Company Logo (`company_logo`)
Two separate preset ids (different downstream consumers: web footer vs. PDF packing-slip/shipping-label) but same shape family:
- aspect_ratio: CONTAIN mode, no forced ratio (logos must not be stretched/cropped)
- shape: CONTAIN
- safe_area: `{all: 10%}` padding
- min_resolution: `{all: 300x100}`
- max_zoom: 1.0 (no zoom — logos are placed, not cropped), rotation NONE
- breakpoints: `[all]`
- output_variants: `web 400×auto (WebP)`, `print 1200×auto (PNG, transparency-preserving, for PDF embedding)` — this is a deliberate exception to the "WebP only" rule (§8) because PDF embedding via `fulfillment/service.py` needs transparency-preserving raster; it replaces the current live `httpx.get` fetch at PDF time entirely with a pre-generated, cached print-quality asset — the fulfillment code stops making an HTTP call at PDF-generation time and instead reads `image_variants` for `variant_name='print'`
- storage_rules: `branding/`, 5 MB, `{png,svg,webp}` — new upload endpoint, closes G10

### 6.10 SEO / OG Image (`seo_og`)
- aspect_ratio: `1200/630` (fixed, matches OpenGraph spec exactly)
- shape: RECTANGLE, safe_area `{all: 8%}` (platform crop safety per Facebook/Twitter card guidance)
- min_resolution: `{all: 1200x630}`, max_zoom 3.0, rotation NONE
- breakpoints: `[all]`
- output_variants: `og 1200×630` — WebP, not JPEG; every major platform that consumes OpenGraph images (Facebook, Twitter/X, LinkedIn, Slack, Discord) supports WebP as of 2024, so there is no reason to special-case this preset's format the way v1 did ("JPEG for widest compatibility" was a hedge, not a requirement)
- storage_rules: `seo/`, 5 MB, `{jpeg,png,webp}` — new upload endpoint, closes G10

### 6.11 Avatar (`avatar`)
- aspect_ratio: `1:1`, shape CIRCLE, safe_area none
- min_resolution: `{all: 200x200}`, max_zoom 5.0, rotation NONE
- breakpoints: `[all]`
- output_variants: `avatar 400×400`, `avatar-sm 100×100` (nav/header use)
- storage_rules: `avatars/`, 5 MB, `{jpeg,png,webp}` — key is `avatars/{user_id}/{image_id}/…` (UUID-scoped from day one, not fixed-key — closes G9)

### 6.12 Review Images (`review_photo`)
- aspect_ratio: free-form input, output normalized to `4:3` CONTAIN with white padding (matches product photography treatment, avoids distorting customer photos)
- shape: CONTAIN, safe_area none
- min_resolution: `{all: 400x300}`, max_zoom 1.0 (no user-facing crop UI on storefront — auto-normalize only, to keep the customer-facing review form lightweight), rotation NONE
- breakpoints: `[all]`
- output_variants: `thumb 150×150`, `medium 600×450`
- storage_rules: `reviews/`, 8 MB, `{jpeg,png,webp}`, filenames always server-generated UUIDs (closes G7's path-injection risk)

### 6.13 Team / About / Blog (`team_member`, `blog_cover`, `blog_inline`) — future, defined now
- `team_member`: `1:1`, CIRCLE or ROUNDED_RECT (brand choice), min 400×400
- `blog_cover`: `{desktop: 1600/900, mobile: 750/900}`, RECTANGLE
- `blog_inline`: free aspect, CONTAIN, max width 1200
All three registered from day one so that when Team/Blog modules are eventually built (Audit G17), they consume the shared pipeline immediately rather than spawning a fifth bespoke path — this preset registry is now the *only* place image behavior is defined for the entire codebase, present and future.

---

## 7. Responsive Preview System

The shared `<UniversalImageEditor>` renders **three simultaneous, real-UI-accurate preview frames** (Desktop / Tablet / Mobile), not just a crop rectangle:

- Each preview frame is a **scaled-down replica of the actual consuming component's chrome** — e.g. the Hero preset's preview frames literally reuse the storefront's `Hero` slide layout (headline placeholder, CTA button, gradient overlay) at reduced scale, sourced from a small `PreviewChrome` registry keyed by `preset.reference_ui` (`hero-full-bleed`, `product-card`, `collection-tile`, `gender-circle`, …) living in `packages/shared-media/src/UniversalImageEditor/previewChrome/*`.
- Only the breakpoints listed in `preset.breakpoints` render a frame; presets with a single non-viewport-dependent breakpoint (Avatar, Testimonial) show one frame, unlabeled.
- Each frame is independently interactive for presets whose `breakpoints.length > 1`: dragging/zooming in the Mobile frame edits only that breakpoint's `crop_box`; a "Copy from Desktop" affordance seeds a new breakpoint's crop from an already-set one.
- Safe-area guides are rendered as a dashed overlay inside each frame when `preset.safe_area` is non-zero.
- Live preview uses **client-side canvas rendering** of the in-memory original (no server round-trip per drag frame); only Save triggers the server-side pipeline (§4), guaranteeing preview-vs-output parity because both use the identical crop-math module (`cropMath.ts`, a TS port of `crop_engine.py`'s pure geometry functions, unit-tested against the same fixtures on both sides).

---

## 8. Variant Generation Strategy

**One canonical decision, stated once, not per module:**

- **Format:** WebP, quality 85, and nothing else, for every preset except `footer_logo`/`company_logo`'s `print` variant, which is PNG for PDF-embedding transparency (§6.9 — the one documented, structural exception, not a configurable flag). There is no AVIF path in the shipped system; AVIF is listed only in Future Extensions (§19) as something to evaluate later, with zero scaffolding (no `storage_rules.formats` list, no feature flag, no dead code path) shipped in this design. If AVIF is adopted later, it is a new column/value added to an already-generalized `image_variants.format`, not a retrofit.
- **DPR:** 1x and 2x are always generated for every variant of every preset — this is not conditional on "breakpoint-aware presets" as v1 hedged; it is simply the rule. 3x is deliberately not generated (reserved in the `dpr` column's range but not a Phase-1 output) because no current display density used by Hadha.co's audience benefits from it enough to justify tripling storage for single-breakpoint presets like Avatar.
- **Trigger:** synchronous, in-request, immediately after Save for presets with ≤4 output artifacts (Product, Collection, Category, Avatar, Testimonial, Instagram, Gender Section, Review). For presets with more (Hero: 3 breakpoints × 2 DPR = 6 files; Banner similarly), generation is offloaded to a FastAPI `BackgroundTasks` call so the HTTP response returns as soon as the DB row is written with `status='pending'`; the admin UI polls `GET /admin/media/{id}` and reflects `pending|ready|failed`.
- **Determinism:** variant generation is a pure function of `(original_bytes, CropGeometry, CropPreset)` — safe to re-run idempotently, which is the primitive behind `POST /admin/media/{id}/regenerate` (e.g. if a preset's target resolution changes org-wide, all affected images are batch-regenerated from their originals with zero admin re-crop action).
- **Failure handling (closes G12):** each variant write is tracked individually in `image_variants.status`; a partial failure (e.g. one DPR tier fails) does not roll back successfully-generated siblings, is logged with structured context (`image_id`, `variant_name`, `breakpoint`, exception), and surfaces in the admin UI as a retry-able per-variant state — never a silent `NULL`.

---

## 9. Database Design

Two tables model every image in the system. There is no third "legacy" table anywhere — `product_images` and `cms_media` do not exist after cutover; they are dropped in the same Alembic migration that creates these two.

```sql
-- Canonical image asset (one row per uploaded original + its full crop/variant lineage)
CREATE TABLE images (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module          VARCHAR(40)  NOT NULL,        -- 'product' | 'hero' | 'collection' | ... (== preset.id family)
    preset_id       VARCHAR(60)  NOT NULL,        -- FK-by-convention into PRESET_REGISTRY (not a DB FK; registry is code-defined)
    owner_type      VARCHAR(40)  NOT NULL,        -- 'product' | 'collection' | 'category' | 'banner' | 'cms_section_item' | 'user' | 'review' | 'company_config' | 'seo_page'
    owner_id        UUID         NULL,            -- polymorphic FK target (nullable only for not-yet-attached uploads, e.g. media-library items)
    original_key    TEXT         NOT NULL,        -- R2 key of the untouched original
    original_ext    VARCHAR(10)  NOT NULL,
    original_width  INTEGER      NOT NULL,
    original_height INTEGER      NOT NULL,
    original_size_bytes INTEGER NOT NULL,
    mime_type       VARCHAR(80)  NOT NULL,
    alt_text        TEXT         NULL,
    metadata        JSONB        NOT NULL DEFAULT '{}',  -- CropGeometry per breakpoint, focus_point, safe_area snapshot, preset snapshot — §13
    status          VARCHAR(20)  NOT NULL DEFAULT 'ready', -- 'pending' | 'ready' | 'failed' | 'archived'
    version         INTEGER      NOT NULL DEFAULT 1,     -- bumped on every re-crop/replace; drives ?v= cache-busting
    uploaded_by     UUID         NULL REFERENCES profiles(id),
    sort_order      INTEGER      NOT NULL DEFAULT 0,     -- universal reorder column (closes G6, applies to every gallery-style module, not just products)
    is_primary      BOOLEAN      NOT NULL DEFAULT false,
    deleted_at      TIMESTAMPTZ  NULL,                    -- soft delete pending R2 confirmation (§12)
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_images_owner ON images (owner_type, owner_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_images_owner_sort ON images (owner_type, owner_id, sort_order) WHERE deleted_at IS NULL;
CREATE INDEX ix_images_status ON images (status) WHERE status <> 'ready';

-- One row per generated derived file (thumbnail/medium/large/hero-desktop@2x/...)
CREATE TABLE image_variants (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_id      UUID NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    breakpoint    VARCHAR(20)  NOT NULL,   -- 'desktop' | 'tablet' | 'mobile' | 'all'
    variant_name  VARCHAR(40)  NOT NULL,   -- 'thumbnail' | 'medium' | 'large' | 'og' | 'print' | ...
    dpr           SMALLINT     NOT NULL DEFAULT 1,  -- 1 or 2 (3 reserved, not generated by default)
    format        VARCHAR(10)  NOT NULL DEFAULT 'webp',  -- 'webp' for everything except footer/company logo's 'print' variant ('png')
    url           TEXT         NOT NULL,
    width          INTEGER      NOT NULL,
    height         INTEGER      NOT NULL,
    size_bytes     INTEGER      NOT NULL,
    status         VARCHAR(20)  NOT NULL DEFAULT 'ready', -- per-variant status, closes G12
    error_message  TEXT         NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (image_id, breakpoint, variant_name, dpr)
);
CREATE INDEX ix_image_variants_image ON image_variants (image_id);
```

**Attachment pattern — final, not transitional.** Owner tables get exactly one new column, `primary_image_id UUID NULL REFERENCES images(id)` (`collections`, `categories`, `banners`, `company_config`, `seo_pages`, `profiles` for avatar), and the old URL column on each of those tables is **dropped in the same migration**, not retained as a generated/denormalized compatibility column. There is no `image_url` synced by a DB trigger, because there is no reader left that expects it — every serializer is updated in the same PR that adds the column. Modules needing a full gallery (Product) use `images.owner_type='product', owner_id=<product_id>` with `sort_order`/`is_primary` directly, exactly as `product_images` did, just generalized to the shared table.

**Product images specifically:** `product_images` does not survive cutover in any form (no read-only view, no deprecated columns). Its `crop_x/y/width/height/zoom/rotation` fields map 1:1 into `images.metadata.crops.desktop`, extended to 3 breakpoints per §6.1. Its `is_primary`/`sort_order` columns become `images.is_primary`/`images.sort_order`.

**CMS media (`cms_media`)** does not survive cutover. `owner_type IN ('banner', 'cms_section_item')` rows in `images` replace it entirely. `landing_sections.config`/`draft_config` JSONB stores a reference (`{"image_id": "..."}`) instead of a raw URL string, resolved server-side at read time into the correct variant/breakpoint URL set — this is what finally makes `mobile_image_url` actually render (G2): the resolver, not a hardcoded frontend field access, decides which variants to return, and the frontend consumes a `srcset`-ready bundle rather than picking one field.

**`banners` table:** keeps its identity columns (label, link, sort order, active flag) but drops `desktop_image_url`/`mobile_image_url` in favor of `primary_image_id` — a single FK to an `images` row whose `promo_banner` preset already carries both desktop and mobile crops as breakpoints within one record, eliminating the two-column, two-upload-slot pattern entirely.

**No backfill script, no generated columns, no soft migration.** Because there is no production data, §17 specifies re-uploading and re-cropping the (small) set of dev-seed images once, by hand, during cutover, rather than writing, testing, and maintaining a one-time lossy backfill script whose entire purpose would be to avoid work that, for seed data, is faster to just do directly.

---

## 10. Backend Architecture

`Backend/app/modules/media/` is the **only** module in the codebase that touches image bytes, Pillow, or the R2 client. `Backend/app/modules/cms/media_service.py` does not exist after cutover; `profiles/router.py`'s avatar handling and `reviews/service.py`'s `_attach_images` no longer contain any Pillow/R2 code — they call into `media` instead.

```
media/
├── router.py              # REST surface (see endpoint table below)
├── service.py              # UniversalImageService — orchestrates validate→crop→variants→persist
├── crop_engine.py          # pure geometry functions (rotate/mask/crop math), no I/O, unit-testable
├── variant_generator.py    # Pillow-driven, consumes CropPreset.output_variants, WebP-only (§8)
├── preset_registry.py      # PRESET_REGISTRY, CropPreset/ShapeType/Breakpoint/VariantSpec models
├── storage.py               # R2Client (single instantiation), key builder, presigned helper, delete-with-retry
├── validation.py            # MIME/size/dimension checks, preset-aware
├── repository.py            # images/image_variants CRUD, polymorphic owner queries
├── schemas.py                # Pydantic request/response (UploadResponse, CropRequest, VariantSummary)
└── background.py             # variant regeneration task, retry/backoff for failed variants
```

**Endpoints (preset-parameterized, replacing all ~12 bespoke endpoints previously spread across `media/router.py` + `cms/router.py` + `profiles/router.py` + `reviews/router.py`):**
- `GET  /admin/media/presets` — returns `PRESET_REGISTRY` (public shape, no secrets) for frontend consumption.
- `POST /admin/media/{preset_id}/upload` — multipart upload; validates against `preset.storage_rules`; stores original; returns `image_id` + `status: pending`, generates default (focus-point-centered) variants immediately using preset defaults so there's always a usable image even before an admin manually crops.
- `PATCH /admin/media/{image_id}/crop` — body = `CropGeometry` (per-breakpoint boxes, zoom, pan, rotation, focus_point); triggers crop engine + regenerates only affected variants; bumps `version`.
- `PUT /admin/media/{image_id}/replace` — swaps the original, nulls all crop geometry, forces re-crop.
- `PATCH /admin/media/{image_id}/attach` — sets `owner_type`/`owner_id` (used when an image is uploaded via a generic media picker before the parent entity is saved, e.g. new Collection draft).
- `PATCH /admin/media/reorder` — body = `[{image_id, sort_order}]` for a given `(owner_type, owner_id)` — closes G6, generalized to every gallery-style module, not just products.
- `DELETE /admin/media/{image_id}` — soft delete + async R2 cleanup with retry+alert on failure (closes G12).
- `POST /admin/media/{image_id}/regenerate` — maintenance/ops endpoint to re-run variant generation from the stored original + geometry (preset changes).
- Storefront-facing read: images are never fetched by ID directly by the storefront; owner entities' serializers (`ProductSchema`, `CollectionSchema`, `BannerSchema`, …) embed a resolved `ImageBundle` (§13) inline, keeping today's "URLs already CDN-absolute in the API response" contract intact.

**Presigned upload path decision (closes G13, decided, not deferred):** `get_presigned_upload_url` is **deleted, not carried forward.** The Audit found no confirmed caller for it (G13); rather than re-implement and re-document an unaudited path "just in case," this design ships only the multipart-upload endpoint for every preset, including large-source presets like Hero (a 15 MB cap comfortably fits standard multipart upload; there is no volume today that justifies a direct-to-R2 presigned path). If a genuine need for direct-to-R2 large uploads emerges later, it is added then, as a new, purpose-built endpoint — not resurrected speculatively.

**Layering:** `router.py` never touches Pillow/boto3 directly (today it does, per Audit §4 code citations) — all of that lives in `service.py`/`variant_generator.py`/`storage.py`, giving a clean controller→service→repository/storage layering consistent with the rest of the codebase's modular-monolith convention (`Backend/app/modules/*`).

---

## 11. Frontend Architecture

**New shared package** — `packages/shared-media/` (sibling to `shared-ui`/`shared-api`/`shared-types`/`shared-utils`), housing everything crop/preview-specific:

```
packages/shared-media/src/
├── UniversalImageEditor/
│   ├── UniversalImageEditor.tsx      # top-level orchestrator: Upload→Crop→Preview→Save
│   ├── CropCanvas.tsx                 # zoom/pan/rotate/mask-aware canvas (wraps react-easy-crop, extended for shape masks)
│   ├── PreviewFrame.tsx               # renders one breakpoint's real-UI-accurate preview
│   ├── previewChrome/                 # per-reference_ui mini-layouts (hero-full-bleed.tsx, product-card.tsx, ...)
│   ├── SafeAreaOverlay.tsx
│   ├── VariantStatusBadge.tsx
│   └── useCropGeometry.ts             # state machine: per-breakpoint geometry, "copy from desktop", undo
├── cropMath.ts                        # TS port of crop_engine.py's pure functions (parity-tested)
├── presetClient.ts                    # fetches/caches GET /admin/media/presets
└── index.ts
```

- **Every** upload/crop surface in the admin app — `ProductForm.tsx`, `CollectionForm.tsx`, `CategoryForm.tsx`, `admin.cms.index.tsx` (Hero/Banner/Instagram/Footer/Testimonial fields), and a new Company/SEO settings screen — is reduced to `<UniversalImageEditor presetId="hero" ownerType="banner" ownerId={id} onSaved={...} />`. `admin/src/components/admin/ImageUpload.tsx`, `admin/src/components/admin/products/ImageCropModal.tsx`, and `admin/src/components/cms/ImageUploadField.tsx` are all deleted — none of them exist alongside `<UniversalImageEditor>`, not even briefly (see §16).
- **Storefront** consumes the identical component only where customer-facing upload exists: Avatar (account settings) with `presetId="avatar"`, and Review photo submission with `presetId="review_photo"` — guaranteeing the same validation/UX customers and admins get. The storefront's duplicate `components/cms/ImageUploadField.tsx` (flagged by the Audit as a leftover copy of the admin component with unconfirmed usage) is deleted outright.
- **`ImageWithFallback`'s successor is mandatory, not optional** (closes G15): `shared-media` exports `<ResponsiveImage>`, a wrapper around `packages/shared-ui`'s existing `ImageWithFallback` that additionally emits `srcSet`/`sizes` from an `ImageBundle` (§13). It is the *only* sanctioned way to render a URIS-managed image; an ESLint custom rule (`no-raw-img-for-uris-assets`) ships in the same phase that rolls out `<ResponsiveImage>` (not deferred to a later "hardening" phase) to prevent any raw `<img>` regression across `storefront/src` from day one.
- **State management:** the editor is a local, self-contained component (React state + one `useCropGeometry` reducer-hook) — no global store needed; it talks to the backend only via the `presetClient`/upload endpoints in `shared-api`.
- **Where types live:** `CropPreset`, `CropGeometry`, `ImageBundle`, `ImageAsset` contracts live in `packages/shared-types/src/media.ts` (new file), shared by `shared-media` (editor), `shared-api` (data fetching/mappers), and both apps' route/page code — replacing the Audit's flagged duplicate `ImageUploadField.tsx` file between admin and storefront trees and the informal per-view URL-picking logic in `mappers.ts`.

---

## 12. Storage Architecture

**One R2 key convention, used by every module from day one** (replaces the 5 divergent patterns cataloged in Audit §6):

```
images/
├── {module}/{owner_type}/{owner_id}/{image_id}/
│   ├── original.{ext}                          ← immutable, never regenerated from
│   └── {breakpoint}/{variant_name}@{dpr}x.webp  ← e.g. desktop/hero@2x.webp, all/thumbnail@1x.webp
│                                                    (…@1x.png for the one documented print-variant exception, §6.9)
```

Concretely: `images/hero/banner/8f2c.../a91e.../desktop/hero@2x.webp`, `images/product/product/{product_id}/{image_id}/all/medium@1x.webp`, `images/avatar/user/{user_id}/{image_id}/all/avatar@1x.webp`.

- **Original preservation:** universal invariant — `original.{ext}` is written exactly once per `image_id` (on upload or explicit Replace) and is the *only* file ever read as crop input; every variant regeneration re-derives from it. This generalizes today's Product-only guarantee to every module, with no exception.
- **UUID-scoped keys everywhere:** closes G7 (Review images' unsanitized-filename risk) and G9 (Avatar's fixed-key staleness) — every module gets a fresh `image_id` per upload/replace, so the key itself changes and old CDN cache entries naturally age out.
- **Cache-Control (closes G8):** `storage.py`'s single `put_object` wrapper always sets `CacheControl: public, max-age=31536000, immutable` on variant files (content-addressed by `image_id`+`version`, truly immutable once written) and `CacheControl: private, max-age=0, must-revalidate` on `original.*`.
- **Versioning/cache-busting:** every served URL appends `?v={images.version}` at serialization time via one shared serializer helper (not reimplemented per module).
- **Deletion:** `storage.py.delete_image_folder()` performs `list_objects_v2` + `delete_objects`, but replaces every `except: pass` with: log at `ERROR` with `image_id`/`key_prefix`, mark the `images` row `status='archived'` with a `deletion_pending=true` flag instead of hard-deleting the DB row immediately, and enqueue a retry via `background.py`. A row is only fully purged once R2 confirms the delete succeeded — eliminating the "DB row gone, R2 orphaned" failure mode (closes G12).

There is no presigned direct-upload key convention (§10 deletes that path).

---

## 13. Metadata Design

`images.metadata` JSONB (validated server-side against a Pydantic model before persist, not freeform):

```json
{
  "preset_id": "hero",
  "preset_version": 3,
  "shape": "rectangle",
  "focus_point": { "x": 0.42, "y": 0.55 },
  "safe_area": { "top": 0, "right": 0, "bottom": 20, "left": 45 },
  "original_dimensions": { "width": 4032, "height": 3024 },
  "crops": {
    "desktop": {
      "aspect_ratio": 2.743,
      "box": { "x": 120, "y": 0, "width": 3792, "height": 1382 },
      "zoom": 1.4,
      "pan": { "x": 12, "y": -8 },
      "rotation": 0
    },
    "tablet":  { "aspect_ratio": 1.463, "box": { "x": 640, "y": 200, "width": 2100, "height": 1435 }, "zoom": 1.1, "pan": {"x":0,"y":0}, "rotation": 0 },
    "mobile":  { "aspect_ratio": 0.65,  "box": { "x": 1400, "y": 0, "width": 1400, "height": 2154 }, "zoom": 1.0, "pan": {"x":0,"y":0}, "rotation": 0 }
  },
  "generated_variants": [
    { "breakpoint": "desktop", "name": "hero", "dpr": 1, "url": "…", "width": 1920, "height": 700 },
    { "breakpoint": "desktop", "name": "hero", "dpr": 2, "url": "…", "width": 3840, "height": 1400 },
    { "breakpoint": "tablet",  "name": "hero", "dpr": 1, "url": "…", "width": 1024, "height": 700 },
    { "breakpoint": "mobile",  "name": "hero", "dpr": 1, "url": "…", "width": 390,  "height": 600 }
  ],
  "last_edited_by": "profile-uuid",
  "last_edited_at": "2026-07-08T10:15:00Z",
  "version": 3
}
```

(`generated_variants` is a denormalized read-cache of `image_variants` rows for fast single-query API responses; `image_variants` remains the queryable source of truth.) The `ImageBundle` shape returned in owner-entity API responses (Product/Collection/Banner/etc.) is a slimmed projection of this: `{ alt_text, focus_point, variants: [{breakpoint, dpr, url, width, height}] }`, which is exactly what `<ResponsiveImage>` needs to build `srcSet`/`sizes` without any extra request.

---

## 14. Component Hierarchy

```
<UniversalImageEditor presetId ownerType ownerId existingImageId? onSaved>
├── <UploadDropzone>                          (shown when no image yet, or "Replace" clicked)
├── <PresetBanner>                             (shows locked preset label/shape/ratio — read-only, from registry)
├── <CropCanvas>                                (shared-media, wraps react-easy-crop + shape mask overlay)
│   ├── <ShapeMaskOverlay>                      (rectangle/square/circle/rounded/custom SVG clip-path)
│   ├── <SafeAreaOverlay>
│   ├── <ZoomSlider> / <RotationSlider>
│   └── <BreakpointTabs>                        (Desktop | Tablet | Mobile — only if preset.breakpoints.length > 1)
├── <PreviewPane>
│   ├── <PreviewFrame breakpoint="desktop">      (real-UI chrome from previewChrome/{reference_ui}.tsx)
│   ├── <PreviewFrame breakpoint="tablet">
│   └── <PreviewFrame breakpoint="mobile">
├── <VariantStatusBadge>                         (pending/ready/failed per variant, post-save)
└── <ActionBar>  [Cancel] [Save & Generate Variants]
```

Every consuming call site (`ProductForm.tsx`, `CollectionForm.tsx`, `admin.cms.index.tsx` Hero/Banner blocks, the new Company/SEO settings screen, storefront Account/Review forms) renders exactly one `<UniversalImageEditor>` instance per image slot — no wrapping bespoke logic beyond passing `presetId`/`ownerType`/`ownerId` and handling `onSaved`.

Rendering side (storefront + admin lists):
```
<ResponsiveImage imageBundle fallbackSrc? sizes? priority?>
└── <ImageWithFallback>  (packages/shared-ui, now used by both apps, not admin-only)
    └── <picture> / <img srcSet sizes loading fetchPriority>
```

---

## 15. Sequence Diagrams

### Upload flow
```
Admin           UniversalImageEditor        POST /admin/media/{preset}/upload      UniversalImageService        R2            DB
  │ pick file  ────────>│                              │                                  │                       │             │
  │                     │ client-side dimension/type   │                                  │                       │             │
  │                     │ pre-check (fast fail)         │                                  │                       │             │
  │                     │────────multipart─────────────>│                                  │                       │             │
  │                     │                              │ validate(preset.storage_rules)   │                       │             │
  │                     │                              │─────────────────────────────────>│                       │             │
  │                     │                              │                                  │ put original.{ext}   │             │
  │                     │                              │                                  │──────────────────────>│             │
  │                     │                              │                                  │ default-crop variants │             │
  │                     │                              │                                  │──────────────────────>│             │
  │                     │                              │                                  │ INSERT images, image_variants        │
  │                     │                              │                                  │──────────────────────────────────────>│
  │                     │<──────image_id, status=ready──────────────────────────────────────────────────────────────────────────│
  │  <── shows default crop, opens Crop step ──────────│                                  │                       │             │
```

### Re-edit flow
```
Admin opens existing image → GET /admin/media/{id} (or embedded in owner fetch)
      │ returns images.metadata.crops + original_dimensions (NOT a derived variant)
      ▼
CropCanvas seeds from stored CropGeometry per breakpoint
      │ admin adjusts zoom/pan/box on e.g. "mobile" tab only
      ▼
PATCH /admin/media/{id}/crop   { crops: { mobile: {...} } }
      │
      ▼
UniversalImageService:
   fetch original.{ext} from R2 (untouched)  ← never reads a prior variant
   crop_engine.apply(original, geometry.mobile, preset)
   variant_generator.generate(only mobile-scoped variants)
   put mobile/*.webp to R2 (new files, since key includes image_id — version bump handles cache-bust)
   UPDATE images SET metadata=..., version=version+1
   UPSERT image_variants (breakpoint='mobile', ...)
      ▼
Response: updated ImageBundle → editor refreshes Mobile PreviewFrame only
```

### Variant generation flow (background path, e.g. Hero with 6 artifacts)
```
PATCH /crop or POST /upload (large preset)
      │
      ▼
service.py: persist images row (status='pending'), enqueue background.generate_variants(image_id)
      │                                                    │
      ▼ (HTTP 202 returned immediately)                    ▼
Admin UI polls GET /admin/media/{id}                    background task:
      │                                                    for each (breakpoint, variant, dpr) in preset.output_variants:
      │                                                      crop_engine.apply(...)
      │                                                      try: put_object(...) ; INSERT image_variants(status='ready')
      │                                                      except: INSERT image_variants(status='failed', error_message=...)
      │                                                             log.error(...); schedule retry (max 3, backoff)
      │                                                    when all variants terminal: UPDATE images SET status = 'ready' | 'failed'
      ▼
VariantStatusBadge shows per-tile ready/failed, "Retry" action available per failed variant
```

---

## 16. Legacy Components to Remove

Every file, service, API, table, component, helper, storage convention, and workflow that this replacement deletes. Nothing in this list is "deprecated" or "kept for compatibility" — everything here is deleted in the release that ships §17's cutover phase.

| # | Current Location | Why It Exists Today | Why It Becomes Obsolete | Replacement | Safe Deletion Order |
|---|---|---|---|---|---|
| 1 | `Backend/app/modules/media/service.py` (`MediaService`) | Product/Collection/Category upload, crop, variant generation, avatar upload, raw byte pass-through for reviews | Fully absorbed and generalized by `UniversalImageService` | `Backend/app/modules/media/service.py` (rewritten as `UniversalImageService`) | After all callers (router endpoints, `profiles`, `reviews`) are repointed — step 3 of §17 |
| 2 | `Backend/app/modules/media/router.py` (existing endpoint set) | Product image CRUD/crop/reorder-less endpoints, Collection/Category cover endpoints | Replaced by preset-parameterized universal endpoints (§10) | New `media/router.py` | Same commit as #1 |
| 3 | `Backend/app/modules/cms/media_service.py` (`CmsMediaService`) | Hero/Banner/Instagram/Footer/Testimonial upload with separate 50 MB/broader-MIME validation, single 400×400 thumbnail | Duplicate R2 client + validation logic; single-tier variants insufficient for responsive delivery | `UniversalImageService` with per-module presets (§6.4–6.9) | Step 3 of §17, alongside #1 |
| 4 | `Backend/app/modules/cms/router.py` media endpoints (`/cms/admin/media/upload`, `GET/PATCH/DELETE /admin/media*`) | CMS media library CRUD | Superseded by universal `/admin/media/*` endpoints | `media/router.py` universal endpoints | Same commit as #3 |
| 5 | `profiles/router.py`'s avatar-processing code path (calls into `MediaService.upload_avatar`) | Fixed-key 400×400 avatar upload, no validation call | Generalized into `avatar` preset with UUID-scoped keys and real validation | `POST /admin/media/avatar/upload` (or storefront-facing equivalent) via `UniversalImageEditor presetId="avatar"` | Step 4 of §17 |
| 6 | `reviews/service.py`'s `_attach_images` image-handling code (raw byte pass-through, unsanitized filenames) | Zero-processing review photo storage | Fully unsafe (G7) and inconsistent with every other module; replaced by `review_photo` preset with server-generated UUID keys and real validation | `UniversalImageService.upload(preset_id="review_photo")` | Step 4 of §17 |
| 7 | `Backend/app/modules/media/service.py::_get_r2_client`, `cms/media_service.py::_r2` (duplicate R2 client constructors) | Two near-identical boto3 client instantiations | Single client belongs in one place | `media/storage.py::R2Client` (single instantiation) | Step 3 of §17 |
| 8 | `Backend/app/modules/media/service.py::_public_url`, `cms/media_service.py`'s duplicate | Two near-identical public-URL builders | Single builder belongs in one place | `media/storage.py`'s URL builder | Step 3 of §17 |
| 9 | `MediaService.get_presigned_upload_url` (`media/service.py:376-389`) | Unaudited direct-to-R2 presigned-upload path, no confirmed caller (Audit G13) | No caller found; multipart upload comfortably covers every preset's size limits | None — deleted outright, not replaced (§10) | Step 3 of §17 |
| 10 | `Backend/alembic`-managed `product_images` table | Product gallery storage w/ crop metadata | Fully absorbed by `images`/`image_variants` with `owner_type='product'` | `images` + `image_variants` | Dropped in the cutover migration (§17 step 2) |
| 11 | `cms_media` table | CMS media library storage | Fully absorbed by `images`/`image_variants` with `owner_type IN ('banner','cms_section_item')` | `images` + `image_variants` | Dropped in the cutover migration |
| 12 | `collections.image_url`, `categories.image_url` columns | Single large-variant URL string | Replaced by `primary_image_id` FK + full `ImageBundle` (all tiers, all breakpoints) | `collections.primary_image_id`, `categories.primary_image_id` | Dropped in the cutover migration |
| 13 | `banners.desktop_image_url`, `banners.mobile_image_url` columns | Two-column desktop/mobile image pattern | Replaced by one `primary_image_id` FK to a `promo_banner`-preset image carrying both breakpoints natively | `banners.primary_image_id` | Dropped in the cutover migration |
| 14 | `profiles.avatar_url` column | Fixed-key avatar URL string | Replaced by `profiles.primary_image_id` (or `owner_type='user'` row) | `profiles.primary_image_id` | Dropped in the cutover migration |
| 15 | `review_images` table | Raw, unprocessed review photo storage | Fully absorbed by `images`/`image_variants` with `owner_type='review'` | `images` + `image_variants` | Dropped in the cutover migration |
| 16 | `company_config.logo_url`, `.packing_slip_logo_url`, `.shipping_label_logo_url`, `.logo_r2_key` columns | Plain string fields, no upload endpoint, admin pastes CDN URL | Replaced by `company_logo`/`footer_logo` presets with real upload+crop | `company_config.primary_image_id` (+ a second FK if packing-slip/shipping-label logos are meant to differ from the web logo) | Dropped in the cutover migration |
| 17 | `seo_pages.og_image` column (raw SQL table) | Plain string field, no upload endpoint | Replaced by `seo_og` preset with real upload+crop | `seo_pages.primary_image_id` | Dropped in the cutover migration |
| 18 | `Backend/app/modules/fulfillment/service.py:418-435` (`httpx.get` live logo fetch at PDF-generation time) | Fetches `company_config.logo_url` over HTTP with a 5s timeout and silent fallback | Replaced by a pre-generated `print` variant read directly from `image_variants` — no HTTP round-trip, no timeout risk, no silent fallback needed | `image_variants` lookup for `variant_name='print'` on the company logo's `image_id` | Step 4 of §17, after `company_logo` preset is live |
| 19 | `admin/src/components/admin/ImageUpload.tsx` | Category/Collection single-image dropzone, simulated progress bar, no crop | Replaced entirely by `<UniversalImageEditor>` | `packages/shared-media/.../UniversalImageEditor.tsx` | Step 5 of §17, once `CollectionForm.tsx`/`CategoryForm.tsx` are repointed |
| 20 | `admin/src/components/admin/products/ImageCropModal.tsx` | Product-only `react-easy-crop` wrapper, 1:1 aspect, no responsive breakpoints | Replaced by the same `<UniversalImageEditor>` used everywhere else | `UniversalImageEditor` (`presetId="product"`) | Step 5 of §17, once `ProductForm.tsx` is repointed |
| 21 | `admin/src/components/cms/ImageUploadField.tsx` | Generic CMS upload-or-paste-URL field (Hero, Banner, Instagram, Footer, Testimonial, Video poster) with the raw-URL-paste escape hatch (G5) | Replaced by `<UniversalImageEditor>`; the raw-URL text input has no equivalent — pasting is removed as a capability, not just hidden | `UniversalImageEditor` per relevant `presetId` | Step 5 of §17, once `admin.cms.index.tsx` is repointed |
| 22 | `storefront/src/components/cms/ImageUploadField.tsx` (duplicate of #21) | Unconfirmed leftover copy of the admin component in the storefront tree | No confirmed storefront authoring UI depends on it; a `<UniversalImageEditor>` instance is dropped in directly if storefront-side CMS authoring is ever confirmed needed | `UniversalImageEditor` (only if a genuine use is confirmed) | Step 5 of §17 |
| 23 | `admin/src/components/admin/products/ProductForm.tsx`'s crop-queue orchestration (`enqueueCrop`, `applyPendingCrop`, `handleCropSave`, lines ≈2453-2726 per the Audit) | Product-specific sequential upload+crop state machine | `<UniversalImageEditor>` owns this state internally via `useCropGeometry` | `UniversalImageEditor`'s internal state machine | Step 5 of §17 |
| 24 | `storefront/src/lib/api/mappers.ts`'s per-view URL-picking logic (`mediumOf`, `largeOf`, hardcoded `image_url`/`primary_image` field selection) | Manual "pick one URL for this context" logic per view type | `ImageBundle` + `<ResponsiveImage>` select the correct variant per viewport automatically | `packages/shared-types/src/media.ts` (`ImageBundle`) + `<ResponsiveImage>` | Step 6 of §17, alongside the storefront rendering rollout |
| 25 | Every raw `<img>` tag in `storefront/src` rendering a URIS-managed image (`ProductCard.tsx`, `Hero.tsx`, `FeaturedCollection.tsx`, `PromoBanner.tsx`, `ShopByCategory.tsx`, `InstagramSection.tsx`, cart/checkout/wishlist/account thumbnails — 36 occurrences per the Audit's grep) | Hand-rolled, inconsistent loading/error handling, hardcoded intrinsic dimensions, no `srcSet` | Replaced by `<ResponsiveImage>`, enforced by the `no-raw-img-for-uris-assets` ESLint rule | `<ResponsiveImage>` | Step 6 of §17 |
| 26 | Storage convention: `products/{id}/{uuid}/{original,thumbnail,medium,large}`, `collections/{id}/{uuid}/...`, `categories/{id}/{uuid}/...`, `{cms_folder}/{media_id}.{ext}` + `_thumb.webp`, `avatars/{user_id}/avatar.webp` (fixed key), `reviews/{review_id}/{i}_{filename}` (raw filename) | Five divergent R2 key patterns (Audit §6) | Replaced by the single `images/{module}/{owner_type}/{owner_id}/{image_id}/...` convention (§12) | Unified R2 key convention | Old objects deleted from R2 once new uploads confirmed working, per §17 step 7 |
| 27 | Alembic migrations `0031_product_image_crop_metadata`, `0032_product_image_large_url_and_version` (schema they created) | Product-only crop metadata and cache-busting columns | Superseded by the universal `images.metadata`/`images.version` columns | New migration creating `images`/`image_variants` | The columns these migrations added are dropped along with `product_images` itself (#10) |

**Not removed — intentionally out of scope:** `order_items.image_url` (Migration `0011_order_item_image_url.py`) remains exactly as-is. It is a system-generated, immutable snapshot copied at order-creation time (not an upload path, not a live pipeline), and generalizing it would add complexity without benefit — orders must keep showing the image as it looked at purchase time even if the product's current image is later replaced. At order-creation time the order-service simply resolves the product's current `ImageBundle` and copies one variant URL into `order_items.image_url`, exactly as it does today against `product_images`.

---

## 17. Replacement Strategy

This is a **build → cutover → delete** sequence, not a gradual migration. Every phase after Phase 0 makes the new system more complete; the single Cutover phase (Phase 3) is where the old system is deleted in its entirety, in one release. There is no phase where both pipelines serve real traffic simultaneously — Phase 2 exercises the new pipeline against seed/test data only, behind a feature branch, before cutover.

### Phase 0 — Foundation (backend only, no visible change, ~1–2 sprints)
- **Built:** `images`/`image_variants` tables (new migration, additive only at this stage — old tables untouched yet), `preset_registry.py` with all 13 presets from §6, `crop_engine.py` with unit tests, `variant_generator.py` (WebP-only, per §8), unified `storage.py` with Cache-Control (closes G8/G11), `validation.py`.
- **Removed:** nothing yet — this phase is purely additive so the new system can be built and tested in isolation.
- **DB tables dropped:** none yet.
- **APIs removed:** none yet.
- **Frontend components deleted:** none yet.
- **Storage conventions retired:** none yet.

### Phase 1 — Shared Frontend Component (~1–2 sprints)
- **Built:** `packages/shared-media` scaffolded; `<UniversalImageEditor>` + `<CropCanvas>` + `<PreviewFrame>` built and validated against the `product` and `hero` presets specifically (the two extremes: single-breakpoint square vs. triple-breakpoint rectangle with safe areas), running against the Phase 0 backend in a dev/staging environment only.
- **Removed:** nothing in production code yet.
- **DB tables dropped:** none.
- **APIs removed:** none.
- **Frontend components deleted:** none.

### Phase 2 — Full Coverage Build-Out (~2–3 sprints)
- **Built:** every remaining preset from §6 wired end-to-end; `UniversalImageService` endpoints (§10) fully implemented for all 13 presets; `<ResponsiveImage>` component built; ESLint `no-raw-img-for-uris-assets` rule authored (not yet enforced repo-wide); background-task variant generation (§8) implemented and tested for Hero/Banner-scale artifact counts.
- **Removed:** nothing in production code yet — this phase is still additive, running the new system against seed data in a branch/staging environment so the entire surface area is proven correct before anything old is touched.
- **DB tables dropped:** none.
- **APIs removed:** none.
- **Frontend components deleted:** none.

### Phase 3 — Cutover (single release, ~1 sprint, the only phase with a maintenance window)
This is the phase where everything in §16 is deleted, all at once, in one coordinated release:
1. **New components built:** none — Phase 3 ships zero new capability, it only cuts over to what Phases 0–2 already built.
2. **Old components removed:** `MediaService`, `CmsMediaService`, `profiles.upload_avatar`'s Pillow/R2 code, `reviews._attach_images`'s image-handling code, `get_presigned_upload_url`, duplicate `_get_r2_client`/`_public_url` implementations (§16 items 1–9).
3. **DB tables/columns dropped, in one migration:** `product_images`, `cms_media`, `review_images` tables; `collections.image_url`, `categories.image_url`, `banners.desktop_image_url`, `banners.mobile_image_url`, `profiles.avatar_url`, `company_config.logo_url`/`.packing_slip_logo_url`/`.shipping_label_logo_url`/`.logo_r2_key`, `seo_pages.og_image` columns (§16 items 10–18). New `primary_image_id` FK columns are added to the surviving owner tables in the same migration.
4. **APIs removed:** every endpoint in `cms/router.py`'s media section, `media/router.py`'s pre-universal endpoint set, `profiles/router.py`'s avatar-specific Pillow path, `reviews/router.py`'s unvalidated image acceptance (§16 items 2, 4, 5, 6).
5. **Frontend components deleted:** `ImageUpload.tsx`, `ImageCropModal.tsx`, `ImageUploadField.tsx` (both admin and storefront copies), `ProductForm.tsx`'s crop-queue orchestration code, `mappers.ts`'s per-view URL-picking logic, every raw `<img>` call site rendering a URIS-managed image (§16 items 19–25) — all call sites are repointed to `<UniversalImageEditor>`/`<ResponsiveImage>` in the same commits that delete the old components, not left broken in between.
6. **Storage conventions that disappear:** all five legacy R2 key patterns (§16 item 26) — new uploads only ever use the unified `images/{module}/{owner_type}/{owner_id}/{image_id}/...` layout from this release forward.
7. **One-time dev-seed re-upload/re-crop:** since there is no production data, whatever dev/staging seed images exist for Products, Collections, Categories, Hero, Banners, CMS sections, Avatars, and Reviews are re-uploaded and re-cropped by hand through the new `<UniversalImageEditor>` as part of this release's QA pass — this is simpler and higher-quality than writing a one-time backfill/transform script for data that has no durability requirement. Old R2 objects under the legacy key patterns are deleted once the new uploads are confirmed rendering correctly everywhere (cart, PDP, admin lists, PDFs).
8. **Code that becomes obsolete and is deleted, not just unused:** `fulfillment/service.py`'s live `httpx.get` logo fetch (§16 item 18) is replaced with a direct `image_variants` lookup in this same phase.

At the end of Phase 3 there is exactly **one** image pipeline in the codebase. `git grep` for `MediaService`, `CmsMediaService`, `product_images`, `cms_media`, `ImageCropModal`, `ImageUploadField` returns zero results outside of the migration history and this document.

### Phase 4 — Hardening (~1 sprint)
- **Built:** structured logging/alerting around variant failures and R2 delete failures (extends §8/§12's per-item status tracking with actual paging/alert wiring); CDN preconnect (`<link rel="preconnect" href="https://cdn.hadha.co">` in `__root.tsx`, alongside the existing Google Fonts preconnects) and `fetchPriority="high"` on the PDP's primary `ProductImageViewer` image (closes G16's LCP gap); `POST /admin/media/{id}/regenerate` exercised as a bulk tool for any preset-wide resolution changes discovered during QA.
- **Removed:** nothing further — by this point §16's inventory is fully deleted; this phase is pure polish on the one remaining pipeline.
- **DB tables dropped:** none (already done in Phase 3).
- **APIs removed:** none (already done in Phase 3).

**Tooling note carried over from v1 and still relevant:** to prevent `preset_registry.py` (Python) and `imagePresets.ts` (TypeScript) from drifting, Phase 0 should include a build-time codegen step (Python model → JSON Schema → TS types) rather than hand-maintaining both — this is a one-time tooling decision, not a migration-phase hedge, so it belongs in Phase 0 regardless of the replacement-vs-migration framing.

---

## 18. Risks

Because this is a replacement, not a migration, the risk profile is materially different from v1 — there is no "which old service breaks if the migration stalls" category of risk, because there is no partial state to stall in. The risks that remain:

- **Cutover is a single coordinated release, not a rolling change.** Phase 3 touches backend endpoints, database schema, and every frontend upload/render call site simultaneously. Mitigation: Phases 0–2 fully build and prove the new system against seed data in a branch/staging environment first, so Phase 3 is a repoint-and-delete operation on already-working code, not first-time integration under a deadline.
- **One-time re-upload/re-crop effort for existing dev-seed data.** Someone has to manually re-upload and re-crop every seed Product/Collection/Category/Hero/Banner/CMS-section/Avatar/Review image through the new editor during Phase 3 QA. This is bounded, known work (the current dev-seed image count is small, pre-production) — not an open-ended migration risk, but it should be scoped and time-boxed before Phase 3 starts so it isn't discovered as a surprise mid-cutover.
- **No rollback path once Phase 3's DB migration runs.** Since old tables/columns are dropped, not soft-retired, rolling back after Phase 3 means restoring from a pre-migration DB snapshot, not toggling a flag. Mitigation: take an explicit DB snapshot immediately before running the Phase 3 migration (standard practice regardless, but worth calling out since there is deliberately no "old table still there as a fallback" safety net by design).
- **Preset drift between backend and frontend** if `packages/shared-types`' TS preset definitions and `preset_registry.py`'s Python definitions are hand-kept-in-sync rather than generated from one schema. Addressed by the Phase 0 codegen tooling decision (§17).
- **Admin retraining.** Every upload surface's UI changes simultaneously across many screens in one release, including Collections/Categories admins who gain a crop step they've never had before. Requires coordinated release notes/training timed to Phase 3, not spread across a long migration window.
- **Increased storage volume.** More variants per image (2x DPR everywhere, all three tiers persisted for Collections/Categories instead of one) increases R2 storage and egress versus today — should be estimated against current bucket size before Phase 0 sign-off, same as v1 flagged, but now against a smaller baseline since there's no need to keep legacy objects around after Phase 3's cleanup.
- **Circular/masked shapes and PDF logo consumption.** The `company_logo`'s `print` variant replacing `fulfillment/service.py`'s live `httpx.get` fetch (§16 item 18) needs the regenerate endpoint (§8) wired correctly so a logo re-upload actually refreshes the cached print asset — this is a functional-correctness risk to test explicitly in Phase 3/4, not a migration-window risk.

---

## 19. Future Extensions

- **AVIF as the default or secondary format**, once broader browser/tooling support and encode-cost tradeoffs are evaluated. This is a genuinely deferred feature, not a hedge shipped-and-disabled — adopting it means adding a value to `image_variants.format` and a generation step in `variant_generator.py`, no schema changes needed.
- **3x DPR tier** for ultra-high-density displays — the `image_variants.dpr` column already accommodates it; a future decision, not a flag baked into Phase 0.
- **Custom SVG mask shapes** beyond Circle/RoundedRect (e.g. brand-specific blob shapes) — `ShapeType.CUSTOM_MASK` + `mask_svg` are already part of the Preset schema (§5); needs an admin-facing mask picker.
- **AI-assisted focus point detection** (face/subject detection to pre-seed `focus_point` on upload) — the schema already isolates `focus_point` from any single crop box, making this a drop-in enhancement to the upload step without touching the crop/variant pipeline.
- **Bulk re-crop / bulk regenerate tooling** for org-wide preset changes (e.g. changing Hero's target resolution) — the idempotent `POST /admin/media/{id}/regenerate` endpoint (§10) is the primitive; a bulk-job wrapper is a natural addition once volume justifies it.
- **Video support**, currently a gap this design does not address (the old `CmsMediaService` handled video ad hoc for Instagram/hero posters, and that capability is not reintroduced here) — could be formalized later as a parallel `VideoPreset` family reusing the same registry pattern.
- **Team/Blog/About modules** — presets already defined (§6.13); implementing these pages becomes a pure "attach `owner_type`" exercise with zero new image infrastructure (directly closes Audit G17 by design).
- **Per-tenant/white-label preset overrides**, if Hadha.co ever needs brand variants — the registry's code-defined nature makes this a natural place to introduce environment- or tenant-scoped overrides later.
- **Proper background task queue** (RQ/Celery) if variant generation volume outgrows FastAPI `BackgroundTasks` — the background-task interface in `media/background.py` is written so the underlying execution mechanism can be swapped without changing callers.

---

### Critical Files for Implementation

- `Backend/app/modules/media/preset_registry.py` (new) — the Crop Preset Registry; every module's behavior derives from entries here.
- `Backend/app/modules/media/crop_engine.py` (new) — pure crop/rotate/mask geometry math shared by preview (TS port) and server-side generation.
- `Backend/alembic/versions/0034_universal_images_schema.py` (new) — creates `images`/`image_variants`, adds `primary_image_id` FK columns, **and drops** `product_images`, `cms_media`, `review_images`, and the legacy URL columns listed in §16 — a single migration that both builds and tears down, run at Phase 3 cutover, not split across a migration window.
- `Frontend_whole/packages/shared-media/src/UniversalImageEditor/UniversalImageEditor.tsx` (new) — the single upload/crop/preview component every admin (and relevant storefront) screen consumes.
- `Frontend_whole/packages/shared-types/src/media.ts` (new) — canonical `CropPreset`/`CropGeometry`/`ImageBundle` contracts shared by backend codegen and both frontend apps.
- `Backend/app/modules/media/service.py` (rewrite) — `UniversalImageService`, the orchestration layer replacing `MediaService` + `CmsMediaService` entirely, not alongside them.

**Biggest architectural decision, restated for the replacement framing:** v1 asked "how do we let two universal tables coexist with four legacy pipelines during a transition window, and how long can `image_url` keep working for old readers?" This document asks a simpler question because the constraint that produced v1's complexity — protecting live traffic during a gradual cutover — does not exist here. The decision is: **build the complete replacement first, prove it against seed data, then delete every legacy table, service, endpoint, and component in one coordinated release.** The result is not "two universal tables plus compatibility scaffolding," it is **two universal tables, full stop** — `images` and `image_variants`, with nothing else in the schema representing an image, anywhere, for any module, ever again.
