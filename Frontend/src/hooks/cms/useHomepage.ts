import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { HomepageData } from "@/types/cms";

const HOMEPAGE_PLACEHOLDER: HomepageData = {
  cache_version: 0,
  layout: [],
  sections: {},
};

export function useHomepage() {
  return useQuery({
    queryKey: queryKeys.cms.homepage,
    queryFn: () => api.get<HomepageData>("/cms/homepage"),
    staleTime: 5 * 60 * 1000,      // 5 minutes — backend caches 24 h
    gcTime: 30 * 60 * 1000,
    retry: 1,
    refetchOnWindowFocus: false,
    placeholderData: HOMEPAGE_PLACEHOLDER,
  });
}
