import { NavJewelleryBgMobile } from "./NavJewelleryBgMobile";

// Fixed number of tiles; the responsive grid below adjusts columns and lets
// `auto-rows-fr` derive row count, so tile size scales per breakpoint without
// re-rendering different variants of the artwork.
const TILE_COUNT = 6;

/**
 * Site-wide decorative background. Reuses the same jewellery line-art asset
 * as the navbar, tiled behind all page content. Fixed to the viewport (not
 * the document) so it never needs to "scroll" with tall pages — no seams,
 * no duplicated image assets, negligible render cost.
 */
export function GlobalJewelleryBackground() {
  return (
    <div
      aria-hidden="true"
      className="fixed inset-0 -z-10 overflow-hidden pointer-events-none select-none opacity-70"
    >
      <div className="grid h-full w-full auto-rows-fr grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: TILE_COUNT }, (_, i) => (
          <div key={i} className="relative">
            <NavJewelleryBgMobile />
          </div>
        ))}
      </div>
    </div>
  );
}
