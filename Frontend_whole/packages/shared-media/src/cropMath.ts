/**
 * Pure crop geometry helpers — a TS port of the bounds-clamping half of
 * Backend/app/modules/media/crop_engine.py's validate_and_clamp_crop_box.
 *
 * This exists so the live preview (CropCanvas/PreviewFrame) can show the
 * exact same clamped box the server will end up persisting, instead of
 * drifting from it. It intentionally does NOT reimplement rotation/shape
 * masking/resizing — those stay server-side; the client only needs to know
 * "does this box fit" for the interactive preview.
 */

import type { CropBoxGeometry, CropPreset, Resolution } from "@hadha/shared-types";

export class CropGeometryError extends Error {}

export function validateAndClampCropBox(
  box: CropBoxGeometry,
  imageWidth: number,
  imageHeight: number,
  strictBounds: boolean,
): CropBoxGeometry {
  const left = box.x;
  const top = box.y;
  const right = box.x + box.width;
  const bottom = box.y + box.height;

  const fits = left >= 0 && top >= 0 && right <= imageWidth && bottom <= imageHeight;
  if (fits) {
    return box;
  }

  if (strictBounds) {
    throw new CropGeometryError(
      `Crop box (${box.x}, ${box.y}, ${box.width}x${box.height}) exceeds source image bounds (${imageWidth}x${imageHeight})`,
    );
  }

  const clampedLeft = Math.max(0, Math.min(left, imageWidth));
  const clampedTop = Math.max(0, Math.min(top, imageHeight));
  const clampedRight = Math.max(0, Math.min(right, imageWidth));
  const clampedBottom = Math.max(0, Math.min(bottom, imageHeight));

  return {
    x: clampedLeft,
    y: clampedTop,
    width: Math.max(0, clampedRight - clampedLeft),
    height: Math.max(0, clampedBottom - clampedTop),
  };
}

/**
 * Seed a default centered crop box for a breakpoint given the source image's
 * dimensions and the breakpoint's target aspect ratio (null = free-form,
 * uses the full image).
 */
export function defaultCropBox(
  imageWidth: number,
  imageHeight: number,
  aspectRatio: number | null,
): CropBoxGeometry {
  if (aspectRatio === null) {
    return { x: 0, y: 0, width: imageWidth, height: imageHeight };
  }

  const imageRatio = imageWidth / imageHeight;
  let width: number;
  let height: number;

  if (imageRatio > aspectRatio) {
    height = imageHeight;
    width = height * aspectRatio;
  } else {
    width = imageWidth;
    height = width / aspectRatio;
  }

  return {
    x: (imageWidth - width) / 2,
    y: (imageHeight - height) / 2,
    width,
    height,
  };
}

/** Axis-aligned bounding box of an `imageWidth x imageHeight` rect after
 * rotating it *rotationDegrees* around its own center — the same "expand to
 * fit" math crop_engine.py's rotation step and the live-preview renderer
 * both rely on. */
export function rotatedBounds(
  imageWidth: number,
  imageHeight: number,
  rotationDegrees: number,
): { width: number; height: number } {
  const radians = (rotationDegrees * Math.PI) / 180;
  const sin = Math.abs(Math.sin(radians));
  const cos = Math.abs(Math.cos(radians));
  return {
    width: imageWidth * cos + imageHeight * sin,
    height: imageWidth * sin + imageHeight * cos,
  };
}

/**
 * Derives a crop box for *aspectRatio* from a breakpoint-independent,
 * resolution-independent "framing": a focus point (fraction of the image,
 * 0-1) and a zoom level (1 = the largest box of this aspect that fits the
 * rotated image; higher = more magnified/smaller box). This is the engine
 * behind "All breakpoints" sync mode — each breakpoint keeps its own aspect
 * ratio (hero's desktop/tablet/mobile differ a lot) while sharing the same
 * center of interest and magnification, rather than requiring literally
 * identical box pixels across breakpoints with incompatible aspects.
 */
