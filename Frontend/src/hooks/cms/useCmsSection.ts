import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { AdminSection, SectionItem, VersionHistoryEntry } from "@/types/cms";

export function useCmsSection(sectionKey: string) {
  return useQuery({
    queryKey: queryKeys.admin.cmsSection(sectionKey),
    queryFn: () => api.get<AdminSection>(`/cms/admin/sections/${sectionKey}`),
    staleTime: 30 * 1000,
    enabled: !!sectionKey,
  });
}

export function useSaveDraft(sectionKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { draft_config: Record<string, unknown>; change_summary?: string }) =>
      api.patch<AdminSection>(`/cms/admin/sections/${sectionKey}/draft`, { body: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(sectionKey) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
    },
  });
}

export function usePublishSection(sectionKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload?: { change_summary?: string; scheduled_at?: string }) =>
      api.post<AdminSection>(`/cms/admin/sections/${sectionKey}/publish`, { body: payload ?? {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(sectionKey) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
      qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    },
  });
}

export function useVersionHistory(sectionKey: string) {
  return useQuery({
    queryKey: queryKeys.admin.cmsSectionVersions(sectionKey),
    queryFn: () => api.get<VersionHistoryEntry[]>(`/cms/admin/sections/${sectionKey}/versions`),
    staleTime: 60 * 1000,
    enabled: !!sectionKey,
  });
}

export function useRollbackVersion(sectionKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionId: string) =>
      api.post<AdminSection>(`/cms/admin/sections/${sectionKey}/rollback/${versionId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(sectionKey) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSectionVersions(sectionKey) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSections });
      qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    },
  });
}

// ── Section items ─────────────────────────────────────────────────────────────

export function useSectionItems(sectionKey: string) {
  return useQuery({
    queryKey: queryKeys.admin.cmsSectionItems(sectionKey),
    queryFn: () => api.get<SectionItem[]>(`/cms/admin/sections/${sectionKey}/items`),
    staleTime: 30 * 1000,
    enabled: !!sectionKey,
  });
}

export function useCreateSectionItem(sectionKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { config: Record<string, unknown>; sort_order?: number }) =>
      api.post<SectionItem>(`/cms/admin/sections/${sectionKey}/items`, { body: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSectionItems(sectionKey) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(sectionKey) });
    },
  });
}

export function useUpdateSectionItem(sectionKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: Partial<SectionItem> }) =>
      api.patch<SectionItem>(`/cms/admin/sections/${sectionKey}/items/${itemId}`, { body: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSectionItems(sectionKey) });
    },
  });
}

export function useDeleteSectionItem(sectionKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) =>
      api.delete<null>(`/cms/admin/sections/${sectionKey}/items/${itemId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSectionItems(sectionKey) });
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSection(sectionKey) });
    },
  });
}

export function useReorderSectionItems(sectionKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entries: Array<{ id: string; sort_order: number }>) =>
      api.post<null>(`/cms/admin/sections/${sectionKey}/items/reorder`, { body: entries }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.cmsSectionItems(sectionKey) });
    },
  });
}
