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
  Star,
  StarOff,
  ImageIcon,
  ChevronLeft,
  ChevronRight,
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
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { useDebounce } from "@hadha/shared-ui/common/use-debounce";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import type { CollectionListResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/collections/")({
  component: AdminCollections,
});

function AdminCollections() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [isActive, setIsActive] = useState<boolean | undefined>(undefined);
  const [isFeatured, setIsFeatured] = useState<boolean | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const debouncedSearch = useDebounce(search, 300);

  const params = useMemo(
    () => ({
      page,
      page_size: 20,
      search: debouncedSearch || undefined,
      is_active: isActive,
      is_featured: isFeatured,
      sort_by: "sort_order",
      sort_dir: "asc",
    }),
    [page, debouncedSearch, isActive, isFeatured],
  );

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.collectionsList(params),
    queryFn: () => api.get<CollectionListResponse>("/admin/collections", { params }),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete<void>(`/admin/collections/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.collections });
      toast.success("Collection deleted.");
      setDeleteId(null);
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const bulkMutation = useMutation({
    mutationFn: (body: { ids: string[]; action: string }) =>
      api.post<void>("/admin/collections/bulk", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.collections });
      setSelected(new Set());
      toast.success("Bulk action applied.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.patch<void>(`/admin/collections/${id}`, { body: { is_active } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.collections }),
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const toggleFeaturedMutation = useMutation({
    mutationFn: ({ id, is_featured }: { id: string; is_featured: boolean }) =>
      api.patch<void>(`/admin/collections/${id}`, { body: { is_featured } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.collections }),
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;

  function toggleSelectAll() {
    if (selected.size === items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((i) => i.id)));
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div>
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Catalogue</p>
          <h1 className="font-display text-4xl mt-1">
            Collections <span className="text-muted-foreground text-2xl">({total})</span>
          </h1>
        </div>
        <button
          onClick={() => navigate({ to: "/admin/collections/new" })}
          className="inline-flex items-center gap-2 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-5 py-3 hover:opacity-90 transition-opacity"
        >
          <Plus className="size-3.5" />
          New Collection
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
            placeholder="Search by name, slug…"
            className="flex-1 bg-transparent outline-none text-sm"
          />
        </div>
        <FilterButton
          label="Active"
          value={isActive}
          onAll={() => {
            setIsActive(undefined);
            setPage(1);
          }}
          onTrue={() => {
            setIsActive(true);
            setPage(1);
          }}
          onFalse={() => {
            setIsActive(false);
            setPage(1);
          }}
        />
        <FilterButton
          label="Featured"
          value={isFeatured}
          onAll={() => {
            setIsFeatured(undefined);
            setPage(1);
          }}
          onTrue={() => {
            setIsFeatured(true);
            setPage(1);
          }}
          onFalse={() => {
            setIsFeatured(false);
            setPage(1);
          }}
        />
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
                ["feature", "Feature"],
                ["unfeature", "Unfeature"],
                ["delete", "Delete"],
              ] as const
            ).map(([action, label]) => (
              <button
                key={action}
                onClick={() =>
                  bulkMutation.mutate({
                    ids: [...selected],
                    action,
                  })
                }
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
              "Status",
              "Featured",
              "Order",
              "Products",
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
                    onChange={toggleSelectAll}
                    className="cursor-pointer"
                  />
                </th>
                <th className="px-4 py-3 w-16">Image</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Featured</th>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Products</th>
                <th className="px-4 py-3">Updated</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((col) => (
                <tr
                  key={col.id}
                  className={`hover:bg-secondary/40 transition-colors ${
                    selected.has(col.id) ? "bg-accent/5" : ""
                  }`}
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(col.id)}
                      onChange={() => toggleSelect(col.id)}
                      className="cursor-pointer"
                    />
                  </td>
                  <td className="px-4 py-3">
                    {col.image_url ? (
                      <ImageWithFallback
                        src={col.image_url}
                        alt=""
                        className="size-10 bg-secondary"
                      />
                    ) : (
                      <div className="size-10 bg-secondary flex items-center justify-center">
                        <ImageIcon className="size-4 text-muted-foreground" />
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div>
                      <Link
                        to="/admin/collections/$collectionId"
                        params={{ collectionId: col.id }}
                        className="hover:underline font-medium"
                      >
                        {col.name}
                      </Link>
                      <p className="text-xs text-muted-foreground font-mono">{col.slug}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() =>
                        toggleActiveMutation.mutate({
                          id: col.id,
                          is_active: !col.is_active,
                        })
                      }
                      className={`text-[10px] uppercase tracking-[0.2em] px-2 py-0.5 transition ${
                        col.is_active
                          ? "bg-accent/15 text-accent hover:bg-destructive/15 hover:text-destructive"
                          : "bg-secondary text-muted-foreground hover:bg-accent/15 hover:text-accent"
                      }`}
                    >
                      {col.is_active ? "Active" : "Inactive"}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() =>
                        toggleFeaturedMutation.mutate({
                          id: col.id,
                          is_featured: !col.is_featured,
                        })
                      }
                      className="text-muted-foreground hover:text-foreground transition"
                    >
                      {col.is_featured ? (
                        <Star className="size-4 fill-amber-400 text-amber-400" />
                      ) : (
                        <StarOff className="size-4" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{col.sort_order}</td>
                  <td className="px-4 py-3 text-muted-foreground">{col.product_count}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {new Date(col.updated_at).toLocaleDateString()}
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
                            to="/admin/collections/$collectionId"
                            params={{ collectionId: col.id }}
                            className="flex items-center gap-2"
                          >
                            <Eye className="size-3.5" />
                            View
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem asChild>
                          <Link
                            to="/admin/collections/$collectionId/edit"
                            params={{ collectionId: col.id }}
                            className="flex items-center gap-2"
                          >
                            <Pencil className="size-3.5" />
                            Edit
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => setDeleteId(col.id)}
                          className="text-destructive focus:text-destructive flex items-center gap-2"
                        >
                          <Trash2 className="size-3.5" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-16 text-center text-muted-foreground text-sm">
                    No collections found.{" "}
                    <Link to="/admin/collections/new" className="underline hover:text-foreground">
                      Create your first collection
                    </Link>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} · {total} collections
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 border border-border hover:bg-secondary disabled:opacity-50 transition"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 border border-border hover:bg-secondary disabled:opacity-50 transition"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      <AlertDialog open={!!deleteId} onOpenChange={(v) => !v && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Collection?</AlertDialogTitle>
            <AlertDialogDescription>
              This will soft-delete the collection. Products will not be removed.
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

function FilterButton({
  label,
  value,
  onAll,
  onTrue,
  onFalse,
}: {
  label: string;
  value: boolean | undefined;
  onAll: () => void;
  onTrue: () => void;
  onFalse: () => void;
}) {
  return (
    <div className="flex border border-border text-xs">
      <button
        onClick={onAll}
        className={`px-3 py-2 transition ${
          value === undefined ? "bg-foreground text-background" : "hover:bg-secondary"
        }`}
      >
        All
      </button>
      <button
        onClick={onTrue}
        className={`px-3 py-2 transition border-l border-border ${
          value === true ? "bg-foreground text-background" : "hover:bg-secondary"
        }`}
      >
        {label}
      </button>
      <button
        onClick={onFalse}
        className={`px-3 py-2 transition border-l border-border ${
          value === false ? "bg-foreground text-background" : "hover:bg-secondary"
        }`}
      >
        Not {label}
      </button>
    </div>
  );
}
