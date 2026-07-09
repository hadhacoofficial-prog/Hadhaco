import { CroppedImageView } from "../CroppedImageView";
import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront's collection grid tile — image with
 * a bottom caption pill, matching the "collection" preset's bottom-20%
 * safe area reserved for that label. */
export function CollectionTileChrome({
  imageSrc,
  naturalWidth,
  naturalHeight,
  geometry,
}: PreviewChromeProps) {
  return (
    <div className="relative w-full aspect-square rounded-md overflow-hidden border bg-secondary">
      {imageSrc && geometry && (
        <CroppedImageView
          imageSrc={imageSrc}
          naturalWidth={naturalWidth}
          naturalHeight={naturalHeight}
          geometry={geometry}
        />
      )}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3">
        <div className="h-2.5 w-2/3 rounded bg-white/90" />
      </div>
    </div>
  );
}
