import type { ProductVariant } from "@/types/public";

export const variantStockOf = (v: ProductVariant): number => v.available_stock ?? v.stock_quantity;

/**
 * The whole product is sold out: no variants and no stock, or variants that
 * are all out of stock. A product with variants can't be judged from its own
 * stock number alone — the shopper buys a variant, so every variant counts.
 */
export function isProductSoldOut(
  variants: ProductVariant[] | undefined,
  availableStock: number,
): boolean {
  return variants && variants.length > 0
    ? variants.every((v) => variantStockOf(v) === 0)
    : availableStock === 0;
}
