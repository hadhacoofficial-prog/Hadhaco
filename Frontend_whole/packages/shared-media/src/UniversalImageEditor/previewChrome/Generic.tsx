import type { PreviewChromeProps } from "./types";

/**
 * Fallback chrome for any preset whose reference_ui doesn't have a
 * dedicated mini-layout yet — still shows the actual crop result, just
 * without the surrounding page chrome. Every preset added to the registry
 * renders something useful immediately; a bespoke chrome is a later
 * refinement, not a blocker.
 */
export function GenericChrome({ imageSrc }: PreviewChromeProps) {
  return (
    <div className="w-full max-w-40 aspect-square rounded-md border bg-secondary overflow-hidden">
      {imageSrc && (
        <img src={imageSrc} alt="" className="w-full h-full object-contain" draggable={false} />
      )}
    </div>
  );
}
