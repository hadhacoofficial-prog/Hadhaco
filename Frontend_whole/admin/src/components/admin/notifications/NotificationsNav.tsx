import { Link, useRouterState } from "@tanstack/react-router";

type NotifNavItem = {
  to:
    | "/admin/notifications"
    | "/admin/notifications/matrix"
    | "/admin/notifications/templates"
    | "/admin/notifications/providers"
    | "/admin/notifications/logs"
    | "/admin/notifications/analytics";
  label: string;
  exact?: boolean;
};

const items: NotifNavItem[] = [
  { to: "/admin/notifications", label: "Dashboard", exact: true },
  { to: "/admin/notifications/matrix", label: "Notification Matrix" },
  { to: "/admin/notifications/templates", label: "Templates" },
  { to: "/admin/notifications/providers", label: "Provider Settings" },
  { to: "/admin/notifications/logs", label: "Notification Logs" },
  { to: "/admin/notifications/analytics", label: "Analytics" },
];

export function NotificationsNav() {
  const path = useRouterState({ select: (s) => s.location.pathname });

  return (
    <nav
      aria-label="Notification Management sections"
      className="flex flex-wrap gap-1 border-b border-border mb-8 -mt-1"
    >
      {items.map((item) => {
        const active = item.exact ? path === item.to : path.startsWith(item.to);
        return (
          <Link
            key={item.to}
            to={item.to}
            className={`px-3.5 py-2.5 text-sm border-b-2 -mb-px transition-colors ${
              active
                ? "border-accent text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
