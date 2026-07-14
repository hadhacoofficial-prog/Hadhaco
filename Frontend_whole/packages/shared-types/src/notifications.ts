// ── Notification Rules (matrix) ──────────────────────────────────────────────

export interface NotificationRuleOut {
  id: string;
  event_type: string;
  display_name: string | null;
  category: string | null;
  description: string | null;
  enabled: boolean;
  email_enabled: boolean;
  whatsapp_enabled: boolean;
  priority: string;
  retry_policy: Record<string, unknown> | null;
  cooldown_seconds: number;
  customer_visible: boolean;
  admin_visible: boolean;
  is_system: boolean;
  display_order: number;
  last_triggered_at: string | null;
  last_sent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationRuleUpdate {
  display_name?: string | null;
  category?: string | null;
  description?: string | null;
  enabled?: boolean;
  email_enabled?: boolean;
  whatsapp_enabled?: boolean;
  priority?: string;
  retry_policy?: Record<string, unknown> | null;
  cooldown_seconds?: number;
  customer_visible?: boolean;
  admin_visible?: boolean;
  display_order?: number;
}

export const NOTIFICATION_CATEGORIES = [
  "orders",
  "payments",
  "shipping",
  "customer",
  "authentication",
  "inventory",
  "cms",
  "workers",
  "marketing",
  "support",
  "system",
] as const;
export type NotificationCategory = (typeof NOTIFICATION_CATEGORIES)[number];

// ── Notification Templates ───────────────────────────────────────────────────

export interface NotificationTemplateOut {
  id: string;
  name: string;
  channel: "email" | "whatsapp";
  event_type: string;
  subject: string | null;
  template_body: string;
  variables: Record<string, unknown> | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface NotificationTemplateUpdate {
  subject?: string | null;
  template_body?: string;
  variables?: Record<string, unknown> | null;
  is_active?: boolean;
}

export interface NotificationTemplateVersionOut {
  id: string;
  template_id: string;
  version: number;
  subject: string | null;
  template_body: string;
  variables: Record<string, unknown> | null;
  created_at: string;
  created_by: string | null;
}

// ── Notification Logs ────────────────────────────────────────────────────────

export type NotificationLogStatus =
  | "pending"
  | "retrying"
  | "sent"
  | "delivered"
  | "read"
  | "failed";

export interface NotificationLogOut {
  id: string;
  channel: string;
  event_type: string;
  recipient: string;
  status: NotificationLogStatus;
  provider: string | null;
  provider_message_id: string | null;
  error_message: string | null;
  attempt_count: number;
  rendered_subject: string | null;
  rendered_body: string | null;
  whatsapp_params: Record<string, unknown> | null;
  template_id: string | null;
  template_version: number | null;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationLogListResponse {
  items: NotificationLogOut[];
  total: number;
  offset: number;
  limit: number;
}

export interface NotificationLogsFilter {
  status?: string;
  channel?: string;
  event_type?: string;
  category?: string;
  provider?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  offset?: number;
  limit?: number;
}

export interface RetryLogsResult {
  retried: number;
  requested: number;
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export interface DailyTotalOut {
  date: string;
  sent: number;
  delivered: number;
  failed: number;
}

export interface TopTemplateOut {
  name: string;
  event_type: string;
  channel: string;
  sent_count: number;
}

export interface ProviderSuccessRateOut {
  sent: number;
  failed: number;
  success_rate: number;
}

export interface NotificationAnalyticsOut {
  total_sent: number;
  total_failed: number;
  total_pending: number;
  total_retrying: number;
  total_delivered: number;
  total_read: number;
  total_retried: number;
  email_sent: number;
  email_failed: number;
  whatsapp_sent: number;
  whatsapp_failed: number;
  avg_delivery_seconds: number | null;
  provider_success_rate: Record<string, ProviderSuccessRateOut>;
  daily_totals: DailyTotalOut[];
  top_templates: TopTemplateOut[];
}

// ── Provider settings / health ───────────────────────────────────────────────

export type NotificationProvider = "email" | "whatsapp";

export interface ProviderSettingsOut {
  provider: string;
  settings: Record<string, string | null>;
}

export interface ProviderSettingsUpdate {
  values: Record<string, string>;
}

export interface ProviderTestResult {
  success: boolean;
  message: string;
  message_id: string | null;
}

export interface ProviderHealthOut {
  provider: string;
  connection_status: "connected" | "error" | "not_configured";
  connection_detail: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_failure_message: string | null;
  last_webhook_at: string | null;
  webhook_url: string | null;
  webhook_verification_configured: boolean;
}

export interface WhatsAppMessageTemplateOut {
  name: string;
  language: string;
  status: "APPROVED" | "PENDING" | "REJECTED" | "DISABLED" | "UNKNOWN" | string;
  category: string;
}
