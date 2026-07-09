import { CroppedImageView } from "../CroppedImageView";
import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront header bar — logo is "contain"-fit
 * (never cropped/cover), matching the "company_logo" preset's shape. */
export function LogoHeaderChrome({ imageSrc, naturalWidth, naturalHeight, geometry }: PreviewChromeProps) {
  return (
    <div className="flex items-center justify-between w-full rounded-md border bg-card px-3 py-2.5">
      <div className="h-8 w-24">
        {imageSrc && geometry && (
          <CroppedImageView
            imageSrc={imageSrc}
            naturalWidth={naturalWidth}
            naturalHeight={naturalHeight}
            geometry={geometry}
            fit="contain"
          />
        )}
      </div>
      <div className="flex items-center gap-2.5">
        <div className="h-1.5 w-8 rounded bg-muted" />
        <div className="h-1.5 w-8 rounded bg-muted" />
        <div className="h-1.5 w-8 rounded bg-muted" />
      </div>
    </div>
  );
}
