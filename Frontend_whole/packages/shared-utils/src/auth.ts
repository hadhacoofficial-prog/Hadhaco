/**
 * Redirect sanitization for authentication flows.
 *
 * Prevents open-redirect attacks by whitelisting allowed post-login
 * destinations.  Any path not in the whitelist falls back to the default.
 *
 * Usage:
 *   const safeRedirect = sanitizeRedirect(searchParams.redirect);
 *   navigate({ to: safeRedirect });
 *
 *   // Or build a full return URL from the current location:
 *   const returnUrl = getAuthRedirectUrl(window.location);
 *   navigate({ to: "/account/login", search: { redirect: returnUrl } });
 */

const SAFE_REDIRECT_PATHS = [
  "/account",
  "/account/orders",
  "/cart",
  "/checkout",
  "/checkout/success",
  "/checkout/payment-failed",
  "/checkout/reservation-expired",
  "/checkout/stock-changed",
  "/products",
  "/collections",
  "/wishlist",
  "/search",
  "/about",
  "/contact",
  "/faq",
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
  "/admin/reviews",
  "/admin/coupons",
  "/admin/enquiries",
  "/admin/notifications",
  "/admin/reports",
  "/admin/templates",
  "/admin/2fa",
] as const;

/** Strip query string and hash from a path, returning just the pathname. */
function stripQueryHash(path: string): string {
  const qIdx = path.indexOf("?");
  const hIdx = path.indexOf("#");
  const end = qIdx !== -1 ? qIdx : hIdx !== -1 ? hIdx : path.length;
  return path.substring(0, end);
}

export function sanitizeRedirect(path: string | undefined, defaultPath = "/account"): string {
  if (!path) return defaultPath;
  // Block protocol-relative URLs and non-absolute paths
  if (!path.startsWith("/") || path.startsWith("//")) return defaultPath;
  // Extract the pathname portion (before ? or #) for whitelist matching
  const pathname = stripQueryHash(path);
  // Check against whitelist
  const matched = SAFE_REDIRECT_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
  // Return the full path (with query/hash intact) if matched
  return matched ? path : defaultPath;
}

/**
 * Build a safe, full relative redirect URL from the current location.
 *
 * Captures pathname + search params + hash so the user returns to the exact
 * page they were on.  The `redirect` search param itself is excluded to
 * avoid circular redirects.
 *
 * @param location - Browser location or TanStack Router location object.
 * @param defaultPath - Fallback if the built URL fails sanitization.
 * @returns A sanitized relative URL safe for the `?redirect=` param.
 */
export function getAuthRedirectUrl(
  location: { pathname: string; search?: Record<string, unknown> | string; hash?: string },
  defaultPath = "/account",
): string {
  const { pathname, search, hash } = location;
  let url = pathname;

  if (search) {
    if (typeof search === "string") {
      // Already a query string (e.g. "?tab=orders")
      if (search && search !== "?") url += search;
    } else {
      // Parsed search object from TanStack Router
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(search)) {
        if (v != null && k !== "redirect") params.set(k, String(v));
      }
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    }
  }

  if (hash) url += hash;

  return sanitizeRedirect(url, defaultPath);
}