export function computeSyncedCropBox(
  imageWidth: number,
  imageHeight: number,
  aspectRatio: number | null,
  focusPoint: { x: number; y: number },
  zoom: number,
  rotationDegrees: number,
): CropBoxGeometry {
  const { width: boundsWidth, height: boundsHeight } = rotatedBounds(
    imageWidth,
    imageHeight,
    rotationDegrees,
  );

  let boxWidth: number;
  let boxHeight: number;
  if (aspectRatio === null) {
    boxWidth = boundsWidth;
    boxHeight = boundsHeight;
  } else if (boundsWidth / boundsHeight > aspectRatio) {
    boxHeight = boundsHeight;
    boxWidth = boxHeight * aspectRatio;
  } else {
    boxWidth = boundsWidth;
    boxHeight = boxWidth / aspectRatio;
  }

  const z = Math.max(1, zoom);
  boxWidth = Math.min(boundsWidth, boxWidth / z);
  boxHeight = Math.min(boundsHeight, boxHeight / z);

  // The unrotated image sits centered within its rotated bounding box.
  const imageOffsetX = (boundsWidth - imageWidth) / 2;
  const imageOffsetY = (boundsHeight - imageHeight) / 2;
  const centerX = imageOffsetX + focusPoint.x * imageWidth;
  const centerY = imageOffsetY + focusPoint.y * imageHeight;

  const x = Math.min(Math.max(0, centerX - boxWidth / 2), boundsWidth - boxWidth);
  const y = Math.min(Math.max(0, centerY - boxHeight / 2), boundsHeight - boxHeight);

  return { x, y, width: boxWidth, height: boxHeight };
}

/** Inverse of computeSyncedCropBox's centering step — recovers the focus
 * point (as an image-space fraction) that a given box is centered on, so
 * editing one breakpoint's box can update the shared framing that the other
 * linked breakpoints derive from. */
export function focusPointFromBox(
  imageWidth: number,
  imageHeight: number,
  rotationDegrees: number,
  box: CropBoxGeometry,
): { x: number; y: number } {
  const { width: boundsWidth, height: boundsHeight } = rotatedBounds(
    imageWidth,
    imageHeight,
    rotationDegrees,
  );
  const imageOffsetX = (boundsWidth - imageWidth) / 2;
  const imageOffsetY = (boundsHeight - imageHeight) / 2;
  const centerX = box.x + box.width / 2 - imageOffsetX;
  const centerY = box.y + box.height / 2 - imageOffsetY;
  return {
    x: imageWidth > 0 ? Math.min(1, Math.max(0, centerX / imageWidth)) : 0.5,
    y: imageHeight > 0 ? Math.min(1, Math.max(0, centerY / imageHeight)) : 0.5,
  };
}

/** Mirrors Backend/app/modules/media/validation.py's
 * `_smallest_min_resolution` — the component-wise minimum (width, height)
 * floor across every breakpoint a preset declares, used as the upload-time
 * gate. Returns null for presets with no min_resolution entries at all. */
export function smallestMinResolution(preset: CropPreset): Resolution | null {
  const resolutions = Object.values(preset.minResolution).filter(
    (r): r is Resolution => r != null,
  );
  if (resolutions.length === 0) return null;
  return {
    width: Math.min(...resolutions.map((r) => r.width)),
    height: Math.min(...resolutions.map((r) => r.height)),
  };
}

/** Reads a File's natural pixel dimensions without uploading it. Resolves
 * null for SVGs (no raster dimensions) or anything the browser can't decode
 * client-side — callers treat null as "can't check here," leaving the
 * server as the final authority. */
export async function readImageDimensions(
  file: File,
): Promise<{ width: number; height: number } | null> {
  if (file.type === "image/svg+xml") return null;
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
      img.onerror = () => resolve(null);
      img.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Validates a picked file's dimensions against *preset*'s minimum
 * resolution requirement, mirroring validation.py's upload-time gate so the
 * message matches the backend's exactly — this lets a too-small image be
 * rejected inline, right where it was picked, instead of only surfacing as
 * a 422 after the upload round-trip. Returns an error string to display, or
 * null if the file passes (or couldn't be checked client-side).
 */
export async function validateFileResolution(
  file: File,
  preset: CropPreset,
): Promise<string | null> {
  const floor = smallestMinResolution(preset);
  if (!floor) return null;
  const dims = await readImageDimensions(file);
  if (!dims) return null;
  if (dims.width < floor.width || dims.height < floor.height) {
    return `Image is ${dims.width}x${dims.height}, below the minimum ${floor.width}x${floor.height} required for ${preset.label}`;
  }
  return null;
}
