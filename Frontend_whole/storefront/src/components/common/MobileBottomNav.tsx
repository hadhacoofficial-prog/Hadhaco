import { Link, useRouterState } from "@tanstack/react-router";
import { Home, LayoutGrid, Search, Heart, User } from "lucide-react";
import { useWishlist } from "@/stores/wishlist";
import { useAuthContext } from "@/providers/auth-context";

export function MobileBottomNav() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const wishCount = useWishlist((s) => s.items.length);
  const { isAuthenticated: isAuthed } = useAuthContext();

  const items = [
    { to: "/", label: "Home", icon: Home, match: (p: string) => p === "/" },
    {
      to: "/collections",
      label: "Shop",
      icon: LayoutGrid,
      match: (p: string) => p.startsWith("/collections") || p.startsWith("/products"),
    },
    { to: "/search", label: "Search", icon: Search, match: (p: string) => p.startsWith("/search") },
    {
      to: "/wishlist",
      label: "Wishlist",
      icon: Heart,
      match: (p: string) => p.startsWith("/wishlist"),
      badge: wishCount,
    },
    {
      to: isAuthed ? "/account" : "/account/login",
      label: "Account",
      icon: User,
      match: (p: string) => p.startsWith("/account"),
    },
  ] as const;

  return (
    <nav
      aria-label="Primary mobile navigation"
      className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-background/95 backdrop-blur border-t border-border"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="grid grid-cols-5">
        {items.map((it) => {
          const active = it.match(path);
          const Icon = it.icon;
          return (
            <li key={it.label}>
              <Link
                to={it.to}
                className={`flex flex-col items-center justify-center gap-1 py-2.5 text-[10px] tracking-[0.14em] uppercase transition ${
                  active ? "text-primary" : "text-muted-foreground"
                }`}
              >
                <span className="relative">
                  <Icon className="size-5" />
                  {"badge" in it && it.badge ? (
                    <span className="absolute -top-1.5 -right-2 bg-accent text-accent-foreground text-[9px] font-medium rounded-full size-4 flex items-center justify-center">
                      {it.badge}
                    </span>
                  ) : null}
                </span>
                {it.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
