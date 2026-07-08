import { useEffect, useRef, useState } from "react";
import type { Breakpoint, BreakpointCropGeometry } from "@hadha/shared-types";
import { GenericChrome } from "./previewChrome/Generic";
import { HeroFullBleedChrome } from "./previewChrome/HeroFullBleed";
import { ProductCardChrome } from "./previewChrome/ProductCard";
import { renderCroppedPreview } from "./renderPreview";

interface PreviewFrameProps {
  referenceUi: string;
  breakpoint: Breakpoint;
  imageElement: HTMLImageElement | null;
  geometry: BreakpointCropGeometry | undefined;
}

const BREAKPOINT_LABEL: Record<Breakpoint, string> = {
  desktop: "Desktop",
  tablet: "Tablet",
  mobile: "Mobile",
  all: "Preview",
};

// A short debounce (not requestAnimationFrame, which browsers throttle or
// fully pause on backgrounded/non-visible tabs) so rapid crop drags don't
// re-render the preview canvas on every intermediate pixel.
const RENDER_DEBOUNCE_MS = 80;

/**
 * Renders one breakpoint's crop inside a scaled replica of the real
 * consuming UI (architecture doc §7) — not just the bare crop rectangle.
 */
export function PreviewFrame({ referenceUi, breakpoint, imageElement, geometry }: PreviewFrameProps) {
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (!imageElement || !geometry) {
      setPreviewSrc(null);
      return;
    }
    timeoutRef.current = setTimeout(() => {
      setPreviewSrc(renderCroppedPreview(imageElement, geometry));
    }, RENDER_DEBOUNCE_MS);
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [imageElement, geometry]);

  const chrome = (() => {
    switch (referenceUi) {
      case "product-card":
        return <ProductCardChrome imageSrc={previewSrc} />;
      case "hero-full-bleed":
        return <HeroFullBleedChrome imageSrc={previewSrc} breakpoint={breakpoint} />;
      default:
        return <GenericChrome imageSrc={previewSrc} />;
    }
  })();

  return (
    <div className="flex flex-col items-center gap-2">
      <span className="text-xs font-medium text-muted-foreground">
        {BREAKPOINT_LABEL[breakpoint]}
      </span>
      {chrome}
    </div>
  );
}
