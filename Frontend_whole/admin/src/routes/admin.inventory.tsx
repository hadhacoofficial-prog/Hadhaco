import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Minus, Plus, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import type { LowStockItem, ProductListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/inventory")({
  component: AdminInventory,
});

function AdminInventory() {
  const queryClient = useQueryClient();

  const { data: lowStockData } = useQuery({
    queryKey: queryKeys.admin.lowStock,
    queryFn: () => api.get<LowStockItem[]>("/admin/inventory/low-stock"),
    staleTime: 60_000,
  });

  const { data: productsData, isLoading } = useQuery({
    queryKey: queryKeys.admin.products({ page: 1, page_size: 200 }),
    queryFn: () =>
      api.get<ProductListResponse>("/admin/products", { params: { page: 1, page_size: 200 } }),
    staleTime: 60_000,
  });

  const adjustMutation = useMutation({
    mutationFn: ({ id, delta }: { id: string; delta: number }) =>
      api.post<unknown>(`/admin/products/${id}/inventory/adjust`, {
        body: { delta, notes: "Admin adjustment" },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.lowStock });
      toast.success("Stock adjusted.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const products = productsData?.items ?? [];
  const lowStockIds = new Set((lowStockData ?? []).map((l) => l.id));
  const lowCount = lowStockData?.length ?? 0;

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
            Stock control
          </p>
          <h1 className="font-display text-4xl mt-1">Inventory</h1>
          {lowCount > 0 && (
            <p className="text-sm text-muted-foreground mt-2 inline-flex items-center gap-2">
              <AlertTriangle className="size-3.5 text-accent" />
              {lowCount} SKU{lowCount === 1 ? "" : "s"} below threshold
            </p>
          )}
        </div>
      </header>

      <div className="bg-background border border-border overflow-x-auto">
        {isLoading ? (
          <TableSkeleton
            headers={["Product", "SKU", "Quantity", "Committed", "Available", "Actions"]}
            rows={8}
            firstColWide
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">On hand</th>
                <th className="px-4 py-3">Adjust</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {products.map((p) => {
                const isLow = lowStockIds.has(p.id);
                return (
                  <tr key={p.id}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        {p.primary_image ? (
                          <img
                            src={p.primary_image}
                            alt=""
                            className="size-10 object-cover bg-secondary shrink-0"
                          />
                        ) : (
                          <div className="size-10 bg-secondary shrink-0" />
                        )}
                        <span className="line-clamp-1 max-w-[280px]">{p.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{p.sku}</td>
                    <td className="px-4 py-3">{p.stock_quantity}</td>
                    <td className="px-4 py-3">
                      <div className="inline-flex gap-1">
                        <button
                          onClick={() => adjustMutation.mutate({ id: p.id, delta: -1 })}
                          disabled={adjustMutation.isPending}
                          className="border border-border p-1 hover:bg-secondary disabled:opacity-50"
                        >
                          <Minus className="size-3.5" />
                        </button>
                        <button
                          onClick={() => adjustMutation.mutate({ id: p.id, delta: 1 })}
                          disabled={adjustMutation.isPending}
                          className="border border-border p-1 hover:bg-secondary disabled:opacity-50"
                        >
                          <Plus className="size-3.5" />
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                          p.stock_quantity === 0
                            ? "bg-destructive/15 text-destructive"
                            : isLow
                              ? "bg-accent/15 text-accent"
                              : "text-muted-foreground"
                        }`}
                      >
                        {p.stock_quantity === 0 ? "Out" : isLow ? "Low" : "Healthy"}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {products.length === 0 && !isLoading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground text-sm">
                    No products found.
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
