import { createFileRoute, Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Shield } from "lucide-react";

export const Route = createFileRoute("/admin/settings")({
  component: SettingsLayout,
});

function SettingsLayout() {
  const path = useRouterState({ select: (s) => s.location.pathname });

  const tabs = [
    { to: "/admin/settings", label: "General", exact: true },
    { to: "/admin/settings/security", label: "Security", icon: Shield },
  ];

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
          Configuration
        </p>
        <h1 className="font-display text-3xl mt-0.5">Settings</h1>
      </header>

      <div className="border-b border-border mb-6">
        <nav className="flex gap-0 -mb-px">
          {tabs.map((tab) => {
            const active = tab.exact ? path === tab.to : path.startsWith(tab.to);
            return (
              <Link
                key={tab.to}
                to={tab.to}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm border-b-2 transition ${
                  active
                    ? "border-foreground text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                {tab.icon && <tab.icon className="size-3.5" />}
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <Outlet />
    </div>
  );
}
