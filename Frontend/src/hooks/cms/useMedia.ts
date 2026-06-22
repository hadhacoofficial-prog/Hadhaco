import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { CmsMedia, MediaListResponse } from "@/types/cms";

interface MediaListParams {
  page?: number;
  page_size?: number;
  folder?: string;
  mime_type?: string;
}

export function useMediaList(params: MediaListParams = {}) {
  return useQuery({
    queryKey: queryKeys.admin.cmsMedia(params as Record<string, unknown>),
    queryFn: () =>
      api.get<MediaListResponse>("/cms/admin/media", {
        params: {
          page: params.page ?? 1,
          page_size: params.page_size ?? 48,
          ...(params.folder ? { folder: params.folder } : {}),
          ...(params.mime_type ? { mime_type: params.mime_type } : {}),
        },
      }),
    staleTime: 60 * 1000,
  });
}

export function useUploadMedia() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      folder,
      alt_text,
    }: {
      file: File;
      folder?: string;
      alt_text?: string;
    }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("folder", folder ?? "/");
      if (alt_text) fd.append("alt_text", alt_text);
      return api.post<CmsMedia>("/cms/admin/media/upload", { body: fd });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "cms", "media"] });
    },
  });
}

export function useUpdateMedia() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: { alt_text?: string; folder?: string; tags?: string[] };
    }) => api.patch<CmsMedia>(`/cms/admin/media/${id}`, { body: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "cms", "media"] });
    },
  });
}

export function useDeleteMedia() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<null>(`/cms/admin/media/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "cms", "media"] });
    },
  });
}
