/** GST % from a form field: blank/invalid falls back to the 3% silver default, an explicit 0 is kept. */
export const parseTaxRate = (value: string): number => {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : 3;
};

const round2 = (n: number): number => Math.round(n * 100) / 100;

/**
 * The selling price is what the customer pays: GST is already inside it.
 * Same extraction the backend uses for orders and invoices
 * (`price * rate / (100 + rate)`), never added on top.
 */
export const gstBreakdown = (
  sellingPrice: number,
  taxRatePct: number,
): { gstIncluded: number; priceBeforeGst: number } => {
  const gstIncluded = round2((sellingPrice * taxRatePct) / (100 + taxRatePct));
  return { gstIncluded, priceBeforeGst: round2(sellingPrice - gstIncluded) };
};
