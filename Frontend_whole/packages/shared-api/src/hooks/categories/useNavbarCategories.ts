import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type { NavbarCategoriesResponse } from "@hadha/shared-types";

const EMPTY: NavbarCategoriesResponse = {
  women: [],
  men: [],
  unisex: [],
  kids: [],
};

/**
 * Fetches navbar categories from GET /categories/navbar.
 *
 * Caching strategy (categories almost never change):
 *   staleTime  24 h  â€” no background refetch within a session
 *   gcTime      7 d  â€” keep in memory across navigations
 *   retry        1   â€” one retry on network failure
 *   refetch flags all disabled â€” never refetch on focus/reconnect/remount
 *
 * The backend serves this from a 24-hour Redis cache and busts it automatically
 * whenever an admin creates, updates, or deletes a category.
 * The frontend will pick up fresh data on the next page load after the cache
 * staleTime expires.
 */
export function useNavbarCategories() {
  return useQuery({
    queryKey: queryKeys.categories.navbar,
    queryFn: () => api.get<NavbarCategoriesResponse>("/categories/navbar"),
    staleTime: 24 * 60 * 60 * 1000, // 24 hours
    gcTime: 7 * 24 * 60 * 60 * 1000, // 7 days
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
    placeholderData: EMPTY,
  });
}
