import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { CategoryForm } from "@/components/admin/categories/CategoryForm";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { CategoryDetail } from "@/types/admin";

export const Route = createFileRoute("/admin/categories/$categoryId/edit")({
  component: EditCategoryPage,
});

function EditCategoryPage() {
  const { categoryId } = Route.useParams();

  const { data: category, isLoading } = useQuery({
    queryKey: queryKeys.admin.category(categoryId),
    queryFn: () => api.get<CategoryDetail>(`/admin/categories/${categoryId}`),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
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

  return <CategoryForm mode="edit" category={category} />;
}
