import type { Breakpoint, BreakpointCropGeometry } from "@hadha/shared-types";
import { CategoryTileChrome } from "./previewChrome/CategoryTile";
import { CollectionTileChrome } from "./previewChrome/CollectionTile";
import { GenderCircleChrome } from "./previewChrome/GenderCircle";
import { GenericChrome } from "./previewChrome/Generic";
import { HeroFullBleedChrome } from "./previewChrome/HeroFullBleed";
import { LogoFooterChrome } from "./previewChrome/LogoFooter";
import { LogoHeaderChrome } from "./previewChrome/LogoHeader";
import { ProductCardChrome } from "./previewChrome/ProductCard";

interface PreviewFrameProps {
  referenceUi: string;
  /** "contain" for logo/inline-image presets with no fixed target aspect —
   * only consulted by the generic fallback chrome; every dedicated chrome
   * already knows its own fit from its own layout. */
  shape: string;
  breakpoint: Breakpoint;
  imageSrc: string | null;
  naturalWidth: number;
  naturalHeight: number;
  geometry: BreakpointCropGeometry | undefined;
}

const BREAKPOINT_LABEL: Record<Breakpoint, string> = {
  desktop: "Desktop",
  tablet: "Tablet",
  mobile: "Mobile",
  all: "Preview",
};

/**
 * Renders one breakpoint's crop inside a scaled replica of the real
 * consuming UI (architecture doc §7) — not just the bare crop rectangle.
 * Purely a function of the current in-memory geometry: no canvas render,
 * no debounce, no wait for a server round-trip, so it updates on every
 * drag/zoom/rotate tick exactly like the crop canvas itself.
 */
export function PreviewFrame({
  referenceUi,
  shape,
  breakpoint,
  imageSrc,
  naturalWidth,
  naturalHeight,
  geometry,
}: PreviewFrameProps) {
  const chrome = (() => {
    const props = { imageSrc, naturalWidth, naturalHeight, geometry };
    switch (referenceUi) {
      case "product-card":
        return <ProductCardChrome {...props} />;
      case "collection-tile":
        return <CollectionTileChrome {...props} />;
      case "category-tile":
        return <CategoryTileChrome {...props} />;
      case "gender-circle":
      case "testimonial-avatar":
      case "avatar":
      case "team-member":
        return <GenderCircleChrome {...props} />;
      case "hero-full-bleed":
      case "promo-banner":
        return <HeroFullBleedChrome {...props} breakpoint={breakpoint} />;
      case "company-logo":
        return <LogoHeaderChrome {...props} />;
      case "footer-logo":
        return <LogoFooterChrome {...props} />;
      default:
        return <GenericChrome {...props} fit={shape === "contain" ? "contain" : "cover"} />;
    }
  })();

  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {BREAKPOINT_LABEL[breakpoint]}
      </span>
      {chrome}
    </div>
  );
}
