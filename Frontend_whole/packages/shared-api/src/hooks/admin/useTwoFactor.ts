import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type {
  TwoFactorStatus,
  Setup2FAResponse,
  Verify2FAResponse,
  Validate2FAResponse,
  RegenerateBackupCodesResponse,
} from "@hadha/shared-types";

export function useTwoFactorStatus() {
  return useQuery({
    queryKey: queryKeys.admin.twoFactorStatus,
    queryFn: () => api.get<TwoFactorStatus>("/auth/admin/2fa/status"),
    staleTime: 30_000,
  });
}

export function useTwoFactorSetup() {
  return useMutation({
    mutationFn: () => api.post<Setup2FAResponse>("/auth/admin/2fa/setup"),
  });
}

export function useTwoFactorVerify() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (totp_code: string) =>
      api.post<Verify2FAResponse>("/auth/admin/2fa/verify", { body: { totp_code } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.twoFactorStatus });
    },
  });
}

export function useTwoFactorValidate() {
  return useMutation({
    mutationFn: (totp_code: string) =>
      api.post<Validate2FAResponse>("/auth/admin/2fa/validate", { body: { totp_code } }),
  });
}

export function useTwoFactorDisable() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (totp_code: string) =>
      api.post<null>("/auth/admin/2fa/disable", { body: { totp_code } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.twoFactorStatus });
    },
  });
}

export function useTwoFactorRegenerateCodes() {
  return useMutation({
    mutationFn: (totp_code: string) =>
      api.post<RegenerateBackupCodesResponse>("/auth/admin/2fa/backup-codes/regenerate", {
        body: { totp_code },
      }),
  });
}

export function useForceReset2FA() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (user_id: string) =>
      api.post<null>(`/admin/users/${user_id}/2fa/reset`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.twoFactorStatus });
    },
  });
}
