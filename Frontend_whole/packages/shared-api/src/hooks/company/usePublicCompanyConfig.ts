import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type { CompanyConfig } from "@hadha/shared-types";

/**
 * Public hook — fetches company config from the unauthenticated `/company`
 * endpoint.  The response is server-side cached (SWR, 1 h TTL) so
 * repeated calls are essentially free.
 */
export const usePublicCompanyConfig = () =>
  useQuery({
    queryKey: queryKeys.company.config,
    queryFn: () => api.get<CompanyConfig>("/company"),
    staleTime: 5 * 60_000, // 5 min client-side stale time
    gcTime: 60 * 60_000, // keep in cache for 1 h
  });
