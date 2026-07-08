import type { ShapeType } from "@hadha/shared-types";

interface ShapeMaskOverlayProps {
  shape: ShapeType;
}

/**
 * Draws a dimmed mask around the crop window so the admin sees the final
 * shape (circle/rounded-rect) rather than always seeing a plain rectangle,
 * matching what apply_shape_mask will actually produce server-side.
 * Purely cosmetic — react-easy-crop still reports a rectangular crop box;
 * the shape is applied to the pixels inside that box at save time.
 */
export function ShapeMaskOverlay({ shape }: ShapeMaskOverlayProps) {
  if (shape !== "circle" && shape !== "rounded_rect") {
    return null;
  }

  // A box-shadow with a huge spread on a shaped hole is the standard
  // trick for dimming everything outside an arbitrary shape without
  // needing an even-odd clip-path.
  const borderRadius = shape === "circle" ? "50%" : "12%";

  return (
    <div
      className="pointer-events-none absolute inset-0 z-10"
      style={{
        borderRadius,
        boxShadow: "0 0 0 9999px rgba(0,0,0,0.55)",
      }}
    />
  );
}
