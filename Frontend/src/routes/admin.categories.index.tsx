import { useState, useMemo } from "react";
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Search,
  Pencil,
  Trash2,
  Eye,
  MoreHorizontal,
  ImageIcon,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronRight as ChevronRightIcon,
} from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { TableSkeleton } from "@/components/loading/TableSkeleton";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import type { CategoryAdminListItem, CategoryAdminListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/categories/")({
  component: AdminCategories,
});

function useDebounce<T>(value: T, delay: number): T {
  const [d, setD] = useState(value);
  useMemo(() => {
    const t = setTimeout(() => setD(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return d;
}

function AdminCategories() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [isActive, setIsActive] = useState<boolean | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const debouncedSearch = useDebounce(search, 300);

  const params = useMemo(
    () => ({
      page,
      page_size: 50,
      search: debouncedSearch || undefined,
      is_active: isActive,
    }),
    [page, debouncedSearch, isActive],
  );

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.categoriesList(params),
    queryFn: () => api.get<CategoryAdminListResponse>("/admin/categories", { params }),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/admin/categories/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories });
      toast.success("Category deleted.");
      setDeleteId(null);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const bulkMutation = useMutation({
    mutationFn: (body: { ids: string[]; action: string }) =>
      api.post<void>("/admin/categories/bulk", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories });
      setSelected(new Set());
      toast.success("Bulk action applied.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.patch<void>(`/admin/categories/${id}`, { body: { is_active } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories }),
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;

  // Build tree for display when not searching
  const isSearching = !!debouncedSearch;
  const topLevel = isSearching ? items : items.filter((c) => !c.parent_id);
  const childrenOf = (parentId: string) => items.filter((c) => c.parent_id === parentId);

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function renderRow(cat: CategoryAdminListItem, depth = 0) {
    const children = childrenOf(cat.id);
    const hasChildren = children.length > 0 || cat.children_count > 0;
    const isExpanded = expandedIds.has(cat.id);

    return (
      <>
        <tr
          key={cat.id}
          className={`hover:bg-secondary/40 transition-colors ${
            selected.has(cat.id) ? "bg-accent/5" : ""
          }`}
        >
          <td className="px-4 py-3">
            <input
              type="checkbox"
              checked={selected.has(cat.id)}
              onChange={() => toggleSelect(cat.id)}
              className="cursor-pointer"
            />
          </td>
          <td className="px-4 py-3">
            {cat.image_url ? (
              <img src={cat.image_url} alt="" className="size-8 object-cover bg-secondary" />
            ) : (
              <div className="size-8 bg-secondary flex items-center justify-center">
                <ImageIcon className="size-3 text-muted-foreground" />
              </div>
            )}
          </td>
          <td className="px-4 py-3">
            <div className="flex items-center gap-2" style={{ paddingLeft: `${depth * 20}px` }}>
              {hasChildren && !isSearching ? (
                <button
                  onClick={() => toggleExpand(cat.id)}
                  className="text-muted-foreground hover:text-foreground transition shrink-0"
                >
                  {isExpanded ? (
                    <ChevronDown className="size-4" />
                  ) : (
                    <ChevronRightIcon className="size-4" />
                  )}
                </button>
              ) : (
                <span className="w-4 shrink-0" />
              )}
              <div>
                <Link
                  to="/admin/categories/$categoryId"
                  params={{ categoryId: cat.id }}
                  className="hover:underline font-medium text-sm"
                >
                  {cat.name}
                </Link>
                <p className="text-xs text-muted-foreground font-mono">{cat.slug}</p>
              </div>
            </div>
          </td>
          <td className="px-4 py-3 text-xs text-muted-foreground">
            {cat.parent_id ? (items.find((c) => c.id === cat.parent_id)?.name ?? "—") : "—"}
          </td>
          <td className="px-4 py-3 text-muted-foreground text-sm">{cat.product_count}</td>
          <td className="px-4 py-3 text-muted-foreground text-sm">{cat.sort_order}</td>
          <td className="px-4 py-3">
            <button
              onClick={() => toggleActiveMutation.mutate({ id: cat.id, is_active: !cat.is_active })}
              className={`text-[10px] uppercase tracking-[0.2em] px-2 py-0.5 transition ${
                cat.is_active
                  ? "bg-accent/15 text-accent hover:bg-destructive/15 hover:text-destructive"
                  : "bg-secondary text-muted-foreground hover:bg-accent/15 hover:text-accent"
              }`}
            >
              {cat.is_active ? "Active" : "Inactive"}
            </button>
          </td>
          <td className="px-4 py-3 text-muted-foreground text-xs">
            {new Date(cat.updated_at).toLocaleDateString()}
          </td>
          <td className="px-4 py-3 text-right">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="text-muted-foreground hover:text-foreground transition p-1">
                  <MoreHorizontal className="size-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem asChild>
                  <Link
                    to="/admin/categories/$categoryId"
                    params={{ categoryId: cat.id }}
                    className="flex items-center gap-2"
                  >
                    <Eye className="size-3.5" />
                    View
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link
                    to="/admin/categories/$categoryId/edit"
                    params={{ categoryId: cat.id }}
                    className="flex items-center gap-2"
                  >
                    <Pencil className="size-3.5" />
                    Edit
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => setDeleteId(cat.id)}
                  className="text-destructive focus:text-destructive flex items-center gap-2"
                  disabled={cat.children_count > 0}
                >
                  <Trash2 className="size-3.5" />
                  {cat.children_count > 0 ? "Has subcategories" : "Delete"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </td>
        </tr>
        {hasChildren &&
          isExpanded &&
          !isSearching &&
          children.map((child) => renderRow(child, depth + 1))}
      </>
    );
  }

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Catalogue</p>
          <h1 className="font-display text-4xl mt-1">
            Categories <span className="text-muted-foreground text-2xl">({total})</span>
          </h1>
        </div>
        <button
          onClick={() => navigate({ to: "/admin/categories/new" })}
          className="inline-flex items-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-5 py-3 hover:opacity-90 transition-opacity"
        >
          <Plus className="size-3.5" />
          New Category
        </button>
      </header>

      {/* Filters */}
      <div className="bg-background border border-border p-4 flex flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-2 border border-border px-3 py-2 flex-1 min-w-[200px]">
          <Search className="size-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search by name or slug…"
            className="flex-1 bg-transparent outline-none text-sm"
          />
        </div>
        <div className="flex border border-border text-xs">
          {(
            [
              [undefined, "All"],
              [true, "Active"],
              [false, "Inactive"],
            ] as const
          ).map(([val, label], i) => (
            <button
              key={label}
              onClick={() => {
                setIsActive(val);
                setPage(1);
              }}
              className={`px-3 py-2 transition ${i > 0 ? "border-l border-border" : ""} ${
                isActive === val ? "bg-foreground text-background" : "hover:bg-secondary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="bg-accent/10 border border-accent/30 px-4 py-2 flex items-center gap-3 mb-4">
          <span className="text-sm">{selected.size} selected</span>
          <div className="flex gap-2 ml-auto">
            {(
              [
                ["activate", "Activate"],
                ["deactivate", "Deactivate"],
                ["delete", "Delete"],
              ] as const
            ).map(([action, label]) => (
              <button
                key={action}
                onClick={() => bulkMutation.mutate({ ids: [...selected], action })}
                disabled={bulkMutation.isPending}
                className={`text-[10px] uppercase tracking-[0.2em] px-3 py-1.5 border border-border hover:bg-secondary transition ${
                  action === "delete" ? "text-destructive hover:bg-destructive/10" : ""
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-background border border-border overflow-x-auto">
        {isLoading ? (
          <TableSkeleton
            headers={[
              "",
              "Image",
              "Name",
              "Parent",
              "Products",
              "Order",
              "Status",
              "Updated",
              "Actions",
            ]}
            rows={8}
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={selected.size === items.length && items.length > 0}
                    onChange={() =>
                      selected.size === items.length
                        ? setSelected(new Set())
                        : setSelected(new Set(items.map((i) => i.id)))
                    }
                    className="cursor-pointer"
                  />
                </th>
                <th className="px-4 py-3 w-12">Img</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Parent</th>
                <th className="px-4 py-3">Products</th>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Updated</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {topLevel.map((cat) => renderRow(cat, 0))}
              {topLevel.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-16 text-center text-muted-foreground text-sm">
                    No categories found.{" "}
                    <Link to="/admin/categories/new" className="underline hover:text-foreground">
                      Create your first category
                    </Link>
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
            Page {page} of {totalPages} · {total} categories
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

      <AlertDialog open={!!deleteId} onOpenChange={(v) => !v && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Category?</AlertDialogTitle>
            <AlertDialogDescription>
              This will soft-delete the category. You cannot delete categories that have
              subcategories. Products in this category will not be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteId && deleteMutation.mutate(deleteId)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
