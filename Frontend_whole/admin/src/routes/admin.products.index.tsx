import { useMemo, useState } from "react";
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Search, Plus, Trash2, Pencil, FolderOpen, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { useDebounce } from "@hadha/shared-ui/common/use-debounce";
import type { CollectionListResponse, ProductListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/products/")({
  component: AdminProducts,
});

function AdminProducts() {
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, 300);
  const [collectionId, setCollectionId] = useState<string>("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const params = useMemo(
    () => ({
      search: debouncedQ || undefined,
      collection_id: collectionId || undefined,
      page: 1,
      page_size: 50,
    }),
    [debouncedQ, collectionId],
  );

  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: queryKeys.admin.products(params),
    queryFn: () => api.get<ProductListResponse>("/admin/products", { params }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const { data: collectionsData } = useQuery({
    queryKey: queryKeys.admin.collectionsList(),
    queryFn: () =>
      api.get<CollectionListResponse>("/admin/collections", {
        params: { page: 1, page_size: 200 },
      }),
    staleTime: 120_000,
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
  const collections = collectionsData?.items ?? [];

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
        {collections.length > 0 && (
          <div className="relative flex items-center border border-border px-3 py-2 min-w-[180px]">
            <FolderOpen className="size-4 text-muted-foreground shrink-0 mr-2" />
            <select
              value={collectionId}
              onChange={(e) => setCollectionId(e.target.value)}
              className="flex-1 bg-transparent outline-none text-sm appearance-none pr-6"
            >
              <option value="">All collections</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <ChevronDown className="size-3.5 text-muted-foreground absolute right-3 pointer-events-none" />
          </div>
        )}
      </div>

      <div
        className={`bg-background border border-border overflow-x-auto transition-opacity ${isPlaceholderData ? "opacity-60" : ""}`}
      >
        {isLoading ? (
          <TableSkeleton
            headers={["Product", "SKU", "Collections", "Price", "Stock", "Status", "Actions"]}
            rows={8}
            firstColWide
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Collections</th>
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
                        <ImageWithFallback
                          src={p.primary_image}
                          alt=""
                          className="size-10 bg-secondary shrink-0"
                        />
                      ) : (
                        <div className="size-10 bg-secondary shrink-0" />
                      )}
                      <span className="line-clamp-1 max-w-[240px]">{p.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{p.sku}</td>
                  <td className="px-4 py-3">
                    {p.collections.length === 0 ? (
                      <span className="text-muted-foreground text-xs">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {p.collections.slice(0, 2).map((c) => (
                          <Link
                            key={c.id}
                            to="/admin/collections/$collectionId"
                            params={{ collectionId: c.id }}
                            className="text-[10px] uppercase tracking-[0.15em] px-2 py-0.5 bg-secondary text-muted-foreground hover:text-foreground transition"
                          >
                            {c.name}
                          </Link>
                        ))}
                        {p.collections.length > 2 && (
                          <span className="text-[10px] text-muted-foreground px-1 py-0.5">
                            +{p.collections.length - 2}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
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
                  <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground text-sm">
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
