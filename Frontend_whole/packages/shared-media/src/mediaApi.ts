import { api } from "@hadha/shared-api";
import type { Breakpoint, CropGeometry, ImageBundle } from "@hadha/shared-types";

/**
 * Appends a one-off nonce to *url* so the browser treats it as a resource
 * it has never seen, regardless of the server's own `?v=` cache-buster.
 * Used specifically when swapping in a thumbnail right after the
 * background worker finishes generating it (`pollImageUntilReady`
 * resolved) — belt-and-suspenders against any intermediate cache (a CDN
 * configured to ignore query strings, a proxy, etc.) that might otherwise
 * still serve bytes cached under an earlier `?v=` during the brief window
 * between "pending" and "ready" (docs audit CB-1 Phase 2 cache-busting fix).
 * Never persisted — only applied to the URL handed to an `<img src>` for
 * this one render.
 */
export function bustCacheUrl(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}cb=${Date.now()}`;
}

/** Raw shape of Backend/app/modules/media/schemas.py's ImageVariantOut/ImageOut (snake_case). */
interface ImageVariantOutRaw {
  id: string;
  breakpoint: string;
  variant_name: string;
  dpr: number;
  format: string;
  url: string;
  width: number;
  height: number;
  status: string;
  error_message: string | null;
}

export interface ImageOutRaw {
  id: string;
  module: string;
  preset_id: string;
  owner_type: string;
  owner_id: string | null;
  original_ext: string;
  original_width: number;
  original_height: number;
  /** The untouched original upload — always what the crop editor should
   * re-open against, never a generated variant. */
  original_url: string;
  alt_text: string | null;
  status: string;
  version: number;
  sort_order: number;
  is_primary: boolean;
  metadata: {
    focus_point: { x: number; y: number };
    crops: Record<string, unknown>;
  };
  variants: ImageVariantOutRaw[];
  created_at: string;
  updated_at: string;
}

/** Converts a backend ImageOut response into the ImageBundle shape ResponsiveImage consumes. */
export function toImageBundle(image: ImageOutRaw): ImageBundle {
  return {
    imageId: image.id,
    altText: image.alt_text,
    focusPoint: image.metadata.focus_point,
    variants: image.variants
      .filter((v) => v.status === "ready")
      .map((v) => ({
        breakpoint: v.breakpoint as Breakpoint,
        dpr: v.dpr,
        url: v.url,
        width: v.width,
        height: v.height,
      })),
  };
}

/** GET /admin/media/{image_id} — full current state (original_url, crop
 * metadata, variants) for one image. The "Edit Crop" flow calls this to
 * always re-open the editor against the untouched original plus the
 * previously-saved crop geometry, instead of trusting a variant URL that
 * happens to be cached in the caller's local UI state. */
export async function getImage(imageId: string): Promise<ImageOutRaw> {
  return api.get<ImageOutRaw>(`/admin/media/${imageId}`);
}

export class ImageGenerationFailedError extends Error {
  constructor(imageId: string) {
    super(`Variant generation failed for image ${imageId}`);
    this.name = "ImageGenerationFailedError";
  }
}

export class ImageGenerationTimeoutError extends Error {
  constructor(imageId: string) {
    super(`Timed out waiting for variant generation for image ${imageId}`);
    this.name = "ImageGenerationTimeoutError";
  }
}

/**
 * Polls GET /admin/media/{id} until the background variant-generation
 * worker (docs audit CB-1 Phase 2) finishes. crop/upload/replace/regenerate
 * now return as soon as the "pending" status + crop metadata are persisted
 * — well before real variants exist — so any caller that needs to know
 * when generation has actually *finished* (to refresh a stale thumbnail, or
 * show a "Generating…" indicator) polls this instead of trusting the
 * initial response's variant list.
 */
export async function pollImageUntilReady(
  imageId: string,
  { intervalMs = 1500, timeoutMs = 30_000 }: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<ImageOutRaw> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const raw = await getImage(imageId);
    if (raw.status === "ready") return raw;
    if (raw.status === "failed") throw new ImageGenerationFailedError(imageId);
    if (Date.now() >= deadline) throw new ImageGenerationTimeoutError(imageId);
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

/** POST /admin/media/{preset_id}/upload */
export async function uploadImage(params: {
  presetId: string;
  file: File;
  ownerType: string;
  ownerId?: string;
}): Promise<ImageOutRaw> {
  const form = new FormData();
  form.append("file", params.file);
  const search = new URLSearchParams({ owner_type: params.ownerType });
  if (params.ownerId) search.set("owner_id", params.ownerId);
  return api.upload<ImageOutRaw>(`/admin/media/${params.presetId}/upload?${search}`, form);
}

/** PATCH /admin/media/{image_id}/crop */
export async function cropImage(imageId: string, geometry: CropGeometry): Promise<ImageOutRaw> {
  const crops = Object.fromEntries(
    Object.entries(geometry.crops).map(([bp, g]) => [
      bp,
      {
        box: g!.box,
        zoom: g!.zoom,
        pan: g!.pan,
        rotation: g!.rotation,
      },
    ]),
  );
  return api.patch<ImageOutRaw>(`/admin/media/${imageId}/crop`, {
    body: { crops, focus_point: geometry.focusPoint },
  });
}

/** PUT /admin/media/{image_id}/replace */
export async function replaceImage(imageId: string, file: File): Promise<ImageOutRaw> {
  const form = new FormData();
  form.append("file", file);
  return api.put<ImageOutRaw>(`/admin/media/${imageId}/replace`, { body: form });
}

/** PATCH /admin/media/{image_id}/attach */
export async function attachImage(
  imageId: string,
  ownerType: string,
  ownerId: string,
): Promise<ImageOutRaw> {
  return api.patch<ImageOutRaw>(`/admin/media/${imageId}/attach`, {
    body: { owner_type: ownerType, owner_id: ownerId },
  });
}

/** PATCH /admin/media/reorder */
export async function reorderImages(
  ownerType: string,
  ownerId: string,
  items: { imageId: string; sortOrder: number }[],
): Promise<void> {
  await api.patch(`/admin/media/reorder`, {
    body: {
      owner_type: ownerType,
      owner_id: ownerId,
      items: items.map((i) => ({ image_id: i.imageId, sort_order: i.sortOrder })),
    },
  });
}

/** PATCH /admin/media/{image_id}/set-primary */
export async function setPrimaryImage(imageId: string): Promise<ImageOutRaw> {
  return api.patch<ImageOutRaw>(`/admin/media/${imageId}/set-primary`);
}

/** DELETE /admin/media/{image_id} */
export async function deleteImage(imageId: string): Promise<void> {
  await api.delete(`/admin/media/${imageId}`);
}

/** POST /admin/media/{image_id}/regenerate */
export async function regenerateImage(imageId: string): Promise<ImageOutRaw> {
  return api.post<ImageOutRaw>(`/admin/media/${imageId}/regenerate`);
}

/** PATCH /admin/media/{image_id}/alt-text */
export async function updateImageAltText(
  imageId: string,
  altText: string | null,
): Promise<ImageOutRaw> {
  return api.patch<ImageOutRaw>(`/admin/media/${imageId}/alt-text`, {
    body: { alt_text: altText },
  });
}
