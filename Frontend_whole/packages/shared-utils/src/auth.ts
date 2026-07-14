/**
 * Redirect sanitization for authentication flows.
 *
 * Prevents open-redirect attacks by whitelisting allowed post-login
 * destinations.  Any path not in the whitelist falls back to the default.
 *
 * Usage:
 *   const safeRedirect = sanitizeRedirect(searchParams.redirect);
 *   navigate({ to: safeRedirect });
 */

const SAFE_REDIRECT_PATHS = [
  "/account",
  "/account/orders",
  "/cart",
  "/checkout",
  "/wishlist",
  "/search",
  // Admin paths
  "/admin",
  "/admin/products",
  "/admin/orders",
  "/admin/customers",
  "/admin/cms",
  "/admin/categories",
  "/admin/collections",
  "/admin/inventory",
  "/admin/settings",
] as const;

export function sanitizeRedirect(path: string | undefined, defaultPath = "/account"): string {
  if (!path) return defaultPath;
  // Block protocol-relative URLs and non-absolute paths
  if (!path.startsWith("/") || path.startsWith("//")) return defaultPath;
  // Check against whitelist
  const matched = SAFE_REDIRECT_PATHS.some((p) => path === p || path.startsWith(p + "/"));
  return matched ? path : defaultPath;
}
