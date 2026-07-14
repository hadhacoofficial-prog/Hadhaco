import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/notifications/templates")({
  component: () => <Outlet />,
});
