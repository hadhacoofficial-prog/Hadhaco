import { createFileRoute } from "@tanstack/react-router";
import { NotificationLogsTable } from "@/components/admin/notifications/NotificationLogsTable";

export const Route = createFileRoute("/admin/notifications/logs")({
  component: NotificationLogsTable,
});
