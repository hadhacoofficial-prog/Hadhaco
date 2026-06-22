import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { NavigationCategoriesResponse } from "@/types/public";

const EMPTY: NavigationCategoriesResponse = {
  women: [],
  men: [],
  unisex: [],
  kids: [],
  gender_meta: {},
};

/**
 * Fetches the main navigation categories from GET /categories/navigation.
 *
 * Caching strategy (categories change only when an admin acts):
 *   staleTime   24 h  — no background refetch within a session
 *   gcTime       7 d  — keep in memory across navigations
 *   retry         1   — one retry on network failure
 *   refetch flags all disabled
 *
 * The backend serves this from a 24-hour Redis cache ('navigation:categories:v1')
 * and busts it automatically on every admin create / update / delete / reorder.
 * The frontend picks up fresh data after staleTime expires or on the next session.
 */
export function useNavigationCategories() {
  return useQuery({
    queryKey: queryKeys.categories.navigation,
    queryFn: () => api.get<NavigationCategoriesResponse>("/categories/navigation"),
    staleTime: 24 * 60 * 60 * 1000, // 24 hours
    gcTime: 7 * 24 * 60 * 60 * 1000, // 7 days
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
    placeholderData: EMPTY,
  });
}
