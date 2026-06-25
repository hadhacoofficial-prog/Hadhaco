import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type { AdminSection, ReorderEntry } from "@hadha/shared-types";

export function useCmsSections() {
  return useQuery({
    queryKey: queryKeys.admin.cmsSections,
    queryFn: () => api.get<AdminSection[]>("/cms/admin/sections"),
    staleTime: 30 * 1000,
  });
}

export function useReorderSections() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entries: ReorderEntry[]) =>
      api.post<null>("/cms/admin/sections/reorder", { body: entries }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
      qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    },
  });
}

export function useToggleSection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sectionKey: string) =>
      api.post<AdminSection>(`/cms/admin/sections/${sectionKey}/toggle`),
    onSuccess: (_data, sectionKey) => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(sectionKey) });
      qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    },
  });
}

export function useInvalidateCache() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<null>("/cms/admin/cache/invalidate"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    },
  });
}
