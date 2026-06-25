import { createFileRoute } from "@tanstack/react-router";
import { ProductForm } from "@/components/admin/products/ProductForm";

export const Route = createFileRoute("/admin/products/new")({
  component: NewProductPage,
});

function NewProductPage() {
  return <ProductForm mode="new" />;
}
