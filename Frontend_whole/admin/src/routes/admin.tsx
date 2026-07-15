import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router";
import { useEffect, useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuthRedirectUrl } from "@hadha/shared-utils";
import { getSession } from "@/lib/supabase/session";
import { roleSatisfies } from "@/types/auth";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ProfileDto } from "@/types/profile";
import type { TwoFactorStatus } from "@/types/admin";
import { useAuthContext } from "@/providers/auth-context";
import {
  LayoutDashboard,
  Package,
  ShoppingBag,
  Users,
  ArrowLeft,
  Boxes,
  Star,
  LayoutTemplate,
  Ticket,
  BarChart3,
  LogOut,
  FolderOpen,
  Tag,
  Settings2,
  MessageSquare,
  Menu,
  Bell,
  Loader2,
} from "lucide-react";
import markAsset from "@/assets/hadha-mark.png";

export const Route = createFileRoute("/admin")({
  beforeLoad: async ({ context: { queryClient }, location }) => {
    if (location.pathname === "/admin/login") return;
    if (typeof window === "undefined") return;

    const session = await getSession();
    if (!session) {
      throw redirect({
        to: "/admin/login",
        search: { redirect: getAuthRedirectUrl(location) },
      });
    }

    let profile: ProfileDto | null = null;
    try {
      profile = await queryClient.fetchQuery({
        queryKey: queryKeys.profile.me,
        queryFn: () => api.get<ProfileDto>("/me"),
        staleTime: 60_000,
      });
    } catch {
      throw redirect({ to: "/admin/login", search: { redirect: getAuthRedirectUrl(location) } });
    }

    const role = profile?.role;
    const normalizedRole =
      role === "customer" || role === "admin" || role === "super_admin" ? role : null;
    if (!roleSatisfies(normalizedRole, "admin")) throw redirect({ to: "/" });
  },
  head: () => ({
    meta: [{ title: "Admin · Hadha" }, { name: "robots", content: "noindex" }],
  }),
  component: AdminLayout,
});

type NavTo =
  | "/admin"
  | "/admin/products"
  | "/admin/collections"
  | "/admin/categories"
  | "/admin/inventory"
  | "/admin/orders"
  | "/admin/customers"
  | "/admin/reviews"
  | "/admin/coupons"
  | "/admin/cms"
  | "/admin/reports"
  | "/admin/templates"
  | "/admin/settings"
  | "/admin/enquiries"
  | "/admin/notifications";

type NavItem = {
  to: NavTo;
  label: string;
  icon: React.ReactNode;
  exact?: boolean;
};

const nav: NavItem[] = [
  {
    to: "/admin",
    label: "Dashboard",
    icon: <LayoutDashboard className="size-4" />,
    exact: true,
  },
  { to: "/admin/products", label: "Products", icon: <Package className="size-4" /> },
  { to: "/admin/collections", label: "Collections", icon: <FolderOpen className="size-4" /> },
  { to: "/admin/categories", label: "Categories", icon: <Tag className="size-4" /> },
  { to: "/admin/inventory", label: "Inventory", icon: <Boxes className="size-4" /> },
  { to: "/admin/orders", label: "Orders", icon: <ShoppingBag className="size-4" /> },
  { to: "/admin/customers", label: "Customers", icon: <Users className="size-4" /> },
  { to: "/admin/reviews", label: "Reviews", icon: <Star className="size-4" /> },
  { to: "/admin/coupons", label: "Coupons", icon: <Ticket className="size-4" /> },
  { to: "/admin/enquiries", label: "Enquiries", icon: <MessageSquare className="size-4" /> },
  { to: "/admin/notifications", label: "Notifications", icon: <Bell className="size-4" /> },
  { to: "/admin/cms", label: "Homepage CMS", icon: <LayoutTemplate className="size-4" /> },
  { to: "/admin/reports", label: "Reports", icon: <BarChart3 className="size-4" /> },
  { to: "/admin/templates", label: "Templates", icon: <Settings2 className="size-4" /> },
  { to: "/admin/settings", label: "Store Settings", icon: <Settings2 className="size-4" /> },
];

const SIDEBAR_WIDTH = 260;
const SIDEBAR_WIDTH_COLLAPSED = 64;
const STORAGE_KEY = "hadha:admin:sidebar-collapsed";

function getInitialCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored !== null) return stored === "true";
  return window.innerWidth < 1440;
}

