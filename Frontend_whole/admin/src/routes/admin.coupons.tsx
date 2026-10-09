import { useCallback, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Loader2, Plus, Tag, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { SortableHeader, nextSort, type SortState } from "@hadha/shared-ui/data/SortableHeader";
import { TableSearchInput } from "@hadha/shared-ui/data/TableSearchInput";
import { FilterSelect } from "@hadha/shared-ui/data/FilterSelect";
import { ActiveFilterChips, type FilterChip } from "@hadha/shared-ui/data/ActiveFilterChips";
import { TablePagination } from "@hadha/shared-ui/data/TablePagination";
import type {
  CouponDto,
  CouponListResponse,
  CouponStatus,
  CouponType,
  CreateCouponDto,
} from "@/types/admin";
import {
  patchSearch,
  useClampPage,
  sortFromSearch,
  sortToSearch,
  urlDir,
  urlEnum,
  urlPage,
  urlText,
  useUrlSearchText,
} from "@/lib/tableUrlState";

const COUPON_SORT_KEYS = ["code", "value", "usage_count", "valid_until", "created_at"] as const;
const DEFAULT_SORT: SortState<CouponSortKey> = { sortBy: "created_at", sortDir: "desc" };
const FIRST_DIR = { code: "asc", valid_until: "asc" } as const;

const couponsSearchSchema = z.object({
  q: urlText,
  state: urlEnum(["live", "scheduled", "expired", "inactive"]),
  type: urlEnum(["percentage", "fixed_amount", "free_shipping"]),
  sort: urlEnum(COUPON_SORT_KEYS),
  dir: urlDir,
  page: urlPage,
});
type CouponsSearch = z.infer<typeof couponsSearchSchema>;

export const Route = createFileRoute("/admin/coupons")({
  validateSearch: couponsSearchSchema,
  component: AdminCoupons,
});

// ── helpers ───────────────────────────────────────────────────────────────────

function makeEmpty(): CreateCouponDto {
  return {
    code: "",
    coupon_type: "percentage",
    value: 10,
    description: "",
    status: "active",
    stackable: true,
    one_time_per_customer: false,
    first_order_only: false,
    new_customer_only: false,
    returning_customer_only: false,
  };
}

/** Split a newline / comma separated string into a trimmed array. */
function parseList(raw: string): string[] | null {
  const items = raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

function joinList(arr: string[] | null | undefined): string {
  return arr?.join("\n") ?? "";
}

// ── main component ────────────────────────────────────────────────────────────

type CouponSortKey = (typeof COUPON_SORT_KEYS)[number];

const STATE_OPTIONS = [
  { value: "live", label: "Live now" },
  { value: "scheduled", label: "Scheduled" },
  { value: "expired", label: "Expired" },
  { value: "inactive", label: "Inactive / draft" },
];
const TYPE_OPTIONS = [
  { value: "percentage", label: "Percentage" },
  { value: "fixed_amount", label: "Fixed amount" },
  { value: "free_shipping", label: "Free shipping" },
];

function AdminCoupons() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CreateCouponDto>(makeEmpty());
  const [editing, setEditing] = useState<CouponDto | null>(null);
  const [openSection, setOpenSection] = useState<string>("basic");
  // List view state lives in the URL; the create/edit form stays local.
  const urlSearch = Route.useSearch();
  const navigate = Route.useNavigate();
  const update = useCallback(
    (patch: Partial<CouponsSearch>, replace = false) =>
      navigate({ search: (prev) => patchSearch(prev, patch), replace }),
    [navigate],
  );

  const [search, setSearch] = useUrlSearchText(urlSearch.q, (q) => update({ q }));
  const debouncedSearch = urlSearch.q ?? "";
  const couponState = urlSearch.state ?? "";
  const couponType = urlSearch.type ?? "";
  const page = urlSearch.page ?? 1;
  const sort = sortFromSearch(urlSearch, DEFAULT_SORT);
  const onSort = (key: CouponSortKey) =>
    update(sortToSearch(nextSort(sort, key, FIRST_DIR), DEFAULT_SORT));
  const setCouponState = (v: string) =>
    update({ state: (v || undefined) as CouponsSearch["state"] });
  const setCouponType = (v: string) => update({ type: (v || undefined) as CouponsSearch["type"] });
  const setPage = (p: number) => update({ page: p > 1 ? p : undefined });

  const listParams = useMemo(
    () => ({
      page,
      page_size: 15,
      search: urlSearch.q,
      state: urlSearch.state,
      coupon_type: urlSearch.type,
      sort_by: sort.sortBy,
      sort_dir: sort.sortDir,
    }),
    [urlSearch, page, sort.sortBy, sort.sortDir],
  );

  const { data: couponsData, isPlaceholderData } = useQuery({
    queryKey: queryKeys.admin.coupons(listParams),
    queryFn: () => api.get<CouponListResponse>("/admin/coupons", { params: listParams }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const chips: FilterChip[] = [];
  if (debouncedSearch)
    chips.push({
      key: "q",
      label: `Search: "${debouncedSearch}"`,
      onRemove: () => update({ q: undefined }),
    });
  if (couponState)
    chips.push({
      key: "state",
      label: `State: ${STATE_OPTIONS.find((o) => o.value === couponState)?.label}`,
      onRemove: () => setCouponState(""),
    });
  if (couponType)
    chips.push({
      key: "type",
      label: `Type: ${TYPE_OPTIONS.find((o) => o.value === couponType)?.label}`,
      onRemove: () => setCouponType(""),
    });
  const clearFilters = () => update({ q: undefined, state: undefined, type: undefined });
  const header = (key: CouponSortKey, label: string) => (
    <SortableHeader label={label} sortKey={key} sort={sort} onSort={onSort} />
  );

  const createMutation = useMutation({
    mutationFn: (body: CreateCouponDto) => api.post<CouponDto>("/admin/coupons", { body }),
    onSuccess: (c) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "coupons"] });
      toast.success(`Saved ${c.code}`);
      setDraft(makeEmpty());
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/admin/coupons/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "coupons"] });
      toast.success("Coupon deleted.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const submit = () => {
    if (!draft.code.trim()) return toast.error("Coupon code is required");
    if ((draft.value ?? 0) <= 0) return toast.error("Value must be > 0");
    createMutation.mutate({ ...draft, code: draft.code.toUpperCase() });
  };

  const list = couponsData?.items ?? [];
  const totalPages = couponsData?.total_pages ?? 1;
  useClampPage(
    page,
    couponsData ? { itemCount: list.length, totalPages } : undefined,
    isPlaceholderData,
    (last) => update({ page: last > 1 ? last : undefined }, true),
  );
  const total = couponsData?.total ?? 0;
  const set = (patch: Partial<CreateCouponDto>) => setDraft((d) => ({ ...d, ...patch }));

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Promotions</p>
        <h1 className="font-display text-4xl mt-1">
          Coupons <span className="text-muted-foreground text-2xl">({total})</span>
        </h1>
      </header>

      <div className="grid lg:grid-cols-[1fr_420px] gap-6 items-start">
        {/* ── Coupon list ───────────────────────────────────────────────────── */}
        {/* Toolbar, table and pagination share one grid column so the form
            stays beside the list on every page. */}
        <div className="min-w-0">
          <div className="bg-background border border-border p-3 flex flex-wrap items-center gap-3 mb-3">
            <TableSearchInput
              value={search}
              onChange={setSearch}
              placeholder="Search code or description…"
              className="flex-1"
            />
            <FilterSelect
              label="State"
              allLabel="All states"
              value={couponState}
              onChange={setCouponState}
              options={STATE_OPTIONS}
              className="w-40"
            />
            <FilterSelect
              label="Type"
              allLabel="All types"
              value={couponType}
              onChange={setCouponType}
              options={TYPE_OPTIONS}
              className="w-40"
            />
          </div>
          <ActiveFilterChips chips={chips} onClearAll={clearFilters} className="mb-3" />
          <div
            className={`bg-background border border-border overflow-x-auto transition-opacity ${isPlaceholderData ? "opacity-60" : ""}`}
            aria-busy={isPlaceholderData}
          >
            <table className="w-full text-sm">
              <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <tr>
                  {header("code", "Code")}
                  {header("value", "Type / Value")}
                  <th className="px-4 py-3">Min order</th>
                  {header("usage_count", "Uses")}
                  <th className="px-4 py-3">Status</th>
                  {header("valid_until", "Expires")}
                  <th className="px-4 py-3">Campaign</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {list.map((c) => {
                  const isDeletingRow =
                    deleteMutation.isPending && deleteMutation.variables === c.id;
                  return (
                    <tr
                      key={c.id}
                      className="hover:bg-secondary/40 cursor-pointer"
                      onClick={() => setEditing(c)}
                    >
                      <td className="px-4 py-3 font-mono font-semibold">{c.code}</td>
                      <td className="px-4 py-3 font-display">
                        {c.coupon_type === "free_shipping"
                          ? "Free Shipping"
                          : c.coupon_type === "percentage"
                            ? `${c.value}%`
                            : `₹${c.value}`}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {c.min_order_amount ? `₹${c.min_order_amount}` : "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {c.usage_count}
                        {c.usage_limit ? `/${c.usage_limit}` : ""}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs whitespace-nowrap">
                        {c.valid_until
                          ? new Date(c.valid_until).toLocaleDateString("en-IN")
                          : "Never"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">
                        {c.campaign_name ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteMutation.mutate(c.id);
                          }}
                          disabled={isDeletingRow}
                          aria-busy={isDeletingRow}
                          className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                        >
                          {isDeletingRow ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Trash2 className="size-4" />
                          )}
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {list.length === 0 && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-10 text-center text-muted-foreground text-sm"
                    >
                      {chips.length ? (
                        <>
                          No coupons match these filters.{" "}
                          <button
                            type="button"
                            onClick={clearFilters}
                            className="underline underline-offset-4 text-foreground"
                          >
                            Clear filters
                          </button>
                        </>
                      ) : (
                        "No coupons yet. Create one →"
                      )}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <TablePagination
            page={page}
            totalPages={totalPages}
            total={total}
            noun="coupons"
            onPageChange={setPage}
          />
        </div>

        {/* ── Create / view form ────────────────────────────────────────────── */}
        <aside className="bg-background border border-border p-5 h-fit space-y-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-xl">
              {editing ? (
                <span className="flex items-center gap-2">
                  <Tag className="size-4" /> {editing.code}
                </span>
              ) : (
                "New coupon"
              )}
            </h2>
            {editing && (
              <button
                onClick={() => setEditing(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>

          {editing ? (
            <CouponDetail coupon={editing} onClose={() => setEditing(null)} />
          ) : (
            <CouponForm
              draft={draft}
              set={set}
              openSection={openSection}
              setOpenSection={setOpenSection}
              onSubmit={submit}
              isPending={createMutation.isPending}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: CouponStatus }) {
  const cls =
    status === "active"
      ? "bg-accent/15 text-accent"
      : status === "draft"
        ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
        : "bg-secondary text-muted-foreground";
  return (
    <span className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${cls}`}>{status}</span>
  );
}

// ── Read-only detail view ─────────────────────────────────────────────────────

function CouponDetail({ coupon: c, onClose }: { coupon: CouponDto; onClose: () => void }) {
  void onClose;
  const row = (label: string, value: React.ReactNode) => (
    <div className="flex justify-between gap-4 py-1.5 border-b border-border/40 last:border-0">
      <span className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground shrink-0">
        {label}
      </span>
      <span className="text-sm text-right">{value}</span>
    </div>
  );

  const yn = (v: boolean) => (v ? "Yes" : "No");
  const list = (arr: string[] | null) => (arr?.length ? arr.join(", ") : "—");

  return (
    <div className="space-y-1 text-sm">
      {row("Code", <span className="font-mono font-semibold">{c.code}</span>)}
      {row("Type", c.coupon_type.replace("_", " "))}
      {row(
        "Value",
        c.coupon_type === "percentage"
          ? `${c.value}%`
          : c.coupon_type === "fixed_amount"
            ? `₹${c.value}`
            : "Free shipping",
      )}
      {row("Status", <StatusBadge status={c.status} />)}
      {row("Valid from", c.valid_from ? c.valid_from.slice(0, 10) : "Now")}
      {row("Valid until", c.valid_until ? c.valid_until.slice(0, 10) : "No expiry")}
      {row("Min order", c.min_order_amount ? `₹${c.min_order_amount}` : "—")}
      {row("Max order", c.max_order_amount ? `₹${c.max_order_amount}` : "—")}
      {row("Max discount", c.max_discount ? `₹${c.max_discount}` : "—")}
      {row("Usage limit", c.usage_limit ?? "Unlimited")}
      {row("Usage count", c.usage_count)}
      {row("Per user limit", c.per_user_limit)}
      {row("One-time per customer", yn(c.one_time_per_customer))}
      {row("First order only", yn(c.first_order_only))}
      {row("New customer only", yn(c.new_customer_only))}
      {row("Returning customer only", yn(c.returning_customer_only))}
      {row("Stackable", yn(c.stackable))}
      {row("Campaign", c.campaign_name ?? "—")}
      {row("Allowed states", list(c.allowed_states))}
      {row("Allowed cities", list(c.allowed_cities))}
      {row("Allowed PIN codes", list(c.allowed_pincodes))}
      {row("Payment methods", list(c.allowed_payment_methods))}
      {row("Shipping methods", list(c.allowed_shipping_methods))}
      {row("Eligible product IDs", list(c.eligible_product_ids))}
      {row("Eligible categories", list(c.eligible_category_slugs))}
      {row("Excluded products", list(c.excluded_product_ids))}
      {row("Excluded categories", list(c.excluded_category_slugs))}
      {row("Allowed emails", list(c.allowed_emails))}
      {row("Allowed phone numbers", list(c.allowed_phone_numbers))}
      {row("Customer groups", list(c.customer_groups))}
    </div>
  );
}

// ── Section accordion ─────────────────────────────────────────────────────────

function Section({
  id,
  label,
  open,
  onToggle,
  children,
}: {
  id: string;
  label: string;
  open: boolean;
  onToggle: (id: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-border">
      <button
        type="button"
        onClick={() => onToggle(id)}
        className="w-full flex items-center justify-between py-3 text-left"
      >
        <span className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
          {label}
        </span>
        {open ? (
          <ChevronDown className="size-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3.5 text-muted-foreground" />
        )}
      </button>
      {open && <div className="pb-4 grid gap-3">{children}</div>}
    </div>
  );
}

// ── Shared field wrapper ──────────────────────────────────────────────────────

function F({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1">
      <span className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

const inputCls =
  "border border-border bg-background px-3 py-2 text-sm w-full focus:outline-none focus:border-foreground transition";
const checkCls = "flex items-center gap-2 text-sm cursor-pointer select-none";

// ── Textarea helper for list fields ──────────────────────────────────────────

function ListField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string[] | null | undefined;
  onChange: (v: string[] | null) => void;
  placeholder?: string;
}) {
  return (
    <F label={label}>
      <textarea
        rows={3}
        placeholder={placeholder ?? "One per line"}
        value={joinList(value)}
        onChange={(e) => onChange(parseList(e.target.value))}
        className={`${inputCls} resize-none font-mono text-xs`}
      />
    </F>
  );
}

// ── The actual create form ────────────────────────────────────────────────────

function CouponForm({
  draft: d,
  set,
  openSection,
  setOpenSection,
  onSubmit,
  isPending,
}: {
  draft: CreateCouponDto;
  set: (patch: Partial<CreateCouponDto>) => void;
  openSection: string;
  setOpenSection: (s: string) => void;
  onSubmit: () => void;
  isPending: boolean;
}) {
  const toggle = (id: string) => setOpenSection(openSection === id ? "" : id);

  return (
    <div className="space-y-0">
      {/* Basic */}
      <Section id="basic" label="Basic info" open={openSection === "basic"} onToggle={toggle}>
        <F label="Code *">
          <input
            value={d.code}
            onChange={(e) => set({ code: e.target.value.toUpperCase() })}
            className={`${inputCls} font-mono uppercase`}
            placeholder="SAVE20"
          />
        </F>
        <F label="Type *">
          <select
            value={d.coupon_type}
            onChange={(e) => set({ coupon_type: e.target.value as CouponType })}
            className={inputCls}
          >
            <option value="percentage">Percentage %</option>
            <option value="fixed_amount">Fixed Amount ₹</option>
            <option value="free_shipping">Free Shipping</option>
          </select>
        </F>
        {d.coupon_type !== "free_shipping" && (
          <F label="Value *">
            <input
              type="number"
              min={1}
              max={d.coupon_type === "percentage" ? 100 : undefined}
              value={d.value}
              onChange={(e) => set({ value: Number(e.target.value) })}
              className={inputCls}
            />
          </F>
        )}
        <F label="Description">
          <input
            value={d.description ?? ""}
            onChange={(e) => set({ description: e.target.value || null })}
            className={inputCls}
            placeholder="Shown to customers"
          />
        </F>
        <F label="Campaign name">
          <input
            value={d.campaign_name ?? ""}
            onChange={(e) => set({ campaign_name: e.target.value || null })}
            className={inputCls}
            placeholder="Diwali 2026"
          />
        </F>
        <F label="Status">
          <select
            value={d.status ?? "active"}
            onChange={(e) => set({ status: e.target.value as CouponStatus })}
            className={inputCls}
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="draft">Draft</option>
          </select>
        </F>
        <label className={checkCls}>
          <input
            type="checkbox"
            checked={d.stackable ?? true}
            onChange={(e) => set({ stackable: e.target.checked })}
          />
          Can stack with other coupons
        </label>
      </Section>

      {/* Validity */}
      <Section
        id="validity"
        label="Validity period"
        open={openSection === "validity"}
        onToggle={toggle}
      >
        <F label="Valid from">
          <input
            type="datetime-local"
            value={d.valid_from?.slice(0, 16) ?? ""}
            onChange={(e) => set({ valid_from: e.target.value || null })}
            className={inputCls}
          />
        </F>
        <F label="Valid until">
          <input
            type="datetime-local"
            value={d.valid_until?.slice(0, 16) ?? ""}
            onChange={(e) => set({ valid_until: e.target.value || null })}
            className={inputCls}
          />
        </F>
      </Section>

      {/* Discount rules */}
      <Section
        id="discount"
        label="Discount rules"
        open={openSection === "discount"}
        onToggle={toggle}
      >
        <F label="Min order amount (₹)">
          <input
            type="number"
            min={0}
            value={d.min_order_amount ?? ""}
            onChange={(e) =>
              set({ min_order_amount: e.target.value ? Number(e.target.value) : undefined })
            }
            className={inputCls}
            placeholder="e.g. 999"
          />
        </F>
        <F label="Max order amount (₹)">
          <input
            type="number"
            min={0}
            value={d.max_order_amount ?? ""}
            onChange={(e) =>
              set({ max_order_amount: e.target.value ? Number(e.target.value) : null })
            }
            className={inputCls}
            placeholder="e.g. 50000"
          />
        </F>
        {d.coupon_type === "percentage" && (
          <F label="Max discount cap (₹)">
            <input
              type="number"
              min={0}
              value={d.max_discount ?? ""}
              onChange={(e) =>
                set({ max_discount: e.target.value ? Number(e.target.value) : null })
              }
              className={inputCls}
              placeholder="e.g. 500"
            />
          </F>
        )}
      </Section>

      {/* Usage limits */}
      <Section id="limits" label="Usage limits" open={openSection === "limits"} onToggle={toggle}>
        <F label="Total usage limit">
          <input
            type="number"
            min={1}
            value={d.usage_limit ?? ""}
            onChange={(e) => set({ usage_limit: e.target.value ? Number(e.target.value) : null })}
            className={inputCls}
            placeholder="Unlimited"
          />
        </F>
        <F label="Per customer limit">
          <input
            type="number"
            min={1}
            value={d.per_user_limit ?? ""}
            onChange={(e) =>
              set({ per_user_limit: e.target.value ? Number(e.target.value) : undefined })
            }
            className={inputCls}
            placeholder="1"
          />
        </F>
        <label className={checkCls}>
          <input
            type="checkbox"
            checked={d.one_time_per_customer ?? false}
            onChange={(e) => set({ one_time_per_customer: e.target.checked })}
          />
          One-time use per customer
        </label>
      </Section>

      {/* Customer eligibility */}
      <Section
        id="eligibility"
        label="Customer eligibility"
        open={openSection === "eligibility"}
        onToggle={toggle}
      >
        <label className={checkCls}>
          <input
            type="checkbox"
            checked={d.first_order_only ?? false}
            onChange={(e) => set({ first_order_only: e.target.checked })}
          />
          First order only
        </label>
        <label className={checkCls}>
          <input
            type="checkbox"
            checked={d.new_customer_only ?? false}
            onChange={(e) => set({ new_customer_only: e.target.checked })}
          />
          New customers only (0 completed orders)
        </label>
        <label className={checkCls}>
          <input
            type="checkbox"
            checked={d.returning_customer_only ?? false}
            onChange={(e) => set({ returning_customer_only: e.target.checked })}
          />
          Returning customers only (≥1 completed order)
        </label>
        <ListField
          label="Allowed email addresses"
          value={d.allowed_emails}
          onChange={(v) => set({ allowed_emails: v })}
          placeholder="customer@example.com"
        />
        <ListField
          label="Allowed phone numbers"
          value={d.allowed_phone_numbers}
          onChange={(v) => set({ allowed_phone_numbers: v })}
          placeholder="+91XXXXXXXXXX"
        />
        <ListField
          label="Customer groups"
          value={d.customer_groups}
          onChange={(v) => set({ customer_groups: v })}
          placeholder="vip, wholesale, premium"
        />
      </Section>

      {/* Product / category */}
      <Section
        id="products"
        label="Product restrictions"
        open={openSection === "products"}
        onToggle={toggle}
      >
        <ListField
          label="Eligible product IDs"
          value={d.eligible_product_ids}
          onChange={(v) => set({ eligible_product_ids: v })}
          placeholder="UUID per line"
        />
        <ListField
          label="Eligible collection IDs"
          value={d.eligible_collection_ids}
          onChange={(v) => set({ eligible_collection_ids: v })}
          placeholder="UUID per line"
        />
        <ListField
          label="Eligible category slugs"
          value={d.eligible_category_slugs}
          onChange={(v) => set({ eligible_category_slugs: v })}
          placeholder="sweets, pickles, dry-fruits"
        />
        <ListField
          label="Excluded product IDs"
          value={d.excluded_product_ids}
          onChange={(v) => set({ excluded_product_ids: v })}
          placeholder="UUID per line"
        />
        <ListField
          label="Excluded category slugs"
          value={d.excluded_category_slugs}
          onChange={(v) => set({ excluded_category_slugs: v })}
          placeholder="gift-sets, bundles"
        />
      </Section>

      {/* Region */}
      <Section
        id="region"
        label="Region restrictions"
        open={openSection === "region"}
        onToggle={toggle}
      >
        <ListField
          label="Allowed states"
          value={d.allowed_states}
          onChange={(v) => set({ allowed_states: v })}
          placeholder="Telangana, Andhra Pradesh"
        />
        <ListField
          label="Allowed cities"
          value={d.allowed_cities}
          onChange={(v) => set({ allowed_cities: v })}
          placeholder="Hyderabad, Vijayawada"
        />
        <ListField
          label="Allowed PIN codes"
          value={d.allowed_pincodes}
          onChange={(v) => set({ allowed_pincodes: v })}
          placeholder="500001, 500002"
        />
      </Section>

      {/* Methods */}
      <Section
        id="methods"
        label="Payment & shipping"
        open={openSection === "methods"}
        onToggle={toggle}
      >
        <F label="Allowed payment methods">
          <div className="grid gap-1.5">
            {["upi", "credit_card", "debit_card", "net_banking", "wallet", "cod"].map((m) => (
              <label key={m} className={checkCls}>
                <input
                  type="checkbox"
                  checked={(d.allowed_payment_methods ?? []).includes(m)}
                  onChange={(e) => {
                    const curr = d.allowed_payment_methods ?? [];
                    set({
                      allowed_payment_methods: e.target.checked
                        ? [...curr, m]
                        : curr.filter((x) => x !== m) || null,
                    });
                  }}
                />
                {m.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
              </label>
            ))}
          </div>
        </F>
        <F label="Allowed shipping methods">
          <div className="grid gap-1.5">
            {["standard", "express"].map((m) => (
              <label key={m} className={checkCls}>
                <input
                  type="checkbox"
                  checked={(d.allowed_shipping_methods ?? []).includes(m)}
                  onChange={(e) => {
                    const curr = d.allowed_shipping_methods ?? [];
                    set({
                      allowed_shipping_methods: e.target.checked
                        ? [...curr, m]
                        : curr.filter((x) => x !== m) || null,
                    });
                  }}
                />
                {m.charAt(0).toUpperCase() + m.slice(1)} Delivery
              </label>
            ))}
          </div>
        </F>
      </Section>

      <div className="pt-4">
        <button
          onClick={onSubmit}
          disabled={isPending}
          aria-busy={isPending}
          className="w-full inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-5 py-3 disabled:opacity-60 hover:bg-primary/90 transition"
        >
          {isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Plus className="size-3.5" />
          )}
          {isPending ? "Saving…" : "Save coupon"}
        </button>
      </div>
    </div>
  );
}
