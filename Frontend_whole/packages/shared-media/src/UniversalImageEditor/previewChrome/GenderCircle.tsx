import { CroppedImageView } from "../CroppedImageView";
import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront's circular gender-section tile —
 * matches the "gender_section" preset's circle shape mask. */
export function GenderCircleChrome({
  imageSrc,
  naturalWidth,
  naturalHeight,
  geometry,
}: PreviewChromeProps) {
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="w-28 aspect-square rounded-full overflow-hidden border bg-secondary">
        {imageSrc && geometry && (
          <CroppedImageView
            imageSrc={imageSrc}
            naturalWidth={naturalWidth}
            naturalHeight={naturalHeight}
            geometry={geometry}
          />
        )}
      </div>
      <div className="h-2 w-16 rounded bg-muted" />
    </div>
  );
}
