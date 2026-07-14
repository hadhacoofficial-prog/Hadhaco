import { createFileRoute, Outlet } from "@tanstack/react-router";
import { NotificationsNav } from "@/components/admin/notifications/NotificationsNav";

export const Route = createFileRoute("/admin/notifications")({
  component: NotificationsLayout,
});

function NotificationsLayout() {
  return (
    <div>
      <header className="mb-2">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
          Notification Management
        </p>
        <h1 className="font-display text-4xl mt-1">Notifications</h1>
      </header>
      <NotificationsNav />
      <Outlet />
    </div>
  );
}
