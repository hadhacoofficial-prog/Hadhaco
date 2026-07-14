import { createFileRoute } from "@tanstack/react-router";
import { NotificationMatrixTable } from "@/components/admin/notifications/NotificationMatrixTable";

export const Route = createFileRoute("/admin/notifications/matrix")({
  component: NotificationMatrixTable,
});
