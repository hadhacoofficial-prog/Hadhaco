import { CroppedImageView } from "../CroppedImageView";
import type { PreviewChromeProps } from "./types";

/**
 * Fallback chrome for any preset whose reference_ui doesn't have a
 * dedicated mini-layout yet — still shows the actual crop result, just
 * without the surrounding page chrome. Every preset added to the registry
 * renders something useful immediately; a bespoke chrome is a later
 * refinement, not a blocker.
 */
export function GenericChrome({
  imageSrc,
  naturalWidth,
  naturalHeight,
  geometry,
  fit = "cover",
}: PreviewChromeProps & { fit?: "cover" | "contain" }) {
  return (
    <div className="w-full aspect-square rounded-md border bg-secondary overflow-hidden">
      {imageSrc && geometry && (
        <CroppedImageView
          imageSrc={imageSrc}
          naturalWidth={naturalWidth}
          naturalHeight={naturalHeight}
          geometry={geometry}
          fit={fit}
        />
      )}
    </div>
  );
}
