import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { isApiError } from "./lib/api/errors";

const TWO_FA_EXEMPT_PATHS = new Set(["/admin/login", "/admin/2fa", "/admin/settings/security"]);

/**
 * The backend is the only source of truth for the admin 2FA gate (see
 * app.core.dependencies on the API side) — it returns 403 with envelope
 * `code: "2FA_REQUIRED"` on any admin-guarded request until the current
 * session has passed the TOTP challenge (or, for accounts that must have
 * 2FA enabled, until it's set up at all). This hard-redirects the whole
 * page so no stale client state survives; it's a UX convenience only,
 * never the security boundary itself.
 */
function handleTwoFactorRequired(error: unknown) {
  if (!isApiError(error) || error.code !== "2FA_REQUIRED") return;
  if (TWO_FA_EXEMPT_PATHS.has(window.location.pathname)) return;

  const details = error.details as { setup_url?: string } | undefined;
  const target =
    details?.setup_url === "/admin/settings/security"
      ? "/admin/settings/security"
      : `/admin/2fa?redirect=${encodeURIComponent(window.location.pathname)}`;
  window.location.assign(target);
}

/**
 * App-wide QueryClient defaults. Per-query overrides (staleTime, etc.) follow
 * the cache strategy documented in the README; these are the safe baselines.
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleTwoFactorRequired }),
    mutationCache: new MutationCache({ onError: handleTwoFactorRequired }),
    defaultOptions: {
      queries: {
        // Most reads tolerate a short staleness window; cache-heavy domains
        // (CMS, categories) raise this, real-time domains (cart) drop it to 0.
        staleTime: 60_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Never retry auth/permission/validation errors; retry transient ones.
          if (isApiError(error)) return error.isRetryable && failureCount < 2;
          return failureCount < 2;
        },
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

export const getRouter = () => {
  const queryClient = createAppQueryClient();

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
