import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import type { OrderListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/orders")({
  component: AdminOrders,
});

const STATUSES = ["confirmed", "processing", "shipped", "delivered", "cancelled"] as const;
type OrderStatus = (typeof STATUSES)[number];

function AdminOrders() {
  const [filter, setFilter] = useState<"all" | OrderStatus>("all");
  const queryClient = useQueryClient();

  const params = {
    page: 1,
    page_size: 50,
    status: filter === "all" ? undefined : filter,
  };

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.orders(params),
    queryFn: () => api.get<OrderListResponse>("/admin/orders", { params }),
    staleTime: 30_000,
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch<unknown>(`/admin/orders/${id}/status`, { body: { status } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
      toast.success("Order status updated.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const list = data?.items ?? [];

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Fulfilment</p>
        <h1 className="font-display text-4xl mt-1">
          Orders <span className="text-muted-foreground text-2xl">({data?.total ?? 0})</span>
        </h1>
      </header>

      <div className="flex flex-wrap gap-2 mb-4">
        {(["all", ...STATUSES] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`text-[11px] uppercase tracking-[0.22em] px-4 py-2 border transition ${
              filter === s
                ? "bg-foreground text-background border-foreground"
                : "border-border hover:border-foreground"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="bg-background border border-border overflow-x-auto">
        {isLoading ? (
          <TableSkeleton
            headers={["Order #", "Date", "Items", "Total", "Payment", "Status"]}
            rows={8}
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Order #</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Items</th>
                <th className="px-4 py-3">Total</th>
                <th className="px-4 py-3">Payment</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.map((o) => (
                <tr key={o.id}>
                  <td className="px-4 py-3 font-mono text-xs">#{o.order_number}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(o.created_at).toLocaleDateString("en-IN")}
                  </td>
                  <td className="px-4 py-3">{o.item_count}</td>
                  <td className="px-4 py-3 font-display">{formatINR(o.total)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                        o.payment_status === "paid"
                          ? "bg-accent/15 text-accent"
                          : o.payment_status === "failed"
                            ? "bg-destructive/15 text-destructive"
                            : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      {o.payment_status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={o.status}
                      onChange={(e) => statusMutation.mutate({ id: o.id, status: e.target.value })}
                      disabled={statusMutation.isPending}
                      className="border border-border bg-background text-xs px-2 py-1 disabled:opacity-50"
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground text-sm">
                    No orders to show.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
