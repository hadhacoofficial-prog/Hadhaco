import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/queryKeys";
import type {
  NotificationAnalyticsOut,
  NotificationLogListResponse,
  NotificationLogsFilter,
  NotificationRuleOut,
  NotificationRuleUpdate,
  NotificationTemplateOut,
  NotificationTemplateUpdate,
  NotificationTemplateVersionOut,
  ProviderHealthOut,
  ProviderSettingsOut,
  ProviderTestResult,
  RetryLogsResult,
  WhatsAppMessageTemplateOut,
} from "@hadha/shared-types";

// ── Notification Matrix (rules) ─────────────────────────────────────────────

export const useNotificationRules = () => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.rules,
    queryFn: () => api.get<NotificationRuleOut[]>("/notifications/admin/rules"),
  });
};

export const useUpdateNotificationRule = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      eventType,
      data,
    }: {
      eventType: string;
      data: NotificationRuleUpdate;
    }) =>
      api.put<NotificationRuleOut>(`/notifications/admin/rules/${eventType}`, {
        body: data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.notifications.rules });
    },
  });
};

// ── Templates ────────────────────────────────────────────────────────────────

export const useNotificationTemplates = () => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.templates,
    queryFn: () =>
      api.get<NotificationTemplateOut[]>("/notifications/admin/templates"),
  });
};

export const useNotificationTemplate = (templateId: string | undefined) => {
  const { data: templates, ...rest } = useNotificationTemplates();
  const template = templates?.find((t) => t.id === templateId);
  return { data: template, templates, ...rest };
};

export const useUpdateNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      templateId,
      data,
    }: {
      templateId: string;
      data: NotificationTemplateUpdate;
    }) =>
      api.put<NotificationTemplateOut>(
        `/notifications/admin/templates/${templateId}`,
        { body: data },
      ),
    onSuccess: (_, { templateId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.notifications.templates,
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.notifications.templateVersions(templateId),
      });
    },
  });
};

export const useDuplicateNotificationTemplate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) =>
      api.post<NotificationTemplateOut>(
        `/notifications/admin/templates/${templateId}/duplicate`,
        {},
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.notifications.templates,
      });
    },
  });
};

export const useNotificationTemplateVersions = (templateId: string | undefined) => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.templateVersions(templateId ?? ""),
    queryFn: () =>
      api.get<NotificationTemplateVersionOut[]>(
        `/notifications/admin/templates/${templateId}/versions`,
      ),
    enabled: !!templateId,
  });
};

export const useRestoreTemplateVersion = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      templateId,
      version,
    }: {
      templateId: string;
      version: number;
    }) =>
      api.post<NotificationTemplateOut>(
        `/notifications/admin/templates/${templateId}/versions/${version}/restore`,
        {},
      ),
    onSuccess: (_, { templateId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.notifications.templates,
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.notifications.templateVersions(templateId),
      });
    },
  });
};

// ── Logs (+ retry) ───────────────────────────────────────────────────────────

export const useNotificationLogs = (
  filters?: NotificationLogsFilter,
  options?: { refetchInterval?: number },
) => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.logs(filters as Record<string, unknown>),
    queryFn: () =>
      api.get<NotificationLogListResponse>("/notifications/admin/logs", {
        params: filters as Record<string, string | number | boolean | null | undefined>,
      }),
    placeholderData: (prev) => prev,
    refetchInterval: options?.refetchInterval,
  });
};

export const useRetryNotificationLogs = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (logIds: string[]) =>
      api.post<RetryLogsResult>("/notifications/admin/logs/retry", {
        body: { log_ids: logIds },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "notifications", "logs"] });
    },
  });
};

// ── Analytics ────────────────────────────────────────────────────────────────

export const useNotificationAnalytics = (hours: number = 24) => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.analytics(hours),
    queryFn: () =>
      api.get<NotificationAnalyticsOut>("/notifications/admin/analytics", {
        params: { hours },
      }),
  });
};

// ── Provider settings & health ──────────────────────────────────────────────

export const useProviderSettings = (provider: string) => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.providerSettings(provider),
    queryFn: () =>
      api.get<ProviderSettingsOut>(
        `/admin/settings/notification-providers/${provider}`,
      ),
  });
};

export const useUpdateProviderSettings = (provider: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (values: Record<string, string>) =>
      api.put<ProviderSettingsOut>(
        `/admin/settings/notification-providers/${provider}`,
        { body: { values } },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.notifications.providerSettings(provider),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.notifications.providerHealth(provider),
      });
    },
  });
};

export const useProviderHealth = (provider: string) => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.providerHealth(provider),
    queryFn: () =>
      api.get<ProviderHealthOut>(
        `/admin/settings/notification-providers/${provider}/health`,
      ),
    refetchInterval: 30_000,
  });
};

export const useTestEmailProvider = () => {
  return useMutation({
    mutationFn: async (to: string) =>
      api.post<ProviderTestResult>(
        "/admin/settings/notification-providers/email/test",
        { params: { to } },
      ),
  });
};

export const useTestWhatsAppProvider = () => {
  return useMutation({
    mutationFn: async ({
      to,
      templateName,
      language,
    }: {
      to: string;
      templateName: string;
      language?: string;
    }) =>
      api.post<ProviderTestResult>(
        "/admin/settings/notification-providers/whatsapp/test",
        { params: { to, template_name: templateName, language: language ?? "en_US" } },
      ),
  });
};

export const useWhatsAppTemplateSync = () => {
  return useQuery({
    queryKey: queryKeys.admin.notifications.waTemplates,
    queryFn: () =>
      api.get<WhatsAppMessageTemplateOut[]>(
        "/admin/settings/notification-providers/whatsapp/templates",
      ),
    enabled: false, // fetched on-demand via refetch() from the Sync button
  });
};
