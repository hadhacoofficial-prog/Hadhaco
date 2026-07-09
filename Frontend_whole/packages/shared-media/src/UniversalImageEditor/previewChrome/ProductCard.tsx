import { CroppedImageView } from "../CroppedImageView";
import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront's square product grid tile — image,
 * name/price placeholders, and a sale badge so the crop's relationship to
 * the surrounding card chrome (corner badge overlap, caption clearance) is
 * visible while framing, not just the bare square. */
export function ProductCardChrome({ imageSrc, naturalWidth, naturalHeight, geometry }: PreviewChromeProps) {
  return (
    <div className="w-full rounded-md border bg-card overflow-hidden">
      <div className="relative aspect-square bg-secondary">
        {imageSrc && geometry && (
          <CroppedImageView
            imageSrc={imageSrc}
            naturalWidth={naturalWidth}
            naturalHeight={naturalHeight}
            geometry={geometry}
          />
        )}
        <span className="absolute left-1.5 top-1.5 rounded bg-foreground/90 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-background">
          New
        </span>
      </div>
      <div className="p-2 space-y-1">
        <div className="h-2 w-3/4 rounded bg-muted" />
        <div className="h-2 w-1/2 rounded bg-muted" />
      </div>
    </div>
  );
}
