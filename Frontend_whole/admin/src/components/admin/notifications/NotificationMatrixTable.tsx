import { useMemo } from "react";
import { toast } from "sonner";
import { toUserMessage } from "@/lib/api/errors";
import { Switch } from "@/components/ui/switch";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useNotificationRules,
  useUpdateNotificationRule,
} from "@/hooks/admin/useNotificationAdmin";
import type { NotificationRuleOut } from "@hadha/shared-types";

const CATEGORY_LABELS: Record<string, string> = {
  orders: "Orders",
  payments: "Payments",
  shipping: "Shipping",
  customer: "Customer",
  authentication: "Authentication",
  inventory: "Inventory",
  cms: "CMS",
  workers: "Workers",
  marketing: "Marketing",
  support: "Support",
  system: "System",
};

const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS);

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function groupByCategory(rules: NotificationRuleOut[]) {
  const groups = new Map<string, NotificationRuleOut[]>();
  for (const rule of rules) {
    const cat = rule.category ?? "system";
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat)!.push(rule);
  }
  return groups;
}

export function NotificationMatrixTable() {
  const { data: rules, isLoading } = useNotificationRules();
  const updateRule = useUpdateNotificationRule();

  const groups = useMemo(() => groupByCategory(rules ?? []), [rules]);

  const handleUpdate = (
    eventType: string,
    data: Parameters<typeof updateRule.mutate>[0]["data"],
  ) => {
    updateRule.mutate(
      { eventType, data },
      {
        onSuccess: () => toast.success("Notification rule updated"),
        onError: (e) => toast.error(toUserMessage(e)),
      },
    );
  };

  if (isLoading) {
    return (
      <TableSkeleton
        headers={[
          "Event",
          "Email",
          "WhatsApp",
          "Enabled",
          "Priority",
          "Retry Policy",
          "Visibility",
          "Last Triggered",
          "Last Sent",
        ]}
        rows={6}
      />
    );
  }

  if (!rules || rules.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-10 text-center">
        No notification events are configured yet.
      </p>
    );
  }

  return (
    <div className="space-y-8">
      {CATEGORY_ORDER.filter((cat) => groups.has(cat)).map((cat) => (
        <section key={cat}>
          <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-3">
            {CATEGORY_LABELS[cat] ?? cat}
          </h2>
          <div className="bg-background border border-border overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Event</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">WhatsApp</th>
                  <th className="px-4 py-3 font-medium">Enabled</th>
                  <th className="px-4 py-3 font-medium">Priority</th>
                  <th className="px-4 py-3 font-medium">Retry Policy</th>
                  <th className="px-4 py-3 font-medium">Visibility</th>
                  <th className="px-4 py-3 font-medium">Last Triggered</th>
                  <th className="px-4 py-3 font-medium">Last Sent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {groups.get(cat)!.map((rule) => (
                  <tr key={rule.id}>
                    <td className="px-4 py-3 align-top max-w-xs">
                      <p className="font-medium">{rule.display_name ?? "Untitled event"}</p>
                      {rule.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">{rule.description}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <Switch
                        checked={rule.email_enabled}
                        disabled={updateRule.isPending}
                        aria-label={`Email enabled for ${rule.display_name ?? rule.event_type}`}
                        onCheckedChange={(checked) =>
                          handleUpdate(rule.event_type, { email_enabled: checked })
                        }
                      />
                    </td>
                    <td className="px-4 py-3 align-top">
                      <Switch
                        checked={rule.whatsapp_enabled}
                        disabled={updateRule.isPending}
                        aria-label={`WhatsApp enabled for ${rule.display_name ?? rule.event_type}`}
                        onCheckedChange={(checked) =>
                          handleUpdate(rule.event_type, { whatsapp_enabled: checked })
                        }
                      />
                    </td>
                    <td className="px-4 py-3 align-top">
                      <Switch
                        checked={rule.enabled}
                        disabled={updateRule.isPending}
                        aria-label={`Master switch for ${rule.display_name ?? rule.event_type}`}
                        onCheckedChange={(checked) =>
                          handleUpdate(rule.event_type, { enabled: checked })
                        }
                      />
                    </td>
                    <td className="px-4 py-3 align-top">
                      <Select
                        value={rule.priority}
                        onValueChange={(value) =>
                          handleUpdate(rule.event_type, { priority: value })
                        }
                      >
                        <SelectTrigger className="w-28 h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="low">Low</SelectItem>
                          <SelectItem value="normal">Normal</SelectItem>
                          <SelectItem value="high">High</SelectItem>
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-muted-foreground">
                      {rule.retry_policy
                        ? JSON.stringify(rule.retry_policy)
                        : "Default (3 attempts)"}
                    </td>
                    <td className="px-4 py-3 align-top text-xs">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full ${
                          rule.customer_visible
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-secondary text-muted-foreground"
                        }`}
                      >
                        {rule.customer_visible ? "Customer" : "Internal"}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-muted-foreground whitespace-nowrap">
                      {formatRelativeTime(rule.last_triggered_at)}
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-muted-foreground whitespace-nowrap">
                      {formatRelativeTime(rule.last_sent_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
