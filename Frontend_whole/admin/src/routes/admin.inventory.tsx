import { useEffect, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import {
  Search,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Loader2,
  RefreshCw,
  Boxes,
  PackageX,
  Lock,
  Clock,
} from "lucide-react";
import { toast } from "sonner";
import { ENV } from "@hadha/shared-api";
import { useDebounce } from "@hadha/shared-ui/common/use-debounce";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  CategoryAdminListResponse,
  CollectionListResponse,
  InventoryMovementListResponse,
  ReservationListResponse,
  StockAdjustMode,
  StockAdjustReason,
  VariantInventoryListResponse,
  VariantInventoryRow,
  VariantOrderHistoryResponse,
} from "@/types/admin";

export const Route = createFileRoute("/admin/inventory")({
  component: AdminInventory,
});

const REASON_LABELS: Record<StockAdjustReason, string> = {
  RESTOCK: "Restock",
  DAMAGE: "Damage",
  CORRECTION: "Correction",
  RETURN: "Return",
  THEFT_LOSS: "Theft / Loss",
  RECOUNT: "Recount",
  OTHER: "Other",
};

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "updated_at", label: "Last Updated" },
  { value: "available_stock", label: "Available Stock" },
  { value: "stock_quantity", label: "Total Stock" },
  { value: "product_name", label: "Product Name" },
  { value: "sku", label: "SKU" },
];

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatAdjustmentChip(row: VariantInventoryRow): string | null {
  const adj = row.last_adjustment;
  if (!adj) return null;
  const reasonLabel = adj.reason
    ? (REASON_LABELS[adj.reason as StockAdjustReason] ?? adj.reason)
    : "";
  let sign = "";
  if (adj.mode === "ADD") sign = "+";
  else if (adj.mode === "REMOVE") sign = "-";
  else if (adj.mode === "SET") sign = "Set ";
  return `${sign}${adj.quantity} ${reasonLabel} • ${timeAgo(adj.at)}`;
}

// ── Live-update SSE banner ────────────────────────────────────────────────────
// Deliberately does NOT auto-refetch on receipt — silently yanking rows out
// from under an admin mid-edit is worse than a one-click banner. Uses a raw
// EventSource (not the full storefront SyncBus, which pulls in cart/checkout/
// wishlist domain modules this admin page has no use for).

function useInventoryLiveUpdateBanner(): [boolean, () => void] {
  const [hasUpdate, setHasUpdate] = useState(false);

  useEffect(() => {
    if (typeof EventSource === "undefined" || !ENV.apiBaseUrl) return;
    const url = `${ENV.apiBaseUrl.replace(/\/+$/, "")}/events/stream`;
    const es = new EventSource(url, { withCredentials: true });

    const handleMessage = (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data) as { event?: string; type?: string };
        const eventType = parsed.event ?? parsed.type;
        if (eventType === "inventory_changed") setHasUpdate(true);
      } catch {
        // Malformed SSE payload — ignore.
      }
    };

    es.onmessage = handleMessage;
    es.addEventListener("sync", handleMessage);

    return () => es.close();
  }, []);

  return [hasUpdate, () => setHasUpdate(false)];
}

