import { useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Pencil,
  Trash2,
  Plus,
  ImageIcon,
  Star,
  GripVertical,
  X,
  ChevronLeft,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
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
import { Skeleton } from "@/components/ui/skeleton";
import { ProductPickerModal } from "@/components/admin/ProductPickerModal";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import type { CollectionDetail, CollectionProductsResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/collections/$collectionId/")({
  component: CollectionDetailPage,
});

function CollectionDetailPage() {
  const { collectionId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [removeProductId, setRemoveProductId] = useState<string | null>(null);

  const { data: collection, isLoading: collectionLoading } = useQuery({
    queryKey: queryKeys.admin.collection(collectionId),
    queryFn: () => api.get<CollectionDetail>(`/admin/collections/${collectionId}`),
    staleTime: 30_000,
  });

  const productsParams = { page, page_size: 20 };
  const { data: productsData, isLoading: productsLoading } = useQuery({
    queryKey: queryKeys.admin.collectionProducts(collectionId, productsParams),
    queryFn: () =>
      api.get<CollectionProductsResponse>(
        `/admin/collections/${collectionId}/products`,
        { params: productsParams }
      ),
    staleTime: 15_000,
    enabled: !!collectionId,
  });

  const addProductsMutation = useMutation({
    mutationFn: (ids: string[]) =>
      api.post<void>(`/admin/collections/${collectionId}/products`, {
        body: { product_ids: ids },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.collectionProducts(collectionId, {}),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.collection(collectionId),
      });
      toast.success("Products added to collection.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const removeProductMutation = useMutation({
    mutationFn: (productId: string) =>
      api.delete<void>(`/admin/collections/${collectionId}/products/${productId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.collectionProducts(collectionId, {}),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.collection(collectionId),
      });
      setRemoveProductId(null);
      toast.success("Product removed from collection.");
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const deleteCollectionMutation = useMutation({
    mutationFn: () => api.delete<void>(`/admin/collections/${collectionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.collections });
      toast.success("Collection deleted.");
      navigate({ to: "/admin/collections" });
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const existingProductIds = productsData?.items.map((p) => p.id) ?? [];
  const totalPages = productsData?.total_pages ?? 1;

  if (collectionLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="bg-background border border-border p-6 space-y-4">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    );
  }

  if (!collection) {
    return (
      <div className="text-center py-20 text-muted-foreground">
        Collection not found.{" "}
        <Link to="/admin/collections" className="underline hover:text-foreground">
          Back to Collections
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
        <Link to="/admin/collections" className="hover:text-foreground transition">
          Collections
        </Link>
        <span>/</span>
        <span className="text-foreground">{collection.name}</span>
      </nav>

      {/* Header */}
      <header className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          {collection.image_url ? (
            <img
              src={collection.image_url}
              alt={collection.name}
              className="size-16 object-cover bg-secondary shrink-0"
            />
          ) : (
            <div className="size-16 bg-secondary flex items-center justify-center shrink-0">
              <ImageIcon className="size-6 text-muted-foreground" />
            </div>
          )}
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-3xl">{collection.name}</h1>
              {collection.is_featured && (
                <Star className="size-4 fill-amber-400 text-amber-400" />
              )}
            </div>
            <p className="text-sm text-muted-foreground font-mono">{collection.slug}</p>
            <div className="flex items-center gap-3 mt-1">
              <span
                className={`text-[10px] uppercase tracking-[0.2em] px-2 py-0.5 ${
                  collection.is_active
                    ? "bg-accent/15 text-accent"
                    : "bg-secondary text-muted-foreground"
                }`}
              >
                {collection.is_active ? "Active" : "Inactive"}
              </span>
              <span className="text-xs text-muted-foreground">
                {collection.product_count} products
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/admin/collections/$collectionId/edit"
            params={{ collectionId }}
            className="inline-flex items-center gap-2 border border-border px-4 py-2 text-sm hover:bg-secondary transition"
          >
            <Pencil className="size-3.5" />
            Edit
          </Link>
          <button
            onClick={() => setDeleteOpen(true)}
            className="inline-flex items-center gap-2 border border-destructive/40 text-destructive px-4 py-2 text-sm hover:bg-destructive/10 transition"
          >
            <Trash2 className="size-3.5" />
            Delete
          </button>
        </div>
      </header>

      {/* Info cards */}
      {collection.description && (
        <div className="bg-background border border-border p-6 mb-6">
          <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-2">
            Description
          </h2>
          <p className="text-sm leading-relaxed">{collection.description}</p>
        </div>
      )}

      {/* Products section */}
      <div className="bg-background border border-border">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
            Products in Collection ({productsData?.total ?? 0})
          </h2>
          <button
            onClick={() => setPickerOpen(true)}
            className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] px-4 py-2 bg-foreground text-background hover:opacity-90 transition"
          >
            <Plus className="size-3" />
            Add Products
          </button>
        </div>

        {productsLoading ? (
          <div className="divide-y divide-border">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-6 py-3">
                <Skeleton className="size-10 shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-48" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </div>
            ))}
          </div>
        ) : productsData?.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-sm">
            <ImageIcon className="size-8 mb-3 opacity-30" />
            <p>No products in this collection yet.</p>
            <button
              onClick={() => setPickerOpen(true)}
              className="mt-4 text-[10px] uppercase tracking-[0.2em] px-4 py-2 bg-foreground text-background hover:opacity-90 transition"
            >
              Add Products
            </button>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  <tr>
                    <th className="px-6 py-3 w-8"></th>
                    <th className="px-4 py-3">Product</th>
                    <th className="px-4 py-3">SKU</th>
                    <th className="px-4 py-3">Price</th>
                    <th className="px-4 py-3">Stock</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {productsData?.items.map((p) => (
                    <tr key={p.id} className="hover:bg-secondary/40 group">
                      <td className="px-6 py-3 text-muted-foreground/40 cursor-grab">
                        <GripVertical className="size-4" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          {p.primary_image ? (
                            <img
                              src={p.primary_image}
                              alt=""
                              className="size-10 object-cover bg-secondary shrink-0"
                            />
                          ) : (
                            <div className="size-10 bg-secondary shrink-0 flex items-center justify-center">
                              <ImageIcon className="size-4 text-muted-foreground" />
                            </div>
                          )}
                          <div>
                            <Link
                              to="/admin/products/$productId"
                              params={{ productId: p.id }}
                              className="hover:underline line-clamp-1"
                            >
                              {p.name}
                            </Link>
                            {p.is_featured && (
                              <Star className="size-3 fill-amber-400 text-amber-400 inline ml-1" />
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {p.sku}
                      </td>
                      <td className="px-4 py-3 font-display">{formatINR(p.base_price)}</td>
                      <td className="px-4 py-3">{p.stock_quantity}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-[10px] uppercase tracking-[0.2em] px-2 py-0.5 ${
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
                        <div className="flex items-center justify-end gap-2">
                          <Link
                            to="/admin/products/$productId"
                            params={{ productId: p.id }}
                            className="text-muted-foreground hover:text-foreground transition"
                          >
                            <Pencil className="size-4" />
                          </Link>
                          <button
                            onClick={() => setRemoveProductId(p.id)}
                            className="text-muted-foreground hover:text-destructive transition"
                          >
                            <X className="size-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between px-6 py-4 border-t border-border">
                <p className="text-sm text-muted-foreground">
                  Page {page} of {totalPages} · {productsData?.total} products
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
          </>
        )}
      </div>

      {/* Product picker */}
      <ProductPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        excludeIds={existingProductIds}
        onSelect={(ids) => addProductsMutation.mutate(ids)}
        loading={addProductsMutation.isPending}
        title="Add Products to Collection"
      />

      {/* Remove product confirm */}
      <AlertDialog
        open={!!removeProductId}
        onOpenChange={(v) => !v && setRemoveProductId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove Product?</AlertDialogTitle>
            <AlertDialogDescription>
              The product will be removed from this collection but will not be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                removeProductId && removeProductMutation.mutate(removeProductId)
              }
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete collection confirm */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete "{collection.name}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This will soft-delete the collection. All product associations will remain but the
              collection will no longer be visible.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteCollectionMutation.mutate()}
              disabled={deleteCollectionMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteCollectionMutation.isPending && (
                <Loader2 className="size-3.5 animate-spin mr-2" />
              )}
              Delete Collection
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
