import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { ChartSkeleton, DashboardKPISkeleton } from "@/components/loading/DashboardSkeleton";
import { useNotificationAnalytics } from "@/hooks/admin/useNotificationAdmin";

const RANGES = [
  { label: "24 Hours", hours: 24 },
  { label: "7 Days", hours: 168 },
  { label: "30 Days", hours: 720 },
  { label: "90 Days", hours: 2160 },
] as const;

export function AnalyticsCharts() {
  const [hours, setHours] = useState<number>(24);
  const { data, isLoading } = useNotificationAnalytics(hours);

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <DashboardKPISkeleton count={4} />
        <div className="grid lg:grid-cols-2 gap-6">
          <ChartSkeleton />
          <ChartSkeleton />
        </div>
      </div>
    );
  }

  const providerRows = Object.entries(data.provider_success_rate).map(([provider, rate]) => ({
    provider,
    success_rate: Math.round(rate.success_rate * 100),
    sent: rate.sent,
    failed: rate.failed,
  }));

  const deliveryRate =
    data.total_sent > 0 ? Math.round((data.total_delivered / data.total_sent) * 100) : 0;
  const readRate =
    data.total_delivered > 0 ? Math.round((data.total_read / data.total_delivered) * 100) : 0;

  return (
    <div className="space-y-6">
      <div className="flex gap-1">
        {RANGES.map((r) => (
          <button
            key={r.hours}
            onClick={() => setHours(r.hours)}
            className={`px-3.5 py-1.5 text-xs rounded-full transition-colors ${
              hours === r.hours
                ? "bg-foreground text-background"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile label="Delivery Rate" value={`${deliveryRate}%`} />
        <StatTile label="Read Rate (WhatsApp)" value={`${readRate}%`} />
        <StatTile
          label="Avg Delivery Time"
          value={
            data.avg_delivery_seconds !== null ? `${data.avg_delivery_seconds.toFixed(1)}s` : "—"
          }
        />
        <StatTile label="Total Retried" value={String(data.total_retried)} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <ChartCard title="Daily notification volume">
          <ChartContainer
            config={{
              sent: { label: "Sent", color: "var(--accent)" },
              delivered: { label: "Delivered", color: "var(--foreground)" },
              failed: { label: "Failed", color: "#c0392b" },
            }}
          >
            <BarChart data={data.daily_totals}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="sent" fill="var(--color-sent)" radius={2} />
              <Bar dataKey="delivered" fill="var(--color-delivered)" radius={2} />
              <Bar dataKey="failed" fill="var(--color-failed)" radius={2} />
            </BarChart>
          </ChartContainer>
        </ChartCard>

        <ChartCard title="Failure trend">
          <ChartContainer config={{ failed: { label: "Failed", color: "#c0392b" } }}>
            <LineChart data={data.daily_totals}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Line
                type="monotone"
                dataKey="failed"
                stroke="var(--color-failed)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ChartContainer>
        </ChartCard>

        <ChartCard title="Provider success rate">
          <ChartContainer
            config={{ success_rate: { label: "Success Rate", color: "var(--accent)" } }}
          >
            <BarChart data={providerRows} layout="vertical">
              <CartesianGrid horizontal={false} />
              <XAxis type="number" domain={[0, 100]} tickLine={false} axisLine={false} />
              <YAxis
                dataKey="provider"
                type="category"
                tickLine={false}
                axisLine={false}
                width={80}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="success_rate" fill="var(--color-success_rate)" radius={2} />
            </BarChart>
          </ChartContainer>
        </ChartCard>

        <ChartCard title="Top templates">
          <ChartContainer config={{ sent_count: { label: "Sent", color: "var(--accent)" } }}>
            <BarChart data={data.top_templates} layout="vertical">
              <CartesianGrid horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} />
              <YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={140} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="sent_count" fill="var(--color-sent_count)" radius={2} />
            </BarChart>
          </ChartContainer>
        </ChartCard>
      </div>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-background border border-border p-5">
      <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">{label}</p>
      <p className="font-display text-3xl mt-3">{value}</p>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-background border border-border p-6">
      <h2 className="font-display text-xl mb-5">{title}</h2>
      {children}
    </div>
  );
}
