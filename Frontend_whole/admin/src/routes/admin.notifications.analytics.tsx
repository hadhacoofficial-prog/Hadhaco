import { createFileRoute } from "@tanstack/react-router";
import { AnalyticsCharts } from "@/components/admin/notifications/AnalyticsCharts";

export const Route = createFileRoute("/admin/notifications/analytics")({
  component: AnalyticsCharts,
});
