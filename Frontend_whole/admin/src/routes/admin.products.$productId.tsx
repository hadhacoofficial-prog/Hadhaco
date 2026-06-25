import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { ProductForm } from "@/components/admin/products/ProductForm";
import type { ProductDetail, CollectionDto } from "@/types/admin";

export const Route = createFileRoute("/admin/products/$productId")({
  component: EditProductPage,
});

function EditProductPage() {
  const { productId } = Route.useParams();

  const { data: product, isLoading: productLoading } = useQuery({
    queryKey: queryKeys.admin.product(productId),
    queryFn: () => api.get<ProductDetail>(`/admin/products/${productId}`),
    staleTime: 30_000,
  });

  const { data: productCollections, isLoading: colLoading } = useQuery({
    queryKey: queryKeys.admin.productCollections(productId),
    queryFn: () => api.get<CollectionDto[]>(`/admin/products/${productId}/collections`),
    staleTime: 30_000,
  });

  if (productLoading || colLoading) {
    return (
      <div className="min-h-screen bg-secondary/20 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="size-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">Loading product…</p>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="min-h-screen bg-secondary/20 flex items-center justify-center">
        <p className="text-muted-foreground">Product not found.</p>
      </div>
    );
  }

  return (
    <ProductForm
      mode="edit"
      initialProduct={product}
      initialCollectionIds={productCollections?.map((c) => c.id) ?? []}
    />
  );
}
