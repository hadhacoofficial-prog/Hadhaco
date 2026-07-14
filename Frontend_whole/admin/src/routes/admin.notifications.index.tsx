import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Mail,
  MessageCircle,
  CheckCheck,
  Eye,
  XCircle,
  RotateCcw,
  Percent,
  Hourglass,
  ListChecks,
} from "lucide-react";
import {
  useNotificationAnalytics,
  useNotificationLogs,
  useNotificationRules,
} from "@/hooks/admin/useNotificationAdmin";
import {
  DashboardKPISkeleton,
  DashboardListSkeleton,
} from "@/components/loading/DashboardSkeleton";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Bar, BarChart, CartesianGrid, XAxis, Pie, PieChart, Cell } from "recharts";

export const Route = createFileRoute("/admin/notifications/")({
  component: NotificationsDashboard,
});

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  retrying: "Retrying",
  sent: "Sent",
  delivered: "Delivered",
  read: "Read",
  failed: "Failed",
};

function NotificationsDashboard() {
  const { data: analytics, isLoading: analyticsLoading } = useNotificationAnalytics(24);
  const { data: rules } = useNotificationRules();
  const { data: recent, isLoading: recentLoading } = useNotificationLogs(
    { limit: 10 },
    { refetchInterval: 30_000 },
  );

  const eventLabel = (eventType: string) =>
    rules?.find((r) => r.event_type === eventType)?.display_name ?? eventType;

  const successRate = analytics
    ? analytics.total_sent + analytics.total_failed > 0
      ? Math.round((analytics.total_sent / (analytics.total_sent + analytics.total_failed)) * 100)
      : 100
    : null;

  const stats = analytics
    ? [
        {
          label: "Emails Sent Today",
          value: analytics.email_sent,
          icon: <Mail className="size-5" />,
        },
        {
          label: "WhatsApp Sent Today",
          value: analytics.whatsapp_sent,
          icon: <MessageCircle className="size-5" />,
        },
        {
          label: "Delivered",
          value: analytics.total_delivered,
          icon: <CheckCheck className="size-5" />,
        },
        { label: "Read", value: analytics.total_read, icon: <Eye className="size-5" /> },
        { label: "Failed", value: analytics.total_failed, icon: <XCircle className="size-5" /> },
        {
          label: "Retrying",
          value: analytics.total_retrying,
          icon: <RotateCcw className="size-5" />,
        },
        {
          label: "Success Rate",
          value: successRate !== null ? `${successRate}%` : "—",
          icon: <Percent className="size-5" />,
        },
        {
          label: "Pending Notifications",
          value: analytics.total_pending,
          icon: <Hourglass className="size-5" />,
        },
        {
          label: "Queue Size",
          value: analytics.total_pending + analytics.total_retrying,
          icon: <ListChecks className="size-5" />,
        },
      ]
    : [];

  const channelData = analytics
    ? [
        { name: "Email", value: analytics.email_sent, fill: "var(--accent)" },
        { name: "WhatsApp", value: analytics.whatsapp_sent, fill: "var(--foreground)" },
      ]
    : [];

  return (
    <div>
      {analyticsLoading ? (
        <DashboardKPISkeleton />
      ) : !analytics ? (
        <p className="text-sm text-muted-foreground py-10 text-center">
          Unable to load notification analytics right now.
        </p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map((s) => (
            <div key={s.label} className="bg-background border border-border p-5">
              <div className="flex items-center justify-between">
                <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                  {s.label}
                </p>
                <span className="text-accent">{s.icon}</span>
              </div>
              <p className="font-display text-3xl mt-3">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {analytics && (
        <div className="grid lg:grid-cols-2 gap-6 mt-8">
          <div className="bg-background border border-border p-6">
            <h2 className="font-display text-xl mb-5">Daily volume (14 days)</h2>
            <ChartContainer
              config={{
                sent: { label: "Sent", color: "var(--accent)" },
                delivered: { label: "Delivered", color: "var(--foreground)" },
                failed: { label: "Failed", color: "#c0392b" },
              }}
            >
              <BarChart data={analytics.daily_totals}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="sent" fill="var(--color-sent)" radius={2} />
                <Bar dataKey="delivered" fill="var(--color-delivered)" radius={2} />
                <Bar dataKey="failed" fill="var(--color-failed)" radius={2} />
              </BarChart>
            </ChartContainer>
          </div>

          <div className="bg-background border border-border p-6">
            <h2 className="font-display text-xl mb-5">Channel distribution</h2>
            <ChartContainer
              config={{
                Email: { label: "Email", color: "var(--accent)" },
                WhatsApp: { label: "WhatsApp", color: "var(--foreground)" },
              }}
            >
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent />} />
                <Pie data={channelData} dataKey="value" nameKey="name" innerRadius={50}>
                  {channelData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
          </div>
        </div>
      )}

      <div className="bg-background border border-border p-6 mt-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-display text-xl">Live activity</h2>
          <Link
            to="/admin/notifications/logs"
            className="text-xs uppercase tracking-[0.18em] text-accent hover:underline"
          >
            View all
          </Link>
        </div>
        {recentLoading ? (
          <DashboardListSkeleton rows={5} />
        ) : !recent || recent.items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-10">
            No notifications sent yet.
          </p>
        ) : (
          <ul className="divide-y divide-border" aria-live="polite">
            {recent.items.map((log) => (
              <li key={log.id} className="py-3 flex items-center justify-between text-sm gap-3">
                <span className="flex-1 min-w-0 truncate">{eventLabel(log.event_type)}</span>
                <span className="text-muted-foreground uppercase text-xs tracking-wide">
                  {log.channel}
                </span>
                <span className="text-xs text-muted-foreground">
                  {STATUS_LABEL[log.status] ?? log.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
