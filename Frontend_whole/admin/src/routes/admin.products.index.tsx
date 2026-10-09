import { useCallback, useMemo } from "react";
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { z } from "zod";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Plus, Trash2, Pencil, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { SortableHeader, nextSort, type SortState } from "@hadha/shared-ui/data/SortableHeader";
import {
  patchSearch,
  useClampPage,
  sortFromSearch,
  sortToSearch,
  urlDir,
  urlEnum,
  urlId,
  urlPage,
  urlText,
  useUrlSearchText,
} from "@/lib/tableUrlState";
import { TableSearchInput } from "@hadha/shared-ui/data/TableSearchInput";
import { FilterSelect } from "@hadha/shared-ui/data/FilterSelect";
import { ActiveFilterChips, type FilterChip } from "@hadha/shared-ui/data/ActiveFilterChips";
import { TablePagination } from "@hadha/shared-ui/data/TablePagination";
import type {
  CategoryAdminListResponse,
  CollectionListResponse,
  ProductListResponse,
} from "@/types/admin";

const SORT_KEYS = [
  "name",
  "base_price",
  "stock_quantity",
  "status",
  "created_at",
  "updated_at",
] as const;
type SortKey = (typeof SORT_KEYS)[number];
const DEFAULT_SORT: SortState<SortKey> = { sortBy: "created_at", sortDir: "desc" };
const FIRST_DIR = { name: "asc", status: "asc", base_price: "asc", stock_quantity: "asc" } as const;

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "draft", label: "Draft" },
  { value: "archived", label: "Archived" },
];
const STOCK_OPTIONS = [
  { value: "in_stock", label: "In stock" },
  { value: "low_stock", label: "Low stock" },
  { value: "out_of_stock", label: "Out of stock" },
];
const GENDER_OPTIONS = [
  { value: "women", label: "Women" },
  { value: "men", label: "Men" },
  { value: "unisex", label: "Unisex" },
  { value: "kids", label: "Kids" },
];
const FLAG_OPTIONS = [
  { value: "is_featured", label: "Featured" },
  { value: "is_new_arrival", label: "New arrival" },
  { value: "is_best_seller", label: "Best seller" },
  { value: "on_sale", label: "On sale" },
] as const;
type Flag = (typeof FLAG_OPTIONS)[number]["value"];

const productsSearchSchema = z.object({
  q: urlText,
  status: urlEnum(["active", "draft", "archived"]),
  stock: urlEnum(["in_stock", "low_stock", "out_of_stock"]),
  category: urlId,
  collection: urlId,
  gender: urlEnum(["women", "men", "unisex", "kids"]),
  flag: urlEnum(["is_featured", "is_new_arrival", "is_best_seller", "on_sale"]),
  sort: urlEnum(SORT_KEYS),
  dir: urlDir,
  page: urlPage,
});
type ProductsSearch = z.infer<typeof productsSearchSchema>;

export const Route = createFileRoute("/admin/products/")({
  validateSearch: productsSearchSchema,
  component: AdminProducts,
});

