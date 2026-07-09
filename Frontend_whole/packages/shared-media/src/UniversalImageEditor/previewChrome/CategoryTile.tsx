import { CroppedImageView } from "../CroppedImageView";
import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront's category nav tile — image with a
 * centered label pill, same bottom-safe-area shape as the collection tile
 * but styled as a compact nav card rather than a full-bleed grid cell. */
export function CategoryTileChrome({
  imageSrc,
  naturalWidth,
  naturalHeight,
  geometry,
}: PreviewChromeProps) {
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
      </div>
      <div className="flex items-center justify-center p-2">
        <div className="h-2 w-1/2 rounded bg-muted" />
      </div>
    </div>
  );
}
