import { useCallback, useMemo } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { toast } from "sonner";
import { Eye, Loader2 } from "lucide-react";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import { SortableHeader, nextSort, type SortState } from "@hadha/shared-ui/data/SortableHeader";
import { TableSearchInput } from "@hadha/shared-ui/data/TableSearchInput";
import { FilterSelect } from "@hadha/shared-ui/data/FilterSelect";
import {
  DateRangeFilter,
  describeDateRange,
  resolveDateRange,
  type DateRangeValue,
} from "@hadha/shared-ui/data/DateRangeFilter";
import { NumberRangeFilter, type NumberRange } from "@hadha/shared-ui/data/NumberRangeFilter";
import {
  dateRangeFields,
  dateRangeFromSearch,
  dateRangeToSearch,
  patchSearch,
  useClampPage,
  sortFromSearch,
  sortToSearch,
  urlAmount,
  urlDir,
  urlEnum,
  urlPage,
  urlText,
  useUrlSearchText,
} from "@/lib/tableUrlState";
import { ActiveFilterChips, type FilterChip } from "@hadha/shared-ui/data/ActiveFilterChips";
import { TablePagination } from "@hadha/shared-ui/data/TablePagination";
import type { OrderListResponse } from "@/types/admin";

const STATUSES = ["confirmed", "processing", "shipped", "delivered", "cancelled"] as const;
type OrderStatus = (typeof STATUSES)[number];

const FULFILLMENT_STATUS_STYLES: Record<string, string> = {
  pending: "bg-secondary text-muted-foreground",
  packing: "bg-blue-500/15 text-blue-700",
  label_generated: "bg-indigo-500/15 text-indigo-700",
  dispatched: "bg-amber-500/15 text-amber-700",
  in_transit: "bg-orange-500/15 text-orange-700",
  delivered: "bg-accent/15 text-accent",
  cancelled: "bg-destructive/15 text-destructive",
};

const PAYMENT_STATUSES = ["paid", "pending", "failed", "refunded", "partially_refunded"] as const;
const PAYMENT_OPTIONS = [
  { value: "paid", label: "Paid" },
  { value: "pending", label: "Pending" },
  { value: "failed", label: "Failed" },
  { value: "refunded", label: "Refunded" },
  { value: "partially_refunded", label: "Partially refunded" },
];
const FULFILLMENT_STATUSES = [
  "pending",
  "packing",
  "label_generated",
  "dispatched",
  "in_transit",
  "delivered",
  "cancelled",
] as const;

const FULFILLMENT_OPTIONS = Object.keys(FULFILLMENT_STATUS_STYLES).map((v) => ({
  value: v,
  label: v.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
}));

const SORT_KEYS = ["order_number", "created_at", "total", "payment_status", "status"] as const;
type SortKey = (typeof SORT_KEYS)[number];
const DEFAULT_SORT: SortState<SortKey> = { sortBy: "created_at", sortDir: "desc" };
const FIRST_DIR = { order_number: "asc", payment_status: "asc", status: "asc" } as const;

const ordersSearchSchema = z.object({
  status: urlEnum(STATUSES),
  q: urlText,
  payment: urlEnum(PAYMENT_STATUSES),
  fulfillment: urlEnum(FULFILLMENT_STATUSES),
  ...dateRangeFields,
  minTotal: urlAmount,
  maxTotal: urlAmount,
  sort: urlEnum(SORT_KEYS),
  dir: urlDir,
  page: urlPage,
});
type OrdersSearch = z.infer<typeof ordersSearchSchema>;

export const Route = createFileRoute("/admin/orders/")({
  validateSearch: ordersSearchSchema,
  component: AdminOrders,
});