function AdminLayout() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { isAuthenticated } = useAuthContext();
  const navigate = useNavigate();

  const [collapsed, setCollapsed] = useState<boolean>(getInitialCollapsed);

  const toggleSidebar = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }, []);

  // Auto-collapse on small screens
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1439px)");
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      if (e.matches) {
        setCollapsed(true);
        localStorage.setItem(STORAGE_KEY, "true");
      }
    };
    handler(mq);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: queryKeys.profile.me,
    queryFn: () => api.get<ProfileDto>("/me"),
    enabled: isAuthenticated,
    staleTime: 60_000,
    retry: 1,
  });

  const { data: tfStatus } = useQuery({
    queryKey: queryKeys.admin.twoFactorStatus,
    queryFn: () => api.get<TwoFactorStatus>("/auth/admin/2fa/status"),
    enabled: isAuthenticated,
    staleTime: 60_000,
    retry: 1,
  });

  const role = profile?.role;
  const normalizedRole =
    role === "customer" || role === "admin" || role === "super_admin" ? role : null;
  const isAdmin = roleSatisfies(normalizedRole, "admin");

  useEffect(() => {
    if (path === "/admin/login" || path === "/admin/2fa") return;
    if (!isAuthenticated) {
      const redirectUrl = getAuthRedirectUrl(window.location, "/admin");
      navigate({ to: "/admin/login", search: { redirect: redirectUrl } });
      return;
    }
    if (!profileLoading && !isAdmin) {
      navigate({ to: "/" });
      return;
    }
    // If 2FA is enabled but not verified in this session, redirect to challenge
    if (tfStatus?.is_enabled && !sessionStorage.getItem("hadha:2fa_verified")) {
      const redirectUrl = getAuthRedirectUrl(window.location, "/admin");
      navigate({ to: "/admin/2fa", search: { redirect: redirectUrl } });
    }
  }, [isAuthenticated, profileLoading, isAdmin, tfStatus, path, navigate]);

  if (path === "/admin/login" || path === "/admin/2fa") {
    return <Outlet />;
  }

  if (!isAuthenticated || profileLoading || !profile || !isAdmin) {
    return (
      <div className="min-h-screen bg-secondary/40 flex items-center justify-center">
        <div className="size-8 border-2 border-foreground border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const sidebarWidth = collapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH;

  return (
    <div className="min-h-screen bg-secondary/40 flex">
      {/* ── Sidebar ── */}
      <aside
        className="bg-foreground text-background lg:min-h-screen flex flex-col shrink-0 overflow-hidden transition-[width] duration-250 ease-in-out"
        style={{ width: sidebarWidth }}
      >
        {/* Header */}
        <div className="flex-none px-4 pt-5 pb-3 flex items-center gap-3">
          <button
            onClick={toggleSidebar}
            className="flex-none p-1.5 rounded-md hover:bg-background/10 transition-colors"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <Menu className="size-5" />
          </button>
          {!collapsed && (
            <>
              <Link to="/" className="flex items-center gap-2.5 min-w-0">
                <img src={markAsset} alt="Hadha" className="h-8 w-auto shrink-0" />
                <span className="font-display text-xl tracking-wide truncate">Hadha</span>
              </Link>
            </>
          )}
        </div>
        {!collapsed && (
          <p className="text-[10px] uppercase tracking-[0.3em] text-background/60 px-6 pb-1">
            Admin CMS
          </p>
        )}

        {/* Nav */}
        <nav className="mt-4 space-y-0.5 flex-1 px-2">
          {nav.map((n) => {
            const active = n.exact ? path === n.to : path.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                title={collapsed ? n.label : undefined}
                className={`flex items-center gap-3 px-3 py-2.5 text-sm transition rounded-lg ${
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-background/80 hover:bg-background/10"
                } ${collapsed ? "justify-center" : ""}`}
              >
                <span className="shrink-0">{n.icon}</span>
                {!collapsed && <span className="truncate">{n.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div
          className={`flex-none border-t border-background/10 px-3 py-3 space-y-1.5 ${collapsed ? "flex flex-col items-center" : ""}`}
        >
          <Link
            to="/"
            title={collapsed ? "Back to storefront" : undefined}
            className={`flex items-center gap-2 text-xs text-background/60 hover:text-background transition rounded-md px-2 py-1.5 ${
              collapsed ? "justify-center" : ""
            }`}
          >
            <ArrowLeft className="size-3.5 shrink-0" />
            {!collapsed && <span>Back to storefront</span>}
          </Link>
          <div className={collapsed ? "flex justify-center" : ""}>
            <LogoutButton collapsed={collapsed} />
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 min-w-0 p-6 md:p-10">
        <Outlet />
      </main>
    </div>
  );
}

function LogoutButton({ collapsed }: { collapsed: boolean }) {
  const { logout } = useAuthContext();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      setIsLoggingOut(false);
      navigate({ to: "/admin/login", search: { redirect: undefined } });
    }
  }

  return (
    <button
      onClick={handleLogout}
      disabled={isLoggingOut}
      aria-busy={isLoggingOut}
      title={collapsed ? "Sign out" : undefined}
      className={`flex items-center gap-2 text-xs text-background/60 hover:text-background transition w-full text-left rounded-md px-2 py-1.5 disabled:opacity-60 ${
        collapsed ? "justify-center" : ""
      }`}
    >
      {isLoggingOut ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin" />
      ) : (
        <LogOut className="size-3.5 shrink-0" />
      )}
      {!collapsed && <span>{isLoggingOut ? "Signing out…" : "Sign out"}</span>}
    </button>
  );
}
