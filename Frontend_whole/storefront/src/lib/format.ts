export { formatINR, formatCurrency, formatDate, formatDateTime } from "@hadha/shared-utils";

/**
 * Normalizes silver purity values like "925", "925 Silver", "925 Sterling Silver"
 * to the correct "92.5" form (idempotent — leaves already-correct values untouched).
 */
export function formatPurity(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw.replace(/\b925\b/, "92.5");
}

/**
 * Customer-facing return policy line for a product. `isReturnable` undefined
 * means the data source did not carry the policy (e.g. a list card), so no
 * specific promise is made. An admin-written `customLabel` wins over the
 * generated wording; "{days}" in it is replaced with the return window.
 */
export function formatReturnPolicy(
  isReturnable: boolean | undefined,
  windowDays: number | undefined,
  customLabel?: string,
): string {
  const custom = customLabel?.trim();
  if (custom) {
    return custom
      .replaceAll("{days}", windowDays === undefined ? "" : String(windowDays))
      .replace(/\s{2,}/g, " ")
      .trim();
  }
  if (isReturnable === undefined) return "Returns vary by product";
  if (!isReturnable) return "No return, no refund";
  if (windowDays === undefined) return "Returns accepted";
  return `${windowDays}-day returns`;
}
