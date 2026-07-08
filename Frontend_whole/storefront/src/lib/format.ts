export { formatINR, formatCurrency, formatDate, formatDateTime } from "@hadha/shared-utils";

/**
 * Normalizes silver purity values like "925", "925 Silver", "925 Sterling Silver"
 * to the correct "92.5" form (idempotent — leaves already-correct values untouched).
 */
export function formatPurity(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw.replace(/\b925\b/, "92.5");
}
