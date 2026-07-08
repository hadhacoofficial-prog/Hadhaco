import { api } from "@hadha/shared-api";
import type { Breakpoint, CropGeometry, ImageBundle } from "@hadha/shared-types";

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
