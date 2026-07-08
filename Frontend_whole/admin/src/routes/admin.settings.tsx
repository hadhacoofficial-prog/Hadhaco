import { createFileRoute } from "@tanstack/react-router";
import { SettingsForm } from "@/components/admin/settings/SettingsForm";

export const Route = createFileRoute("/admin/settings")({
  component: SettingsForm,
});
