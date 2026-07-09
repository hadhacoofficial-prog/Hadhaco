import { CroppedImageView } from "../CroppedImageView";
import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront's dark footer bar — logo is
 * "contain"-fit on a dark background, matching the "footer_logo" preset. */
export function LogoFooterChrome({ imageSrc, naturalWidth, naturalHeight, geometry }: PreviewChromeProps) {
  return (
    <div className="flex flex-col gap-3 w-full rounded-md border bg-neutral-900 px-3 py-3">
      <div className="h-7 w-20">
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
      <div className="flex gap-4">
        <div className="h-1.5 w-10 rounded bg-white/25" />
        <div className="h-1.5 w-10 rounded bg-white/25" />
        <div className="h-1.5 w-10 rounded bg-white/25" />
      </div>
    </div>
  );
}
