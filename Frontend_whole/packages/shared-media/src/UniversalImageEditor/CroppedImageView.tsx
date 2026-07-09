import type { BreakpointCropGeometry } from "@hadha/shared-types";
import { rotatedBounds } from "../cropMath";

interface CroppedImageViewProps {
  /** The untouched original — never a previously-generated variant. */
  imageSrc: string;
  naturalWidth: number;
  naturalHeight: number;
  geometry: BreakpointCropGeometry;
  className?: string;
  /** "cover" (default) fills the container edge to edge — correct whenever
   * the container's own aspect ratio already matches the crop box's (every
   * preset with a fixed aspectRatio). "contain" instead letterboxes within
   * the container, preserving the box's own aspect — for "contain"-shape
   * presets (logos) whose box has no fixed target aspect and shouldn't be
   * stretched to fit an arbitrary container shape. */
  fit?: "cover" | "contain";
}

/**
 * Renders exactly what `geometry.box` (+ rotation) crops out of the source
 * image, live, via a pure CSS transform — no canvas, no toDataURL, no
 * debounce, no async step. This is what makes the preview panels update
 * instantly on every drag/zoom/rotate tick and never depend on the image's
 * origin (a canvas-based approach taints on cross-origin CDN images without
 * permissive CORS headers; a plain scaled+positioned <img> never touches
 * pixel data, so it can't taint no matter where the image is hosted).
 *
 * The math: a wrapper sized to the full (natural) image, expressed as a
 * percentage of *its own* box so it stays responsive, is translated (in
 * percentages of its own size, matching CSS `translate()` semantics) and
 * rotated so that `box` exactly fills the container — derived once from
 * geometry, not measured from the DOM.
 */
export function CroppedImageView({
  imageSrc,
  naturalWidth,
  naturalHeight,
  geometry,
  className,
  fit = "cover",
}: CroppedImageViewProps) {
  const { box, rotation } = geometry;
  if (!box.width || !box.height || !naturalWidth || !naturalHeight) return null;

  const { width: rotatedWidth, height: rotatedHeight } = rotatedBounds(
    naturalWidth,
    naturalHeight,
    rotation,
  );

  // Wrapper size as a percentage of the crop box (its containing block here
  // is the box-shaped container below), so scaling is resolution-independent.
  const wrapperWidthPct = (naturalWidth / box.width) * 100;
  const wrapperHeightPct = (naturalHeight / box.height) * 100;

  // translate() percentages are relative to the *translated element's own*
  // size (per the CSS spec), hence dividing by naturalWidth/Height rather
  // than the container — see cropMath.ts's computeSyncedCropBox for the
  // box/rotation geometry this mirrors.
  const translateXPct = (((rotatedWidth - naturalWidth) / 2 - box.x) / naturalWidth) * 100;
  const translateYPct = (((rotatedHeight - naturalHeight) / 2 - box.y) / naturalHeight) * 100;

  const cropped = (
    <div className="relative h-full w-full overflow-hidden">
      <div
        className="absolute left-0 top-0"
        style={{
          width: `${wrapperWidthPct}%`,
          height: `${wrapperHeightPct}%`,
          transform: `translate(${translateXPct}%, ${translateYPct}%) rotate(${rotation}deg)`,
        }}
      >
        <img src={imageSrc} alt="" className="h-full w-full object-fill" draggable={false} />
      </div>
    </div>
  );

  if (fit === "cover") {
    return <div className={className ?? "h-full w-full"}>{cropped}</div>;
  }

  // "contain": the box's own aspect ratio (not the outer container's) sets
  // the shape — center a correctly-shaped sub-box inside the container and
  // do all the crop math relative to that, so nothing gets stretched.
  return (
    <div className={className ?? "flex h-full w-full items-center justify-center"}>
      <div
        className="relative max-h-full max-w-full"
        style={{ aspectRatio: `${box.width} / ${box.height}`, width: "100%" }}
      >
        {cropped}
      </div>
    </div>
  );
}
