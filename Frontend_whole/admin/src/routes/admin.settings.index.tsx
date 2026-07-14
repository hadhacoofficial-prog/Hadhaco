import { createFileRoute } from "@tanstack/react-router";
import { SettingsForm } from "@/components/admin/settings/SettingsForm";

export const Route = createFileRoute("/admin/settings/")({
  component: SettingsIndex,
});

function SettingsIndex() {
  return <SettingsForm />;
}
