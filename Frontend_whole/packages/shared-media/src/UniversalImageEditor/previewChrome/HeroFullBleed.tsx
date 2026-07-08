import type { Breakpoint } from "@hadha/shared-types";
import type { PreviewChromeProps } from "./types";

/** Miniature replica of the storefront's full-bleed hero slide, including
 * the headline/CTA overlay so the safe-area guides on the crop editor line
 * up with content that will actually sit on top of the image. */
export function HeroFullBleedChrome({
  imageSrc,
  breakpoint,
}: PreviewChromeProps & { breakpoint: Breakpoint }) {
  const isMobile = breakpoint === "mobile";
  return (
    <div
      className={
        isMobile
          ? "relative w-32 aspect-[390/600] rounded-md overflow-hidden border bg-secondary"
          : "relative w-full aspect-[1920/700] rounded-md overflow-hidden border bg-secondary"
      }
    >
      {imageSrc && (
        <img src={imageSrc} alt="" className="w-full h-full object-cover" draggable={false} />
      )}
      <div
        className={
          isMobile
            ? "absolute inset-x-0 bottom-0 p-3 bg-gradient-to-t from-black/60 to-transparent space-y-1.5"
            : "absolute inset-y-0 left-0 w-1/2 flex flex-col justify-center gap-2 p-6 bg-gradient-to-r from-black/50 to-transparent"
        }
      >
        <div className="h-2.5 w-2/3 rounded bg-white/80" />
        <div className="h-2 w-1/2 rounded bg-white/60" />
        <div className="h-5 w-16 rounded bg-white/90 mt-1" />
      </div>
    </div>
  );
}
