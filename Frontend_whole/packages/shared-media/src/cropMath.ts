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

import type { CropBoxGeometry } from "@hadha/shared-types";

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
