import type { BreakpointCropGeometry } from "@hadha/shared-types";

/**
 * Client-side-only preview render: rotate + crop *image* per *geometry* and
 * return a data URL sized to fit within maxPreviewWidth. This is a rough
 * visual approximation for the editor's live preview panes — the
 * authoritative pixels are always generated server-side by
 * crop_engine.py + variant_generator.py from the untouched original.
 */
export function renderCroppedPreview(
  image: HTMLImageElement,
  geometry: BreakpointCropGeometry,
  maxPreviewWidth = 480,
): string | null {
  const { box, rotation } = geometry;
  if (!box.width || !box.height) return null;

  const rotationCanvas = document.createElement("canvas");
  const radians = (rotation * Math.PI) / 180;
  const sin = Math.abs(Math.sin(radians));
  const cos = Math.abs(Math.cos(radians));
  const rotatedWidth = image.naturalWidth * cos + image.naturalHeight * sin;
  const rotatedHeight = image.naturalWidth * sin + image.naturalHeight * cos;
  rotationCanvas.width = rotatedWidth;
  rotationCanvas.height = rotatedHeight;
  const rotationCtx = rotationCanvas.getContext("2d");
  if (!rotationCtx) return null;

  rotationCtx.translate(rotatedWidth / 2, rotatedHeight / 2);
  rotationCtx.rotate(radians);
  rotationCtx.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);

  const scale = Math.min(1, maxPreviewWidth / box.width);
  const outWidth = Math.max(1, Math.round(box.width * scale));
  const outHeight = Math.max(1, Math.round(box.height * scale));

  const outCanvas = document.createElement("canvas");
  outCanvas.width = outWidth;
  outCanvas.height = outHeight;
  const outCtx = outCanvas.getContext("2d");
  if (!outCtx) return null;

  outCtx.drawImage(
    rotationCanvas,
    box.x,
    box.y,
    box.width,
    box.height,
    0,
    0,
    outWidth,
    outHeight,
  );

  return outCanvas.toDataURL("image/webp", 0.85);
}
