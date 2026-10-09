import { useCallback, useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { formatINR } from "@/lib/format";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import { SortableHeader, nextSort, type SortState } from "@hadha/shared-ui/data/SortableHeader";
import { TableSearchInput } from "@hadha/shared-ui/data/TableSearchInput";
import { FilterSelect } from "@hadha/shared-ui/data/FilterSelect";
import {
  DateRangeFilter,
  describeDateRange,
  resolveDateRange,
} from "@hadha/shared-ui/data/DateRangeFilter";
import { ActiveFilterChips, type FilterChip } from "@hadha/shared-ui/data/ActiveFilterChips";
import { TablePagination } from "@hadha/shared-ui/data/TablePagination";
import {
  dateRangeFields,
  dateRangeFromSearch,
  dateRangeToSearch,
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
import type { AdminUserListResponse } from "@/types/admin";

const SORT_KEYS = [
  "email",
  "full_name",
  "role",
  "order_count",
  "total_spent",
  "created_at",
] as const;
type SortKey = (typeof SORT_KEYS)[number];
const DEFAULT_SORT: SortState<SortKey> = { sortBy: "created_at", sortDir: "desc" };
const FIRST_DIR = { email: "asc", full_name: "asc", role: "asc" } as const;

const customersSearchSchema = z.object({
  q: urlText,
  role: urlEnum(["customer", "admin", "super_admin"]),
  status: urlEnum(["active", "suspended"]),
  ...dateRangeFields,
  sort: urlEnum(SORT_KEYS),
  dir: urlDir,
  page: urlPage,
});
type CustomersSearch = z.infer<typeof customersSearchSchema>;

export const Route = createFileRoute("/admin/customers")({
  validateSearch: customersSearchSchema,
  component: AdminCustomers,
});

const ROLE_OPTIONS = [
  { value: "customer", label: "Customer" },
  { value: "admin", label: "Admin" },
  { value: "super_admin", label: "Super admin" },
];
const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
] as const;

function AdminCustomers() {
  // All view state lives in the URL (refresh / back / shared links keep it).
  const urlSearch = Route.useSearch();
  const navigate = Route.useNavigate();
  const update = useCallback(
    (patch: Partial<CustomersSearch>, replace = false) =>
      navigate({ search: (prev) => patchSearch(prev, patch), replace }),
    [navigate],
  );

  const [search, setSearch] = useUrlSearchText(urlSearch.q, (q) => update({ q }));
  const debouncedSearch = urlSearch.q ?? "";
  const role = urlSearch.role ?? "";
  const status = urlSearch.status ?? "";
  const joined = dateRangeFromSearch(urlSearch);
  const page = urlSearch.page ?? 1;
  const sort = sortFromSearch(urlSearch, DEFAULT_SORT);
  const onSort = (key: SortKey) =>
    update(sortToSearch(nextSort(sort, key, FIRST_DIR), DEFAULT_SORT));
  const setRole = (v: string) => update({ role: (v || undefined) as CustomersSearch["role"] });
  const setStatus = (v: string) =>
    update({ status: (v || undefined) as CustomersSearch["status"] });
  const setJoined = (v: Parameters<typeof dateRangeToSearch>[0]) => update(dateRangeToSearch(v));
  const setPage = (p: number) => update({ page: p > 1 ? p : undefined });

  const params = useMemo(
    () => ({
      page,
      page_size: 15,
      search: urlSearch.q,
      role: urlSearch.role,
      is_active: urlSearch.status ? urlSearch.status === "active" : undefined,
      sort_by: sort.sortBy,
      sort_dir: sort.sortDir,
      ...resolveDateRange(dateRangeFromSearch(urlSearch)),
    }),
    [urlSearch, page, sort.sortBy, sort.sortDir],
  );

  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: queryKeys.admin.customers(params),
    queryFn: () => api.get<AdminUserListResponse>("/admin/users", { params }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const customers = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  useClampPage(
    page,
    data ? { itemCount: customers.length, totalPages } : undefined,
    isPlaceholderData,
    (last) => update({ page: last > 1 ? last : undefined }, true),
  );
  const total = data?.total ?? 0;

  const chips: FilterChip[] = [];
  if (debouncedSearch)
    chips.push({
      key: "q",
      label: `Search: "${debouncedSearch}"`,
      onRemove: () => update({ q: undefined }),
    });
  if (role)
    chips.push({
      key: "role",
      label: `Role: ${ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role}`,
      onRemove: () => setRole(""),
    });
  if (status)
    chips.push({
      key: "status",
      label: `Status: ${status === "active" ? "Active" : "Suspended"}`,
      onRemove: () => setStatus(""),
    });
  const joinedLabel = describeDateRange(joined);
  if (joinedLabel)
    chips.push({
      key: "joined",
      label: `Joined: ${joinedLabel}`,
      onRemove: () => setJoined({ preset: "any" }),
    });
  // Keeps the sort; clears every filter.
  const clearAll = () =>
    update({
      q: undefined,
      role: undefined,
      status: undefined,
      date: undefined,
      from: undefined,
      to: undefined,
    });

  const header = (key: SortKey, label: string, className?: string) => (
    <SortableHeader label={label} sortKey={key} sort={sort} onSort={onSort} className={className} />
  );

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Audience</p>
        <h1 className="font-display text-4xl mt-1">
          Customers <span className="text-muted-foreground text-2xl">({data?.total ?? 0})</span>
        </h1>
      </header>

      <div className="bg-background border border-border p-4 flex flex-wrap items-center gap-3 mb-3">
        <TableSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search by email, name or phone…"
          className="flex-1"
        />
        <FilterSelect
          label="Role"
          allLabel="All roles"
          value={role}
          onChange={setRole}
          options={ROLE_OPTIONS}
          className="w-40"
        />
        <FilterSelect
          label="Status"
          allLabel="All statuses"
          value={status}
          onChange={setStatus}
          options={[...STATUS_OPTIONS]}
          className="w-40"
        />
        <DateRangeFilter label="Joined" value={joined} onChange={setJoined} />
      </div>

      <ActiveFilterChips chips={chips} onClearAll={clearAll} className="mb-4" />

      <div
        className={`bg-background border border-border overflow-x-auto transition-opacity ${isPlaceholderData ? "opacity-60" : ""}`}
        aria-busy={isPlaceholderData}
      >
        {isLoading ? (
          <TableSkeleton
            headers={["Email", "Name", "Role", "Orders", "Total spent", "2FA", "Status", "Joined"]}
            rows={8}
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                {header("email", "Email")}
                {header("full_name", "Name")}
                {header("role", "Role")}
                {header("order_count", "Orders", "text-right")}
                {header("total_spent", "Total spent", "text-right")}
                <th className="px-4 py-3" scope="col">
                  2FA
                </th>
                <th className="px-4 py-3" scope="col">
                  Status
                </th>
                {header("created_at", "Joined")}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {customers.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3">{c.email}</td>
                  <td className="px-4 py-3">{c.full_name ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                        c.role === "super_admin"
                          ? "bg-destructive/15 text-destructive"
                          : c.role === "admin"
                            ? "bg-accent/15 text-accent"
                            : "bg-secondary text-muted-foreground"
                      }`}
                    >
                      {c.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{c.order_count ?? 0}</td>
                  <td className="px-4 py-3 text-right font-display tabular-nums">
                    {c.total_spent ? formatINR(c.total_spent) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {c.role === "admin" || c.role === "super_admin" ? (
                      <span
                        className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                          c.two_factor_enabled
                            ? "bg-accent/15 text-accent"
                            : "bg-secondary text-muted-foreground"
                        }`}
                      >
                        {c.two_factor_enabled ? "Enabled" : "Disabled"}
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] uppercase tracking-[0.22em] px-2 py-0.5 ${
                        c.is_active
                          ? "bg-accent/15 text-accent"
                          : "bg-destructive/15 text-destructive"
                      }`}
                    >
                      {c.is_active ? "Active" : "Suspended"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(c.created_at).toLocaleDateString("en-IN")}
                  </td>
                </tr>
              ))}
              {customers.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-muted-foreground text-sm">
                    {chips.length ? (
                      <>
                        No customers match these filters.{" "}
                        <button
                          type="button"
                          onClick={clearAll}
                          className="underline underline-offset-4 text-foreground"
                        >
                          Clear filters
                        </button>
                      </>
                    ) : (
                      "No customers found."
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
        noun="customers"
        onPageChange={setPage}
      />
    </div>
  );
}
