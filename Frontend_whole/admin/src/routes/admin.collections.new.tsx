import { createFileRoute } from "@tanstack/react-router";
import { CollectionForm } from "@/components/admin/collections/CollectionForm";

export const Route = createFileRoute("/admin/collections/new")({
  component: NewCollectionPage,
});

function NewCollectionPage() {
  return <CollectionForm mode="new" />;
}