function AdminInventory() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("updated_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [variantStatus, setVariantStatus] = useState("");
  const [hasReservations, setHasReservations] = useState(false);
  const [recentlyUpdated, setRecentlyUpdated] = useState(false);
  const [categoryId, setCategoryId] = useState("");
  const [collectionId, setCollectionId] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [adjustTarget, setAdjustTarget] = useState<VariantInventoryRow | null>(null);
  const [hasLiveUpdate, dismissLiveUpdate] = useInventoryLiveUpdateBanner();

  const params = useMemo(
    () => ({
      page,
      page_size: 20,
      search: debouncedSearch || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      variant_status: variantStatus || undefined,
      has_reservations: hasReservations || undefined,
      recently_updated_hours: recentlyUpdated ? 24 : undefined,
      category_id: categoryId || undefined,
      collection_id: collectionId || undefined,
    }),
    [
      page,
      debouncedSearch,
      sortBy,
      sortDir,
      variantStatus,
      hasReservations,
      recentlyUpdated,
      categoryId,
      collectionId,
    ],
  );

  useEffect(() => {
    setPage(1);
  }, [
    debouncedSearch,
    sortBy,
    sortDir,
    variantStatus,
    hasReservations,
    recentlyUpdated,
    categoryId,
    collectionId,
  ]);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.productVariants(params),
    queryFn: () => api.get<VariantInventoryListResponse>("/admin/product-variants", { params }),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const { data: categoriesData } = useQuery({
    queryKey: queryKeys.admin.categoriesList({ page: 1, page_size: 200 }),
    queryFn: () =>
      api.get<CategoryAdminListResponse>("/admin/categories", {
        params: { page: 1, page_size: 200 },
      }),
    staleTime: 300_000,
  });

  const { data: collectionsData } = useQuery({
    queryKey: queryKeys.admin.collectionsList(),
    queryFn: () =>
      api.get<CollectionListResponse>("/admin/collections", {
        params: { page: 1, page_size: 200 },
      }),
    staleTime: 300_000,
  });

  const adjustMutation = useMutation({
    mutationFn: ({
      productId,
      variantId,
      mode,
      quantity,
      reason,
      notes,
    }: {
      productId: string;
      variantId: string;
      mode: StockAdjustMode;
      quantity: number;
      reason: StockAdjustReason;
      notes: string;
    }) =>
      api.post<unknown>(`/admin/products/${productId}/stock/adjust`, {
        body: { mode, quantity, reason, notes: notes || undefined, variant_id: variantId },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "product-variants"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "inventory"] });
      toast.success("Stock adjusted.");
      setAdjustTarget(null);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const items = data?.items ?? [];
  const summary = data?.summary;
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;
  const categories = categoriesData?.items ?? [];
  const collections = collectionsData?.items ?? [];

  const filterChips: { key: string; label: string; active: boolean; onClick: () => void }[] = [
    {
      key: "active",
      label: "Active",
      active: variantStatus === "active",
      onClick: () => setVariantStatus((v) => (v === "active" ? "" : "active")),
    },
    {
      key: "inactive",
      label: "Inactive",
      active: variantStatus === "inactive",
      onClick: () => setVariantStatus((v) => (v === "inactive" ? "" : "inactive")),
    },
    {
      key: "out_of_stock",
      label: "Out of Stock",
      active: variantStatus === "out_of_stock",
      onClick: () => setVariantStatus((v) => (v === "out_of_stock" ? "" : "out_of_stock")),
    },
    {
      key: "has_reservations",
      label: "Has Reservations",
      active: hasReservations,
      onClick: () => setHasReservations((v) => !v),
    },
    {
      key: "recently_updated",
      label: "Recently Updated",
      active: recentlyUpdated,
      onClick: () => setRecentlyUpdated((v) => !v),
    },
  ];

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
            Stock control
          </p>
          <h1 className="font-display text-4xl mt-1">Inventory</h1>
        </div>
      </header>

      {hasLiveUpdate && (
        <div className="mb-6 flex items-center justify-between gap-3 border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm">
          <span className="flex items-center gap-2 text-accent">
            <RefreshCw className="size-3.5" />
            Inventory updated elsewhere
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["admin", "product-variants"] });
              dismissLiveUpdate();
            }}
          >
            Refresh
          </Button>
        </div>
      )}

      {/* KPI tiles */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-px bg-border mb-6 border border-border">
          <KpiTile label="Total Variants" value={summary.total_variants} />
          <KpiTile
            label="Low Stock"
            value={summary.low_stock_variants}
            icon={<AlertTriangle className="size-3.5" />}
            accent={summary.low_stock_variants > 0}
          />
          <KpiTile
            label="Out of Stock"
            value={summary.out_of_stock_variants}
            icon={<PackageX className="size-3.5" />}
            accent={summary.out_of_stock_variants > 0}
            destructive
          />
          <KpiTile
            label="Reserved Units"
            value={summary.reserved_units}
            icon={<Lock className="size-3.5" />}
          />
          <KpiTile
            label="Available Units"
            value={summary.available_units}
            icon={<Boxes className="size-3.5" />}
          />
          <KpiTile label="Total Units" value={summary.total_inventory_units} />
        </div>
      )}

      {/* Search + sort */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by product, SKU, variant, or category…"
            className="pl-9"
          />
        </div>
        <Select value={sortBy} onValueChange={setSortBy}>
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="icon"
          onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
          aria-label="Toggle sort direction"
        >
          {sortDir === "asc" ? (
            <ChevronUp className="size-4" />
          ) : (
            <ChevronDown className="size-4" />
          )}
        </Button>
        {categories.length > 0 && (
          <Select
            value={categoryId || "__all"}
            onValueChange={(v) => setCategoryId(v === "__all" ? "" : v)}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">All Categories</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {collections.length > 0 && (
          <Select
            value={collectionId || "__all"}
            onValueChange={(v) => setCollectionId(v === "__all" ? "" : v)}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Collection" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">All Collections</SelectItem>
              {collections.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2 mb-6">
        {filterChips.map((chip) => (
          <button
            key={chip.key}
            onClick={chip.onClick}
            className={`text-xs px-3 py-1.5 border transition-colors ${
              chip.active
                ? "bg-foreground text-background border-foreground"
                : "border-border text-muted-foreground hover:bg-secondary"
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      <div className="bg-background border border-border overflow-x-auto">
        {isLoading ? (
          <TableSkeleton
            headers={["Variant", "SKU", "Stock", "Reserved", "Available", "Status", ""]}
            rows={8}
            firstColWide
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Product / Variant</th>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Stock</th>
                <th className="px-4 py-3">Reserved</th>
                <th className="px-4 py-3">Available</th>
                <th className="px-4 py-3">Last Adjustment</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((row) => (
                <VariantRow
                  key={row.variant_id}
                  row={row}
                  expanded={expandedId === row.variant_id}
                  onToggleExpand={() =>
                    setExpandedId((id) => (id === row.variant_id ? null : row.variant_id))
                  }
                  onAdjust={() => setAdjustTarget(row)}
                />
              ))}
              {items.length === 0 && !isLoading && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-muted-foreground text-sm">
                    No variants found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} · {total} variants
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 border border-border hover:bg-secondary disabled:opacity-50"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 border border-border hover:bg-secondary disabled:opacity-50"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      )}

      {adjustTarget && (
        <StockAdjustDialog
          row={adjustTarget}
          open={Boolean(adjustTarget)}
          onOpenChange={(open) => !open && setAdjustTarget(null)}
          onSubmit={(payload) =>
            adjustMutation.mutate({
              productId: adjustTarget.product_id,
              variantId: adjustTarget.variant_id,
              ...payload,
            })
          }
          isSubmitting={adjustMutation.isPending}
        />
      )}
    </div>
  );
}

// ── KPI tile ──────────────────────────────────────────────────────────────────

function KpiTile({
  label,
  value,
  icon,
  accent,
  destructive,
}: {
  label: string;
  value: number;
  icon?: React.ReactNode;
  accent?: boolean;
  destructive?: boolean;
}) {
  return (
    <div className="bg-background p-4">
      <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground flex items-center gap-1.5">
        {icon}
        {label}
      </p>
      <p
        className={`text-2xl font-display mt-1 ${
          destructive && accent ? "text-destructive" : accent ? "text-accent" : ""
        }`}
      >
        {value.toLocaleString()}
      </p>
    </div>
  );
}

// ── Variant row (+ expand panel) ─────────────────────────────────────────────

function VariantRow({
  row,
  expanded,
  onToggleExpand,
  onAdjust,
}: {
  row: VariantInventoryRow;
  expanded: boolean;
  onToggleExpand: () => void;
  onAdjust: () => void;
}) {
  const adjustmentLabel = formatAdjustmentChip(row);

  return (
    <>
      <tr className="align-top">
        <td className="px-4 py-3">
          <button onClick={onToggleExpand} className="flex items-center gap-3 text-left w-full">
            {expanded ? (
              <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
            )}
            {row.primary_image ? (
              <ImageWithFallback
                src={row.primary_image}
                alt=""
                className="size-10 bg-secondary shrink-0"
              />
            ) : (
              <div className="size-10 bg-secondary shrink-0" />
            )}
            <span className="min-w-0">
              <span className="line-clamp-1 max-w-[260px] block">{row.product_name}</span>
              <span className="text-xs text-muted-foreground">{row.variant_name}</span>
            </span>
          </button>
        </td>
        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{row.sku}</td>
        <td className="px-4 py-3">{row.stock_quantity}</td>
        <td className="px-4 py-3">{row.reserved_quantity}</td>
        <td className="px-4 py-3 font-medium">{row.available_stock}</td>
        <td className="px-4 py-3 text-xs text-muted-foreground">{adjustmentLabel ?? "—"}</td>
        <td className="px-4 py-3">
          <span
            className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 inline-block ${
              row.available_stock === 0
                ? "bg-destructive/15 text-destructive"
                : row.is_low_stock
                  ? "bg-accent/15 text-accent"
                  : "text-muted-foreground"
            }`}
          >
            {row.available_stock === 0 ? "Out" : row.is_low_stock ? "Low" : "Healthy"}
          </span>
          {!row.is_active && (
            <span className="block text-[10px] uppercase tracking-[0.18em] text-muted-foreground mt-1">
              Inactive
            </span>
          )}
        </td>
        <td className="px-4 py-3">
          <Button size="sm" variant="outline" onClick={onAdjust}>
            Adjust
          </Button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8} className="bg-secondary/40 px-4 py-4">
            <VariantExpandPanel row={row} />
          </td>
        </tr>
      )}
    </>
  );
}

// ── Expand panel: movements, reservations, orders ────────────────────────────

function VariantExpandPanel({ row }: { row: VariantInventoryRow }) {
  const { data: movementsData, isLoading: movementsLoading } = useQuery({
    queryKey: queryKeys.admin.variantMovements(row.variant_id),
    queryFn: () =>
      api.get<InventoryMovementListResponse>(`/admin/products/${row.product_id}/inventory`, {
        params: { variant_id: row.variant_id, page_size: 10 },
      }),
    staleTime: 15_000,
  });

  const { data: reservationsData, isLoading: reservationsLoading } = useQuery({
    queryKey: queryKeys.admin.variantReservations(row.variant_id),
    queryFn: () =>
      api.get<ReservationListResponse>("/admin/inventory/reservations", {
        params: { variant_id: row.variant_id, page_size: 10 },
      }),
    staleTime: 15_000,
  });

  const { data: ordersData, isLoading: ordersLoading } = useQuery({
    queryKey: queryKeys.admin.variantOrders(row.variant_id),
    queryFn: () =>
      api.get<VariantOrderHistoryResponse>(`/admin/product-variants/${row.variant_id}/orders`, {
        params: { page_size: 10 },
      }),
    staleTime: 15_000,
  });

  return (
    <div className="grid md:grid-cols-3 gap-6 text-xs">
      <div>
        <p className="uppercase tracking-[0.18em] text-muted-foreground mb-2">Recent Movements</p>
        {movementsLoading ? (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        ) : movementsData && movementsData.items.length > 0 ? (
          <ul className="space-y-1.5">
            {movementsData.items.map((m) => (
              <li key={m.id} className="flex justify-between gap-2">
                <span className="text-muted-foreground">{m.movement_type}</span>
                <span>
                  {m.delta > 0 ? "+" : ""}
                  {m.delta} · {timeAgo(m.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No movement history.</p>
        )}
      </div>

      <div>
        <p className="uppercase tracking-[0.18em] text-muted-foreground mb-2">
          Active Reservations
        </p>
        {reservationsLoading ? (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        ) : reservationsData && reservationsData.items.length > 0 ? (
          <ul className="space-y-1.5">
            {reservationsData.items.map((r) => (
              <li key={r.id} className="flex justify-between gap-2">
                <span className="text-muted-foreground font-mono">{r.reservation_number}</span>
                <span className="flex items-center gap-1">
                  <Clock className="size-3" />
                  {r.quantity} · {r.status}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No active reservations.</p>
        )}
      </div>

      <div>
        <p className="uppercase tracking-[0.18em] text-muted-foreground mb-2">Recent Orders</p>
        {ordersLoading ? (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        ) : ordersData && ordersData.items.length > 0 ? (
          <ul className="space-y-1.5">
            {ordersData.items.map((o) => (
              <li key={o.order_id} className="flex justify-between gap-2">
                <span className="text-muted-foreground font-mono">{o.order_number}</span>
                <span>
                  {o.quantity} · {timeAgo(o.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No orders yet.</p>
        )}
      </div>
    </div>
  );
}

// ── Stock adjustment dialog ───────────────────────────────────────────────────

function StockAdjustDialog({
  row,
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  row: VariantInventoryRow;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: {
    mode: StockAdjustMode;
    quantity: number;
    reason: StockAdjustReason;
    notes: string;
  }) => void;
  isSubmitting: boolean;
}) {
  const [mode, setMode] = useState<StockAdjustMode>("add");
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState<StockAdjustReason>("RESTOCK");
  const [notes, setNotes] = useState("");

  const parsedQuantity = Number(quantity);
  const isValid = Number.isFinite(parsedQuantity) && parsedQuantity >= 0;

  const handleSubmit = () => {
    if (!isValid) return;
    onSubmit({ mode, quantity: parsedQuantity, reason, notes });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Adjust Stock</DialogTitle>
          <DialogDescription>
            {row.product_name} — {row.variant_name} ({row.sku}). Current stock: {row.stock_quantity}
            .
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            {(["add", "remove", "set"] as StockAdjustMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`text-xs uppercase tracking-[0.15em] py-2 border transition-colors ${
                  mode === m
                    ? "bg-foreground text-background border-foreground"
                    : "border-border text-muted-foreground hover:bg-secondary"
                }`}
              >
                {m === "add" ? "Add" : m === "remove" ? "Remove" : "Set Exact"}
              </button>
            ))}
          </div>

          <div>
            <label className="text-xs uppercase tracking-[0.15em] text-muted-foreground block mb-1">
              {mode === "set" ? "New quantity" : "Quantity"}
            </label>
            <Input
              type="number"
              min={0}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs uppercase tracking-[0.15em] text-muted-foreground block mb-1">
              Reason
            </label>
            <Select value={reason} onValueChange={(v) => setReason(v as StockAdjustReason)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(REASON_LABELS) as StockAdjustReason[]).map((r) => (
                  <SelectItem key={r} value={r}>
                    {REASON_LABELS[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="text-xs uppercase tracking-[0.15em] text-muted-foreground block mb-1">
              Notes (optional)
            </label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Additional context for this adjustment…"
              className="resize-none"
            />
          </div>

          <div className="flex gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
              className="flex-1"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSubmit}
              loading={isSubmitting}
              disabled={!isValid}
              className="flex-1"
            >
              {isSubmitting ? "Saving…" : "Save Adjustment"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
