import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import { NotificationLogsTable } from "@/components/admin/notifications/NotificationLogsTable";
import { dateRangeFields, urlEnum, urlPage, urlText } from "@/lib/tableUrlState";

// Read by NotificationLogsTable via useSearch({ from: "/admin/notifications/logs" }).
const notificationLogsSearchSchema = z.object({
  q: urlText,
  status: urlEnum(["pending", "retrying", "sent", "delivered", "read", "failed"]),
  channel: urlEnum(["email", "whatsapp"]),
  ...dateRangeFields,
  page: urlPage,
});

export const Route = createFileRoute("/admin/notifications/logs")({
  validateSearch: notificationLogsSearchSchema,
  component: NotificationLogsTable,
});
