import type { CropBoxGeometry } from "@hadha/shared-types";

interface MiniNavigatorProps {
  imageSrc: string;
  naturalWidth: number;
  naturalHeight: number;
  box: CropBoxGeometry;
}

/** Photoshop-style corner navigator — the full image with a highlighted
 * rectangle showing where the current crop box sits, so panning/zooming in
 * doesn't lose the sense of "where am I in the source image." The box is
 * already in natural-pixel coordinates (react-easy-crop's onCropComplete
 * output), so this is a direct percentage mapping — no extra measurement or
 * approximation needed. Only rendered by the caller once zoomed in, since
 * at the default fit-to-view the crop box already covers most of the frame. */
export function MiniNavigator({ imageSrc, naturalWidth, naturalHeight, box }: MiniNavigatorProps) {
  if (!naturalWidth || !naturalHeight) return null;

  const left = (box.x / naturalWidth) * 100;
  const top = (box.y / naturalHeight) * 100;
  const width = (box.width / naturalWidth) * 100;
  const height = (box.height / naturalHeight) * 100;

  return (
    <div
      className="pointer-events-none absolute bottom-3 left-3 z-30 w-24 overflow-hidden rounded border border-white/25 shadow-lg"
      style={{ aspectRatio: `${naturalWidth} / ${naturalHeight}` }}
    >
      <img src={imageSrc} alt="" className="h-full w-full object-cover opacity-70" draggable={false} />
      <div
        className="absolute border-2 border-white"
        style={{
          left: `${left}%`,
          top: `${top}%`,
          width: `${width}%`,
          height: `${height}%`,
          boxShadow: "0 0 0 999px rgba(0,0,0,0.45)",
        }}
      />
    </div>
  );
}
