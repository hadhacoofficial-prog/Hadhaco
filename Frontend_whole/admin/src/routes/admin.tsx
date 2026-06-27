import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSession } from "@/lib/supabase/session";
import { roleSatisfies } from "@/types/auth";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ProfileDto } from "@/types/profile";
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
} from "lucide-react";
import markAsset from "@/assets/hadha-mark.png";

export const Route = createFileRoute("/admin")({
  beforeLoad: async ({ context: { queryClient }, location }) => {
    // Login page is public — skip the guard to avoid an infinite redirect loop.
    if (location.pathname === "/admin/login") return;

    // On the server (SSR), window is undefined and localStorage doesn't exist,
    // so getSession() always returns null. Skip here and let the component-level
    // guard handle the check client-side (it will show a loading screen until
    // the authoritative role is confirmed, blocking any admin content from appearing).
    if (typeof window === "undefined") return;

    const session = await getSession();
    if (!session) {
      throw redirect({
        to: "/admin/login",
        search: { redirect: location.pathname },
      });
    }

    // Role lives in the app's profiles table, not in Supabase app_metadata.
    let profile: ProfileDto | null = null;
    try {
      profile = await queryClient.fetchQuery({
        queryKey: queryKeys.profile.me,
        queryFn: () => api.get<ProfileDto>("/me"),
        staleTime: 60_000,
      });
    } catch {
      throw redirect({ to: "/admin/login", search: { redirect: undefined } });
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
  | "/admin/templates";

type NavItem = { to: NavTo; label: string; icon: React.ReactNode; exact?: boolean };

const nav: NavItem[] = [
  { to: "/admin", label: "Dashboard", icon: <LayoutDashboard className="size-4" />, exact: true },
  { to: "/admin/products", label: "Products", icon: <Package className="size-4" /> },
  { to: "/admin/collections", label: "Collections", icon: <FolderOpen className="size-4" /> },
  { to: "/admin/categories", label: "Categories", icon: <Tag className="size-4" /> },
  { to: "/admin/inventory", label: "Inventory", icon: <Boxes className="size-4" /> },
  { to: "/admin/orders", label: "Orders", icon: <ShoppingBag className="size-4" /> },
  { to: "/admin/customers", label: "Customers", icon: <Users className="size-4" /> },
  { to: "/admin/reviews", label: "Reviews", icon: <Star className="size-4" /> },
  { to: "/admin/coupons", label: "Coupons", icon: <Ticket className="size-4" /> },
  { to: "/admin/cms", label: "Homepage CMS", icon: <LayoutTemplate className="size-4" /> },
  { to: "/admin/reports", label: "Reports", icon: <BarChart3 className="size-4" /> },
  { to: "/admin/templates", label: "Templates", icon: <Settings2 className="size-4" /> },
];

// ─── Component-level auth gate ──────────────────────────────────────────────
//
// beforeLoad handles client-side navigations correctly (window is defined).
// But TanStack Start reuses the server's beforeLoad result during hydration, so
// the SSR skip above means the auth check never fires on the initial page load.
//
// This component gate covers that gap:
//  - Shows a spinner while the profile (authoritative role) is loading
//  - Redirects to /admin/login if unauthenticated
//  - Redirects to / if authenticated but not admin
//  - Only renders the admin shell once role === admin | super_admin is confirmed

function AdminLayout() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { isAuthenticated } = useAuthContext();
  const navigate = useNavigate();

  // Fetch authoritative profile. On client-nav this hits the beforeLoad cache
  // (no extra request). On SSR initial load this is the first real auth check.
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: queryKeys.profile.me,
    queryFn: () => api.get<ProfileDto>("/me"),
    enabled: isAuthenticated,
    staleTime: 60_000,
    retry: 1,
  });

  const role = profile?.role;
  const normalizedRole =
    role === "customer" || role === "admin" || role === "super_admin" ? role : null;
  const isAdmin = roleSatisfies(normalizedRole, "admin");

  // Fire redirects once we know auth state — never during loading, never on login page.
  useEffect(() => {
    if (path === "/admin/login") return;
    if (!isAuthenticated) {
      navigate({ to: "/admin/login", search: { redirect: path } });
      return;
    }
    if (!profileLoading && !isAdmin) {
      navigate({ to: "/" });
    }
  }, [isAuthenticated, profileLoading, isAdmin, path]);

  // Login page: public, no sidebar shell
  if (path === "/admin/login") {
    return <Outlet />;
  }

  // Block render while session/profile are being resolved
  if (!isAuthenticated || profileLoading || !profile || !isAdmin) {
    return (
      <div className="min-h-screen bg-secondary/40 flex items-center justify-center">
        <div className="size-8 border-2 border-foreground border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Authenticated admin — render the full shell
  return (
    <div className="min-h-screen bg-secondary/40 grid lg:grid-cols-[260px_1fr]">
      <aside className="bg-foreground text-background p-6 lg:min-h-screen flex flex-col">
        <Link to="/" className="flex items-center gap-3">
          <img src={markAsset} alt="Hadha" className="h-10 w-auto" />
          <span className="font-display text-2xl tracking-wide">Hadha</span>
        </Link>
        <p className="text-[10px] uppercase tracking-[0.3em] text-background/60 mt-1">Admin CMS</p>

        <nav className="mt-10 space-y-1 flex-1">
          {nav.map((n) => {
            const active = n.exact ? path === n.to : path.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={`flex items-center gap-3 px-4 py-2.5 text-sm transition ${
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-background/80 hover:bg-background/10"
                }`}
              >
                {n.icon}
                {n.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto pt-6 border-t border-background/10 space-y-2">
          <Link
            to="/"
            className="flex items-center gap-2 text-xs text-background/60 hover:text-background transition"
          >
            <ArrowLeft className="size-3.5" />
            Back to storefront
          </Link>
          <LogoutButton />
        </div>
      </aside>

      <main className="p-6 md:p-10">
        <Outlet />
      </main>
    </div>
  );
}

function LogoutButton() {
  const { logout } = useAuthContext();
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      await logout();
    } finally {
      navigate({ to: "/admin/login", search: { redirect: undefined } });
    }
  }

  return (
    <button
      onClick={handleLogout}
      className="flex items-center gap-2 text-xs text-background/60 hover:text-background transition w-full text-left"
    >
      <LogOut className="size-3.5" />
      Sign out
    </button>
  );
}
