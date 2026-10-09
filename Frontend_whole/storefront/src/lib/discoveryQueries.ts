import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toListApiParams, type DiscoveryScope, type DiscoveryState } from "@/lib/discovery";
import type { ProductListResponse } from "@/types/admin";

const LIST_STALE = 30_000;

/** Query options for a product listing — shared by route loaders and the grid. */
export function productListQuery(state: DiscoveryState, scope: DiscoveryScope = {}) {
  const params = toListApiParams(state, scope);
  return {
    queryKey: queryKeys.products.list(params),
    queryFn: () => api.get<ProductListResponse>("/products", { params }),
    staleTime: LIST_STALE,
  };
}
