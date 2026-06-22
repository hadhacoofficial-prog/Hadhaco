import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { Link } from "@tanstack/react-router";
import { CollectionForm } from "@/components/admin/collections/CollectionForm";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { CollectionDetail } from "@/types/admin";

export const Route = createFileRoute("/admin/collections/$collectionId/edit")({
  component: EditCollectionPage,
});

function EditCollectionPage() {
  const { collectionId } = Route.useParams();

  const { data: collection, isLoading } = useQuery({
    queryKey: queryKeys.admin.collection(collectionId),
    queryFn: () => api.get<CollectionDetail>(`/admin/collections/${collectionId}`),
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

  return <CollectionForm mode="edit" collection={collection} />;
}
