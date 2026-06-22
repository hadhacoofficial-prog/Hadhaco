import { createFileRoute } from "@tanstack/react-router";
import { CategoryForm } from "@/components/admin/categories/CategoryForm";

export const Route = createFileRoute("/admin/categories/new")({
  component: NewCategoryPage,
});

function NewCategoryPage() {
  return <CategoryForm mode="new" />;
}
