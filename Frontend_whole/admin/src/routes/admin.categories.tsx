import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/categories")({
  component: AdminCategoriesLayout,
});

function AdminCategoriesLayout() {
  return <Outlet />;
}
