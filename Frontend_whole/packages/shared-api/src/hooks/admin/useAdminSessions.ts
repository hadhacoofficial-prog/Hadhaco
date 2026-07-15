import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type {
  AdminSessionListResponse,
  AuditLogPage,
  RevokeSessionResponse,
} from "@hadha/shared-types";

export function useAdminSessions() {
  return useQuery({
    queryKey: queryKeys.admin.sessions,
    queryFn: () => api.get<AdminSessionListResponse>("/auth/admin/sessions"),
    staleTime: 15_000,
  });
}

export function useRevokeAdminSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      api.delete<RevokeSessionResponse>(`/auth/admin/sessions/${sessionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.sessions });
    },
  });
}

export function useRevokeOtherAdminSessions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<RevokeSessionResponse>("/auth/admin/sessions/revoke-others"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.sessions });
    },
  });
}

export function useRevokeAllAdminSessions() {
  return useMutation({
    mutationFn: () => api.post<RevokeSessionResponse>("/auth/admin/sessions/revoke-all"),
  });
}

/**
 * Recent security activity — reuses the existing /admin/audit-logs endpoint
 * (actor_id filter) rather than a second logging/listing system. This
 * naturally surfaces every event this session logs for the current admin —
 * login, logout, 2FA success/failure/lockout, enable/disable, backup-code
 * regeneration, session revocations — since actor_id is always set to the
 * acting admin on all of them.
 */
export function useAdminLoginHistory(currentUserId: string | undefined, page: number, pageSize = 20) {
  const filters = { page, page_size: pageSize, actor_id: currentUserId };
  return useQuery({
    queryKey: queryKeys.admin.auditLogs(filters),
    queryFn: () =>
      api.get<AuditLogPage>("/admin/audit-logs", {
        params: { page, page_size: pageSize, actor_id: currentUserId },
      }),
    enabled: !!currentUserId,
    staleTime: 15_000,
  });
}
