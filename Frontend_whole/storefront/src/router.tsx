import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { isApiError } from "./lib/api/errors";
import { initSync } from "@hadha/shared-api";
import { listenInventoryEvents } from "@/hooks/inventory/listenInventoryEvents";
import { listenReservationEvents } from "@/hooks/reservation/listenReservationEvents";

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

  // Mount the Zustand-store SSE writers globally, for the whole app
  // lifetime — previously these only ran while a product detail page
  // happened to be mounted (via useInventorySync/useReservationSync), so
  // real-time stock/reservation pushes were silently dropped on every other
  // route (home, listings, cart, checkout). initSync above already starts
  // the SSE connection itself and the broader React-Query-invalidation
  // listeners globally; these are the two that were missing the same
  // treatment. Safe to call once here (not inside a component) since
  // getRouter() itself only runs once per app instance.
  listenInventoryEvents();
  listenReservationEvents();

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
