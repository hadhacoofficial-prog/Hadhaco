import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/collections")({
  component: AdminCollectionsLayout,
});

function AdminCollectionsLayout() {
  return <Outlet />;
}
