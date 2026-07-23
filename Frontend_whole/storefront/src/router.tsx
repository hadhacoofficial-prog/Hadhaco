import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { isApiError } from "./lib/api/errors";
import { initSync } from "@hadha/shared-api";

/**
 * App-wide QueryClient defaults. Per-query overrides (staleTime, etc.) follow
 * the cache strategy documented in the README; these are the safe baselines.
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
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

  // Initialize the centralized sync engine with the app's QueryClient.
  // This must happen once at startup so all sync methods can invalidate queries.
  initSync(queryClient);

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