function AdminProducts() {
  // All view state lives in the URL (refresh / back / shared links keep it).
  const urlSearch = Route.useSearch();
  const navigateSearch = Route.useNavigate();
  const update = useCallback(
    (patch: Partial<ProductsSearch>, replace = false) =>
      navigateSearch({ search: (prev) => patchSearch(prev, patch), replace }),
    [navigateSearch],
  );

  const [q, setQ] = useUrlSearchText(urlSearch.q, (value) => update({ q: value }));
  const debouncedQ = urlSearch.q ?? "";
  const collectionId = urlSearch.collection ?? "";
  const categoryId = urlSearch.category ?? "";
  const status = urlSearch.status ?? "";
  const stock = urlSearch.stock ?? "";
  const gender = urlSearch.gender ?? "";
  const flag: Flag | "" = urlSearch.flag ?? "";
  const page = urlSearch.page ?? 1;
  const sort = sortFromSearch(urlSearch, DEFAULT_SORT);
  const onSort = (key: SortKey) =>
    update(sortToSearch(nextSort(sort, key, FIRST_DIR), DEFAULT_SORT));

  const setCollectionId = (v: string) => update({ collection: v || undefined });
  const setCategoryId = (v: string) => update({ category: v || undefined });
  const setStatus = (v: string) => update({ status: (v || undefined) as ProductsSearch["status"] });
  const setStock = (v: string) => update({ stock: (v || undefined) as ProductsSearch["stock"] });
  const setGender = (v: string) => update({ gender: (v || undefined) as ProductsSearch["gender"] });
  const setFlag = (v: Flag | "") => update({ flag: v || undefined });
  const setPage = (p: number) => update({ page: p > 1 ? p : undefined });

  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const params = useMemo(
    () => ({
      search: urlSearch.q,
      collection_id: urlSearch.collection,
      category_id: urlSearch.category,
      status: urlSearch.status,
      stock_status: urlSearch.stock,
      gender: urlSearch.gender,
      ...(urlSearch.flag ? { [urlSearch.flag]: true } : {}),
      sort_by: sort.sortBy,
      sort_dir: sort.sortDir,
      page,
      page_size: 15,
    }),
    [urlSearch, sort.sortBy, sort.sortDir, page],
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

  const { data: categoriesData } = useQuery({
    queryKey: queryKeys.admin.categoriesList({ page: 1, page_size: 200 }),
    queryFn: () =>
      api.get<CategoryAdminListResponse>("/admin/categories", {
        params: { page: 1, page_size: 200 },
      }),
    staleTime: 300_000,
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
  const categories = categoriesData?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  useClampPage(
    page,
    data ? { itemCount: list.length, totalPages } : undefined,
    isPlaceholderData,
    (last) => update({ page: last > 1 ? last : undefined }, true),
  );
  const total = data?.total ?? 0;

  const label = (opts: { value: string; label: string }[], v: string) =>
    opts.find((o) => o.value === v)?.label ?? v;
  const chips: FilterChip[] = [];
  if (debouncedQ)
    chips.push({
      key: "q",
      label: `Search: "${debouncedQ}"`,
      onRemove: () => update({ q: undefined }),
    });
  if (status)
    chips.push({
      key: "status",
      label: `Status: ${label(STATUS_OPTIONS, status)}`,
      onRemove: () => setStatus(""),
    });
  if (stock)
    chips.push({
      key: "stock",
      label: `Stock: ${label(STOCK_OPTIONS, stock)}`,
      onRemove: () => setStock(""),
    });
  if (categoryId)
    chips.push({
      key: "category",
      label: `Category: ${categories.find((c) => c.id === categoryId)?.name ?? "…"}`,
      onRemove: () => setCategoryId(""),
    });
  if (collectionId)
    chips.push({
      key: "collection",
      label: `Collection: ${collections.find((c) => c.id === collectionId)?.name ?? "…"}`,
      onRemove: () => setCollectionId(""),
    });
  if (gender)
    chips.push({
      key: "gender",
      label: `Gender: ${label(GENDER_OPTIONS, gender)}`,
      onRemove: () => setGender(""),
    });
  if (flag)
    chips.push({ key: "flag", label: label([...FLAG_OPTIONS], flag), onRemove: () => setFlag("") });
  // One navigation for every filter; keeps the sort.
  const clearAll = () =>
    update({
      q: undefined,
      status: undefined,
      stock: undefined,
      category: undefined,
      collection: undefined,
      gender: undefined,
      flag: undefined,
    });

  const header = (key: SortKey, text: string) => (
    <SortableHeader label={text} sortKey={key} sort={sort} onSort={onSort} />
  );

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

      <div className="bg-background border border-border p-4 flex flex-wrap items-center gap-3 mb-3">
        <TableSearchInput
          value={q}
          onChange={setQ}
          placeholder="Search by name or SKU…"
          className="flex-1"
        />
        <FilterSelect
          label="Status"
          allLabel="All statuses"
          value={status}
          onChange={setStatus}
          options={STATUS_OPTIONS}
          className="w-36"
        />
        <FilterSelect
          label="Stock"
          allLabel="All stock levels"
          value={stock}
          onChange={setStock}
          options={STOCK_OPTIONS}
          className="w-40"
        />
        {categories.length > 0 && (
          <FilterSelect
            label="Category"
            allLabel="All categories"
            value={categoryId}
            onChange={setCategoryId}
            options={categories.map((c) => ({
              value: c.id,
              label: c.parent_id ? `— ${c.name}` : c.name,
            }))}
            className="w-44"
          />
        )}
        {collections.length > 0 && (
          <FilterSelect
            label="Collection"
            allLabel="All collections"
            value={collectionId}
            onChange={setCollectionId}
            options={collections.map((c) => ({ value: c.id, label: c.name }))}
            className="w-44"
          />
        )}
        <FilterSelect
          label="Gender"
          allLabel="All genders"
          value={gender}
          onChange={setGender}
          options={GENDER_OPTIONS}
          className="w-36"
        />
        <FilterSelect
          label="Highlight"
          allLabel="Any highlight"
          value={flag}
          onChange={setFlag}
          options={[...FLAG_OPTIONS]}
          className="w-40"
        />
      </div>

      <ActiveFilterChips chips={chips} onClearAll={clearAll} className="mb-4" />

      <div
        className={`bg-background border border-border overflow-x-auto transition-opacity ${isPlaceholderData ? "opacity-60" : ""}`}
      >
        {isLoading ? (
          <TableSkeleton
            headers={[
              "Product",
              "SKU",
              "Collections",
              "Price",
              "Stock",
              "Status",
              "Added",
              "Actions",
            ]}
            rows={8}
            firstColWide
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                {header("name", "Product")}
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Collections</th>
                {header("base_price", "Price")}
                {header("stock_quantity", "Stock")}
                {header("status", "Status")}
                {header("created_at", "Added")}
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.map((p) => {
                const isDeleting = deleteMutation.isPending && deleteMutation.variables === p.id;
                return (
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
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                      {new Date(p.created_at).toLocaleDateString("en-IN")}
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
                          disabled={isDeleting}
                          aria-busy={isDeleting}
                          className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                        >
                          {isDeleting ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Trash2 className="size-4" />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {list.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-muted-foreground text-sm">
                    No products match your filters.{" "}
                    {chips.length > 0 && (
                      <button
                        type="button"
                        onClick={clearAll}
                        className="underline underline-offset-4 text-foreground"
                      >
                        Clear filters
                      </button>
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
        noun="products"
        onPageChange={setPage}
      />
    </div>
  );
}
