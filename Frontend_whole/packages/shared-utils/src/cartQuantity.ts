export interface QuantityBounds {
  cartQty: number;
  availableStock: number;
  maxOrderQty: number;
  /** min(maxOrderQty || ∞, availableStock) — absolute ceiling for this line */
  effectiveCap: number;
  /** effectiveCap - cartQty, clamped to ≥ 0 — how many more can be added */
  remainingAllowed: number;
  canAdd: boolean;
  limitMessage: string | null;
}

export function computeQuantityBounds({
  availableStock,
  maxOrderQty,
  cartQty,
}: {
  availableStock: number;
  maxOrderQty: number;
  cartQty: number;
}): QuantityBounds {
  const effectiveCap = maxOrderQty > 0 ? Math.min(maxOrderQty, availableStock) : availableStock;
  const remainingAllowed = Math.max(0, effectiveCap - cartQty);
  const canAdd = remainingAllowed > 0 && availableStock > 0;

  let limitMessage: string | null = null;
  if (availableStock > 0 && !canAdd && cartQty > 0) {
    if (maxOrderQty > 0 && cartQty >= maxOrderQty) {
      limitMessage = `Limit of ${maxOrderQty} per order — already in your cart`;
    } else {
      limitMessage = `All ${availableStock} available — already in your cart`;
    }
  }

  return {
    cartQty,
    availableStock,
    maxOrderQty,
    effectiveCap,
    remainingAllowed,
    canAdd,
    limitMessage,
  };
}
