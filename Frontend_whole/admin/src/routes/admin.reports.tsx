import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { formatINR } from "@/lib/format";
import {
  DashboardKPISkeleton,
  DashboardListSkeleton,
  ChartSkeleton,
} from "@/components/loading/DashboardSkeleton";
import type { AnalyticsDashboard } from "@/types/admin";

export const Route = createFileRoute("/admin/reports")({
  component: AdminReports,
});

function AdminReports() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.analytics.dashboard,
    queryFn: () => api.get<AnalyticsDashboard>("/analytics/admin/dashboard"),
    staleTime: 5 * 60_000,
  });

  const revenueByDay = data?.revenue_by_day ?? [];
  const ordersByStatus = data?.orders_by_status ?? {};
  const topProducts = data?.top_products ?? [];

  const totalRevenue = data?.revenue?.total ?? 0;
  const totalOrders = data?.orders?.total ?? 0;
  const aovValue = data?.aov?.value ?? 0;

  const max = Math.max(1, ...revenueByDay.map((d) => d.total));

  if (isLoading) {
    return (
      <div>
        <header className="mb-8">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Analytics</p>
          <h1 className="font-display text-4xl mt-1">Reports</h1>
        </header>
        <DashboardKPISkeleton count={3} cols={3} showIcon={false} showTrend={false} />
        <div className="grid lg:grid-cols-[2fr_1fr] gap-6 mt-6">
          <div className="bg-background border border-border p-6">
            <h2 className="font-display text-xl mb-5">Daily revenue</h2>
            <ChartSkeleton />
          </div>
          <div className="bg-background border border-border p-6">
            <h2 className="font-display text-xl mb-5">Orders by status</h2>
            <DashboardListSkeleton rows={4} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Analytics</p>
        <h1 className="font-display text-4xl mt-1">Reports</h1>
      </header>

      <div className="grid sm:grid-cols-3 gap-4">
        {[
          { label: "Revenue", value: formatINR(totalRevenue) },
          { label: "Orders", value: String(totalOrders) },
          { label: "AOV", value: formatINR(aovValue) },
        ].map((s) => (
          <div key={s.label} className="bg-background border border-border p-5">
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              {s.label}
            </p>
            <p className="font-display text-3xl mt-2">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-6 mt-6">
        <div className="bg-background border border-border p-6">
          <h2 className="font-display text-xl mb-5">Daily revenue</h2>
          {revenueByDay.length === 0 ? (
            <p className="text-sm text-muted-foreground py-10 text-center">No revenue data.</p>
          ) : (
            <div className="flex items-end gap-2 h-40">
              {revenueByDay.map((d) => {
                const label = d.date?.slice(5) ?? "";
                return (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full bg-accent/70 hover:bg-accent transition"
                      style={{ height: `${(d.total / max) * 100}%` }}
                      title={`${label}: ${formatINR(d.total)}`}
                    />
                    <span className="text-[9px] text-muted-foreground rotate-45 origin-left mt-3">
                      {label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="bg-background border border-border p-6">
          <h2 className="font-display text-xl mb-5">Orders by status</h2>
          <ul className="space-y-2 text-sm">
            {Object.entries(ordersByStatus).length === 0 && (
              <li className="text-muted-foreground">No data.</li>
            )}
            {Object.entries(ordersByStatus).map(([s, n]) => (
              <li key={s} className="flex items-center justify-between">
                <span className="capitalize">{s}</span>
                <span className="font-display">{n}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {topProducts.length > 0 && (
        <div className="bg-background border border-border p-6 mt-6">
          <h2 className="font-display text-xl mb-5">Top selling products</h2>
          <ul className="divide-y divide-border">
            {topProducts.map((p) => (
              <li key={p.product_id} className="py-3 flex items-center gap-3">
                <span className="flex-1 line-clamp-1 text-sm">{p.product_name}</span>
                <span className="text-muted-foreground text-xs uppercase tracking-[0.18em]">
                  {p.total_quantity} sold
                </span>
                <span className="font-display text-sm">{formatINR(p.total_revenue)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
