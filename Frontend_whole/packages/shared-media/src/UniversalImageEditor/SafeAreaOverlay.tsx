import type { SafeArea } from "@hadha/shared-types";

interface SafeAreaOverlayProps {
  safeArea: SafeArea;
}

/** Dashed inset guide marking the preset's reserved edges (e.g. hero's left
 * 45% for headline/CTA copy, collection's bottom 20% for the caption pill) —
 * framing reference only, the server never trims to this. Skipped entirely
 * when a preset reserves no edges. */
export function SafeAreaOverlay({ safeArea }: SafeAreaOverlayProps) {
  const { top, right, bottom, left } = safeArea;
  if (!top && !right && !bottom && !left) return null;

  return (
    <div
      className="pointer-events-none absolute z-20 border border-dashed border-amber-400/70"
      style={{
        top: `${top}%`,
        right: `${right}%`,
        bottom: `${bottom}%`,
        left: `${left}%`,
      }}
    >
      <span className="absolute -top-5 left-0 text-[10px] font-medium uppercase tracking-wide text-amber-400/90">
        Safe area
      </span>
    </div>
  );
}
