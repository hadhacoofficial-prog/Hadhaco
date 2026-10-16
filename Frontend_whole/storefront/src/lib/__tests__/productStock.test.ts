import { describe, expect, it } from "vitest";
import { isProductSoldOut } from "../productStock";
import type { ProductVariant } from "@/types/public";

const variant = (stock: number, over: Partial<ProductVariant> = {}): ProductVariant =>
  ({ id: "v", stock_quantity: stock, ...over }) as ProductVariant;

describe("isProductSoldOut", () => {
  it("variant-less product follows its own stock", () => {
    expect(isProductSoldOut(undefined, 0)).toBe(true);
    expect(isProductSoldOut([], 0)).toBe(true);
    expect(isProductSoldOut([], 3)).toBe(false);
  });

  it("product with variants is sold out only when every variant is", () => {
    expect(isProductSoldOut([variant(0), variant(0)], 0)).toBe(true);
    expect(isProductSoldOut([variant(0), variant(2)], 2)).toBe(false);
  });

  it("a single sold-out variant sells the product out", () => {
    expect(isProductSoldOut([variant(0)], 0)).toBe(true);
  });

  it("prefers available_stock over raw stock_quantity", () => {
    expect(isProductSoldOut([variant(5, { available_stock: 0 })], 0)).toBe(true);
  });

  it("ignores the product-level number when variants exist", () => {
    expect(isProductSoldOut([variant(0)], 7)).toBe(true);
  });
});
