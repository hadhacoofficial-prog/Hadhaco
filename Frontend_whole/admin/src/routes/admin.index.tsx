import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, ShoppingBag, Users, Package, IndianRupee, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { formatINR } from "@/lib/format";
import {
  DashboardKPISkeleton,
  DashboardListSkeleton,
} from "@/components/loading/DashboardSkeleton";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import type { KPIStats, OrderListResponse, ProductListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/")({
  component: Dashboard,
});

function Dashboard() {
  const { data: kpi, isLoading: kpiLoading } = useQuery({
    queryKey: queryKeys.admin.dashboard,
    queryFn: () => api.get<KPIStats>("/admin/dashboard"),
    staleTime: 60_000,
  });

  const { data: recentOrders, isLoading: ordersLoading } = useQuery({
    queryKey: queryKeys.admin.orders({ page: 1, page_size: 5 }),
    queryFn: () =>
      api.get<OrderListResponse>("/admin/orders", { params: { page: 1, page_size: 5 } }),
    staleTime: 60_000,
  });

  const { data: topProducts, isLoading: productsLoading } = useQuery({
    queryKey: queryKeys.admin.products({ page: 1, page_size: 5 }),
    queryFn: () =>
      api.get<ProductListResponse>("/admin/products", { params: { page: 1, page_size: 5 } }),
    staleTime: 60_000,
  });

  const stats = kpi
    ? [
        {
          label: "Today's Revenue",
          value: formatINR(kpi.today_revenue),
          icon: <IndianRupee className="size-5" />,
          trend: "Today",
        },
        {
          label: "Today's Orders",
          value: kpi.today_orders,
          icon: <ShoppingBag className="size-5" />,
          trend: `${kpi.pending_orders} pending`,
        },
        {
          label: "Low Stock",
          value: kpi.low_stock_products,
          icon: <Package className="size-5" />,
          trend: "Need restock",
        },
        {
          label: "New Customers",
          value: kpi.new_customers_today,
          icon: <Users className="size-5" />,
          trend: "Today",
        },
      ]
    : [];

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Overview</p>
        <h1 className="font-display text-4xl mt-1">Dashboard</h1>
      </header>

      {kpiLoading ? (
        <DashboardKPISkeleton />
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
              <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
                <TrendingUp className="size-3 text-accent" />
                {s.trend}
              </p>
            </div>
          ))}
        </div>
      )}

      {kpi && kpi.open_support_tickets + kpi.unresolved_fraud_signals > 0 && (
        <p className="flex items-center gap-2 text-sm text-accent mt-4">
          <AlertTriangle className="size-4" />
          {kpi.open_support_tickets} open support tickets · {kpi.unresolved_fraud_signals} fraud
          signals
        </p>
      )}

      <div className="grid lg:grid-cols-2 gap-6 mt-10">
        <div className="bg-background border border-border p-6">
          <div className="flex items-center justify-between mb-5">
            <h2 className="font-display text-xl">Recent orders</h2>
            <Link
              to="/admin/orders"
              className="text-xs uppercase tracking-[0.18em] text-accent hover:underline"
            >
              View all
            </Link>
          </div>
          {ordersLoading ? (
            <DashboardListSkeleton rows={5} />
          ) : !recentOrders || recentOrders.items.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-10">No orders yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {recentOrders.items.map((o) => (
                <li key={o.id} className="py-3 flex justify-between text-sm">
                  <span className="font-mono">#{o.order_number}</span>
                  <span className="text-muted-foreground">{o.item_count} items</span>
                  <span className="font-display">{formatINR(o.total)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-background border border-border p-6">
          <h2 className="font-display text-xl mb-5">Products</h2>
          {productsLoading ? (
            <DashboardListSkeleton rows={5} />
          ) : !topProducts || topProducts.items.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-10">No products.</p>
          ) : (
            <ul className="divide-y divide-border">
              {topProducts.items.map((p) => (
                <li key={p.id} className="py-3 flex items-center gap-3">
                  {p.primary_image ? (
                    <ImageWithFallback
                      src={p.primary_image}
                      alt=""
                      className="size-10 bg-secondary"
                    />
                  ) : (
                    <div className="size-10 bg-secondary" />
                  )}
                  <span className="text-sm flex-1 line-clamp-1">{p.name}</span>
                  <span className="font-display text-sm">{formatINR(p.base_price)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
