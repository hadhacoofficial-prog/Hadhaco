import { useMemo, useState } from "react";
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import type { ProductListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/products/")({
  component: AdminProducts,
});

function AdminProducts() {
  const [q, setQ] = useState("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const params = useMemo(() => ({ search: q || undefined, page: 1, page_size: 50 }), [q]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.products(params),
    queryFn: () => api.get<ProductListResponse>("/admin/products", { params }),
    staleTime: 60_000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/admin/products/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      toast.success("Product deleted.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const list = data?.items ?? [];

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Catalogue</p>
          <h1 className="font-display text-4xl mt-1">
            Products <span className="text-muted-foreground text-2xl">({data?.total ?? 0})</span>
          </h1>
        </div>
        <button
          onClick={() => navigate({ to: "/admin/products/new" })}
          className="inline-flex items-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-5 py-3 hover:opacity-90 transition-opacity"
        >
          <Plus className="size-3.5" />
          New Product
        </button>
      </header>

      <div className="bg-background border border-border p-4 flex flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-2 border border-border px-3 py-2 flex-1 min-w-[200px]">
          <Search className="size-4 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name or SKU…"
            className="flex-1 bg-transparent outline-none text-sm"
          />
        </div>
      </div>

      <div className="bg-background border border-border overflow-x-auto">
        {isLoading ? (
          <TableSkeleton
            headers={["Product", "SKU", "Price", "Stock", "Status", "Actions"]}
            rows={8}
            firstColWide
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Price</th>
                <th className="px-4 py-3">Stock</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.map((p) => (
                <tr key={p.id} className="hover:bg-secondary/40">
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
                  <td className="px-4 py-3 font-display">{formatINR(p.base_price)}</td>
                  <td className="px-4 py-3">{p.stock_quantity}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                        p.status === "active"
                          ? "bg-accent/15 text-accent"
                          : p.status === "draft"
                            ? "bg-secondary text-muted-foreground"
                            : "bg-destructive/15 text-destructive"
                      }`}
                    >
                      {p.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <Link
                        to="/admin/products/$productId"
                        params={{ productId: p.id }}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <Pencil className="size-4" />
                      </Link>
                      <button
                        onClick={() => {
                          if (confirm(`Delete "${p.name}"?`)) deleteMutation.mutate(p.id);
                        }}
                        disabled={deleteMutation.isPending}
                        className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground text-sm">
                    No products match your filters.
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
