import { useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2, ImageIcon, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
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
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { toUserMessage } from "@/lib/api/errors";
import { formatINR } from "@/lib/format";
import type { CategoryDetail, CategoryProductsResponse } from "@/types/admin";

export const Route = createFileRoute("/admin/categories/$categoryId/")({
  component: CategoryDetailPage,
});

function CategoryDetailPage() {
  const { categoryId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const { data: category, isLoading: categoryLoading } = useQuery({
    queryKey: queryKeys.admin.category(categoryId),
    queryFn: () => api.get<CategoryDetail>(`/admin/categories/${categoryId}`),
    staleTime: 30_000,
  });

  const productsParams = { page, page_size: 20 };
  const { data: productsData, isLoading: productsLoading } = useQuery({
    queryKey: queryKeys.admin.categoryProducts(categoryId, productsParams),
    queryFn: () =>
      api.get<CategoryProductsResponse>(`/admin/categories/${categoryId}/products`, {
        params: productsParams,
      }),
    staleTime: 15_000,
    enabled: !!categoryId,
  });

  const deleteCategoryMutation = useMutation({
    mutationFn: () => api.delete<void>(`/admin/categories/${categoryId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.categories });
      toast.success("Category deleted.");
      navigate({ to: "/admin/categories" });
    },
    onError: (e) => toast.error(toUserMessage(e)),
  });

  const totalPages = productsData?.total_pages ?? 1;

  if (categoryLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!category) {
    return (
      <div className="text-center py-20 text-muted-foreground">
        Category not found.{" "}
        <Link to="/admin/categories" className="underline hover:text-foreground">
          Back to Categories
        </Link>
      </div>
    );
  }

  const canDelete = category.children_count === 0;

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
        <Link to="/admin/categories" className="hover:text-foreground transition">
          Categories
        </Link>
        {category.parent_id && (
          <>
            <span>/</span>
            <span>Parent</span>
          </>
        )}
        <span>/</span>
        <span className="text-foreground">{category.name}</span>
      </nav>

      {/* Header */}
      <header className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          {category.image_url ? (
            <ImageWithFallback
              src={category.image_url}
              alt={category.name}
              className="size-16 bg-secondary shrink-0"
            />
          ) : (
            <div className="size-16 bg-secondary flex items-center justify-center shrink-0">
              <ImageIcon className="size-6 text-muted-foreground" />
            </div>
          )}
          <div>
            <h1 className="font-display text-3xl">{category.name}</h1>
            <p className="text-sm text-muted-foreground font-mono">{category.slug}</p>
            <div className="flex items-center gap-3 mt-1">
              <span
                className={`text-[10px] uppercase tracking-[0.2em] px-2 py-0.5 ${
                  category.is_active
                    ? "bg-accent/15 text-accent"
                    : "bg-secondary text-muted-foreground"
                }`}
              >
                {category.is_active ? "Active" : "Inactive"}
              </span>
              <span className="text-xs text-muted-foreground">
                {category.product_count} products
              </span>
              {category.children_count > 0 && (
                <span className="text-xs text-muted-foreground">
                  {category.children_count} subcategories
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/admin/categories/$categoryId/edit"
            params={{ categoryId }}
            className="inline-flex items-center gap-2 border border-border px-4 py-2 text-sm hover:bg-secondary transition"
          >
            <Pencil className="size-3.5" />
            Edit
          </Link>
          <button
            onClick={() => setDeleteOpen(true)}
            disabled={!canDelete}
            title={!canDelete ? "Delete subcategories first" : ""}
            className="inline-flex items-center gap-2 border border-destructive/40 text-destructive px-4 py-2 text-sm hover:bg-destructive/10 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Trash2 className="size-3.5" />
            Delete
          </button>
        </div>
      </header>

      {category.description && (
        <div className="bg-background border border-border p-6 mb-6">
          <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground mb-2">
            Description
          </h2>
          <p className="text-sm leading-relaxed">{category.description}</p>
        </div>
      )}

      {/* Products */}
      <div className="bg-background border border-border">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-[11px] uppercase tracking-[0.25em] text-muted-foreground">
            Products in Category ({productsData?.total ?? 0})
          </h2>
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
            <p>No products in this category.</p>
            <p className="text-xs mt-1">
              Assign products to this category from the{" "}
              <Link to="/admin/products" className="underline hover:text-foreground">
                Products
              </Link>{" "}
              page.
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary text-left text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  <tr>
                    <th className="px-6 py-3">Product</th>
                    <th className="px-4 py-3">SKU</th>
                    <th className="px-4 py-3">Price</th>
                    <th className="px-4 py-3">Stock</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {productsData?.items.map((p) => (
                    <tr key={p.id} className="hover:bg-secondary/40">
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-3">
                          {p.primary_image ? (
                            <ImageWithFallback
                              src={p.primary_image}
                              alt=""
                              className="size-10 bg-secondary shrink-0"
                            />
                          ) : (
                            <div className="size-10 bg-secondary shrink-0 flex items-center justify-center">
                              <ImageIcon className="size-4 text-muted-foreground" />
                            </div>
                          )}
                          <Link
                            to="/admin/products/$productId"
                            params={{ productId: p.id }}
                            className="hover:underline line-clamp-1"
                          >
                            {p.name}
                          </Link>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{p.sku}</td>
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
                        <Link
                          to="/admin/products/$productId"
                          params={{ productId: p.id }}
                          className="text-muted-foreground hover:text-foreground transition inline-flex"
                        >
                          <Pencil className="size-4" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between px-6 py-4 border-t border-border">
                <p className="text-sm text-muted-foreground">
                  Page {page} of {totalPages}
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

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete "{category.name}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This will soft-delete the category. Products will not be affected but will lose this
              category assignment.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteCategoryMutation.mutate()}
              disabled={deleteCategoryMutation.isPending}
              aria-busy={deleteCategoryMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteCategoryMutation.isPending && (
                <Loader2 className="size-3.5 animate-spin mr-2" />
              )}
              {deleteCategoryMutation.isPending ? "Deleting…" : "Delete Category"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