function AdminOrders() {
  // All view state lives in the URL (refresh / back / shared links keep it).
  const urlSearch = Route.useSearch();
  const navigateSearch = Route.useNavigate();
  const update = useCallback(
    (patch: Partial<OrdersSearch>, replace = false) =>
      navigateSearch({ search: (prev) => patchSearch(prev, patch), replace }),
    [navigateSearch],
  );

  const [search, setSearch] = useUrlSearchText(urlSearch.q, (q) => update({ q }));
  const debouncedSearch = urlSearch.q ?? "";
  const filter: "all" | OrderStatus = urlSearch.status ?? "all";
  const payment = urlSearch.payment ?? "";
  const fulfillment = urlSearch.fulfillment ?? "";
  const placed = dateRangeFromSearch(urlSearch);
  const totalRange: NumberRange = { min: urlSearch.minTotal, max: urlSearch.maxTotal };
  const page = urlSearch.page ?? 1;
  const sort = sortFromSearch(urlSearch, DEFAULT_SORT);
  const onSort = (key: SortKey) =>
    update(sortToSearch(nextSort(sort, key, FIRST_DIR), DEFAULT_SORT));

  const setFilter = (v: "all" | OrderStatus) => update({ status: v === "all" ? undefined : v });
  const setPayment = (v: string) =>
    update({ payment: (v || undefined) as OrdersSearch["payment"] });
  const setFulfillment = (v: string) =>
    update({ fulfillment: (v || undefined) as OrdersSearch["fulfillment"] });
  const setPlaced = (v: DateRangeValue) => update(dateRangeToSearch(v));
  const setTotalRange = (v: NumberRange) => update({ minTotal: v.min, maxTotal: v.max });
  const setPage = (p: number) => update({ page: p > 1 ? p : undefined });

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const params = useMemo(
    () => ({
      page,
      page_size: 15,
      status: urlSearch.status,
      search: urlSearch.q,
      payment_status: urlSearch.payment,
      fulfillment_status: urlSearch.fulfillment,
      min_total: urlSearch.minTotal,
      max_total: urlSearch.maxTotal,
      sort_by: sort.sortBy,
      sort_dir: sort.sortDir,
      ...resolveDateRange(dateRangeFromSearch(urlSearch)),
    }),
    [urlSearch, page, sort.sortBy, sort.sortDir],
  );

  const chips: FilterChip[] = [];
  if (debouncedSearch)
    chips.push({
      key: "q",
      label: `Search: "${debouncedSearch}"`,
      onRemove: () => update({ q: undefined }),
    });
  if (payment)
    chips.push({
      key: "payment",
      label: `Payment: ${PAYMENT_OPTIONS.find((o) => o.value === payment)?.label ?? payment}`,
      onRemove: () => setPayment(""),
    });
  if (fulfillment)
    chips.push({
      key: "fulfillment",
      label: `Fulfilment: ${fulfillment.replace(/_/g, " ")}`,
      onRemove: () => setFulfillment(""),
    });
  const placedLabel = describeDateRange(placed);
  if (placedLabel)
    chips.push({
      key: "placed",
      label: `Placed: ${placedLabel}`,
      onRemove: () => setPlaced({ preset: "any" }),
    });
  if (totalRange.min !== undefined || totalRange.max !== undefined)
    chips.push({
      key: "total",
      label: `Total: ${totalRange.min !== undefined ? formatINR(totalRange.min) : "₹0"} – ${
        totalRange.max !== undefined ? formatINR(totalRange.max) : "any"
      }`,
      onRemove: () => setTotalRange({}),
    });
  // One navigation so nothing races; keeps the sort (and the status tab
  // unless `includeStatus`).
  const clearAll = (includeStatus = false) =>
    update({
      q: undefined,
      payment: undefined,
      fulfillment: undefined,
      date: undefined,
      from: undefined,
      to: undefined,
      minTotal: undefined,
      maxTotal: undefined,
      ...(includeStatus ? { status: undefined } : {}),
    });

  const header = (key: SortKey, label: string) => (
    <SortableHeader label={label} sortKey={key} sort={sort} onSort={onSort} />
  );

  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: queryKeys.admin.orders(params),
    queryFn: () => api.get<OrderListResponse>("/admin/orders", { params }),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch<unknown>(`/admin/orders/${id}/status`, { body: { status } }),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.orders() });
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.order(id) });
      toast.success("Order status updated.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const list = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  useClampPage(
    page,
    data ? { itemCount: list.length, totalPages } : undefined,
    isPlaceholderData,
    (last) => update({ page: last > 1 ? last : undefined }, true),
  );
  const total = data?.total ?? 0;

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Fulfilment</p>
        <h1 className="font-display text-4xl mt-1">
          Orders <span className="text-muted-foreground text-2xl">({data?.total ?? 0})</span>
        </h1>
      </header>

      <div className="flex flex-wrap gap-2 mb-4" role="group" aria-label="Order status">
        {(["all", ...STATUSES] as const).map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={filter === s}
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

      <div className="bg-background border border-border p-4 flex flex-wrap items-center gap-3 mb-3">
        <TableSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search order #, customer name, phone or email…"
          className="flex-1"
        />
        <FilterSelect
          label="Payment"
          allLabel="All payments"
          value={payment}
          onChange={setPayment}
          options={PAYMENT_OPTIONS}
          className="w-40"
        />
        <FilterSelect
          label="Fulfilment"
          allLabel="All fulfilment"
          value={fulfillment}
          onChange={setFulfillment}
          options={FULFILLMENT_OPTIONS}
          className="w-44"
        />
        <DateRangeFilter label="Placed" value={placed} onChange={setPlaced} />
        <NumberRangeFilter
          label="Order total"
          prefix="₹"
          value={totalRange}
          onChange={setTotalRange}
        />
      </div>

      <ActiveFilterChips chips={chips} onClearAll={() => clearAll()} className="mb-4" />

      <div
        className={`bg-background border border-border overflow-x-auto transition-opacity ${isPlaceholderData ? "opacity-60" : ""}`}
        aria-busy={isPlaceholderData}
      >
        {isLoading ? (
          <TableSkeleton
            headers={[
              "Order #",
              "Date",
              "Items",
              "Total",
              "Payment",
              "Status",
              "Fulfillment",
              "Gift",
              "",
            ]}
            rows={8}
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                {header("order_number", "Order #")}
                {header("created_at", "Date")}
                <th className="px-4 py-3">Items</th>
                {header("total", "Total")}
                {header("payment_status", "Payment")}
                {header("status", "Status")}
                <th className="px-4 py-3">Fulfillment</th>
                <th className="px-4 py-3">Gift</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.map((o) => {
                const isRowUpdating =
                  statusMutation.isPending && statusMutation.variables?.id === o.id;
                return (
                  <tr
                    key={o.id}
                    className="hover:bg-secondary cursor-pointer"
                    onClick={() =>
                      navigate({ to: "/admin/orders/$orderId", params: { orderId: o.id } })
                    }
                  >
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
                      <div className="inline-flex items-center gap-1.5">
                        <select
                          value={o.status}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => {
                            e.stopPropagation();
                            statusMutation.mutate({ id: o.id, status: e.target.value });
                          }}
                          disabled={isRowUpdating}
                          aria-busy={isRowUpdating}
                          className="border border-border bg-background text-xs px-2 py-1 disabled:opacity-50"
                        >
                          {STATUSES.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                        {isRowUpdating && (
                          <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                          FULFILLMENT_STATUS_STYLES[o.fulfillment_status] ??
                          "bg-secondary text-muted-foreground"
                        }`}
                      >
                        {o.fulfillment_status.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {o.complimentary_gift ? (
                        <span className="text-[10px] uppercase tracking-[0.16em] inline-flex items-center gap-1">
                          <span>{o.complimentary_gift === "Traditional Sweet" ? "🍬" : "🌶️"}</span>
                          <span className="text-muted-foreground">{o.complimentary_gift}</span>
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() =>
                          navigate({ to: "/admin/orders/$orderId", params: { orderId: o.id } })
                        }
                        className="flex items-center gap-1 text-[10px] uppercase tracking-[0.22em] text-muted-foreground hover:text-foreground transition"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        View
                      </button>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-muted-foreground text-sm">
                    {chips.length || filter !== "all" ? (
                      <>
                        No orders match these filters.{" "}
                        <button
                          type="button"
                          onClick={() => clearAll(true)}
                          className="underline underline-offset-4 text-foreground"
                        >
                          Clear filters
                        </button>
                      </>
                    ) : (
                      "No orders to show."
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <TablePagination
        page={page}
        totalPages={totalPages}
        total={total}
        noun="orders"
        onPageChange={setPage}
      />
    </div>
  );
}
