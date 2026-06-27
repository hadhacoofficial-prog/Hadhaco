import logoAsset from "@/assets/hadha-logo.png";
import markAsset from "@/assets/hadha-mark.png";
import { memo, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  Search,
  User,
  Heart,
  ShoppingBag,
  Menu,
  X,
  ChevronDown,
  Instagram,
  Youtube,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useUi } from "@/stores/ui";
import { useCart } from "@/stores/cart";
import { useWishlist } from "@/stores/wishlist";
import { useAuthContext } from "@/providers/auth-context";
import { useNavigationCategories } from "@/hooks/categories/useNavigationCategories";
import { useHomepage } from "@/hooks/cms/useHomepage";
import type { NavCategoryItem, NavigationCategoriesResponse } from "@/types/public";
import type { FooterConfig } from "@/types/cms";
import { NavJewelleryBg } from "./NavJewelleryBg";
import { NavJewelleryBgMobile } from "./NavJewelleryBgMobile";

// ─── Types ────────────────────────────────────────────────────────────────────

type NavGender = "women" | "men" | "unisex" | "kids";

interface GenderTab {
  key: NavGender;
  label: string;
}

// Fixed parent categories — always rendered even if no subcategories exist.
const GENDER_TABS: GenderTab[] = [
  { key: "women", label: "Shop Women" },
  { key: "men", label: "Shop Men" },
  { key: "unisex", label: "Shop Unisex" },
  { key: "kids", label: "Shop Kids" },
];

// ─── Header ───────────────────────────────────────────────────────────────────

export function Header() {
  const [openMega, setOpenMega] = useState<NavGender | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  const openSearch = useUi((s) => s.openSearch);
  const cartCount = useCart((s) => s.lines.reduce((n, l) => n + l.qty, 0));
  const openCart = useCart((s) => s.open);
  const wishCount = useWishlist((s) => s.items.length);
  const { isAuthenticated: isAuthed } = useAuthContext();

  const { data, isFetching, isError, isPlaceholderData } = useNavigationCategories();
  const categories = data ?? { women: [], men: [], unisex: [], kids: [] };

  const { data: homepage } = useHomepage();
  const footerConfig = (homepage?.sections["footer"]?.config ?? {}) as Partial<FooterConfig>;
  const instagramUrl = footerConfig.instagram ?? "#";
  const youtubeUrl = footerConfig.youtube ?? "#";

  // Show skeleton only on the very first fetch when no cached data exists yet.
  // Background refetches (after 24 h staleTime) show stale cached data instead.
  const isInitialLoading = isFetching && isPlaceholderData;

  // Close open mega menu on Escape
  const closeMega = useCallback(() => setOpenMega(null), []);
  useEffect(() => {
    if (!openMega) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeMega();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [openMega, closeMega]);

  return (
    <>
      <header className="sticky top-0 z-40 bg-background/95 backdrop-blur border-b border-border relative">
        {/* Jewellery background illustration */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
          <NavJewelleryBg />
        </div>

        {/* Utility bar */}
        <div className="relative z-10 hidden md:flex items-center px-8 py-2 text-[11px] tracking-[0.18em] uppercase text-muted-foreground">
          <div className="flex items-center gap-4">
            <a
              href={instagramUrl}
              target="_blank"
              rel="noreferrer"
              aria-label="Instagram"
              className="hover:text-foreground transition"
            >
              <Instagram className="size-3.5" />
            </a>
            <a
              href={youtubeUrl}
              target="_blank"
              rel="noreferrer"
              aria-label="YouTube"
              className="hover:text-foreground transition"
            >
              <Youtube className="size-3.5" />
            </a>
          </div>
          <p className="absolute left-1/2 -translate-x-1/2 text-foreground">
            The strong Decision · నిర్ణయం మీది నాణ్యత మాది
          </p>
        </div>

        {/* Main bar */}
        <div className="relative z-10 flex items-center justify-between px-4 md:px-8 py-4 border-t border-border/60">
          <button
            onClick={() => setMobileOpen(true)}
            className="lg:hidden p-2 -ml-2"
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>

          <Link to="/" className="flex items-center shrink-0" aria-label="Hadha Silver Jewellery">
            <img
              src={logoAsset}
              alt="Hadha Silver Jewellery"
              className="h-18 md:h-16 w-auto max-w-[260px] md:max-w-[340px] object-contain"
            />
          </Link>

          {/* Desktop nav */}
          <nav
            className="hidden lg:flex items-center gap-6 xl:gap-8 text-[12px] font-medium tracking-[0.16em] uppercase"
            aria-label="Primary navigation"
          >
            {GENDER_TABS.map(({ key, label }) => (
              <MegaItem
                key={key}
                gender={key}
                label={label}
                items={categories[key]}
                isLoading={isInitialLoading}
                isError={isError}
                openMega={openMega}
                setOpenMega={setOpenMega}
              />
            ))}

            {/* Deals — direct link, no dropdown */}
            <Link
              to="/products"
              search={{ deals: "true" }}
              className="hover:text-primary transition"
            >
              Deals
            </Link>

            {/* New Arrivals — direct link, no dropdown */}
            <Link
              to="/products"
              search={{ sort: "newest" }}
              className="hover:text-primary transition"
            >
              New Arrivals
            </Link>
          </nav>

          {/* Action icons */}
          <div className="flex items-center gap-3 md:gap-5">
            <button
              onClick={openSearch}
              aria-label="Search"
              className="hover:text-primary transition"
            >
              <Search className="size-5" />
            </button>
            <Link
              to={isAuthed ? "/account" : "/account/login"}
              aria-label="Account"
              className="hidden md:block hover:text-accent transition"
            >
              <User className="size-5" />
            </Link>
            <Link
              to="/wishlist"
              aria-label="Wishlist"
              className="hidden md:flex relative hover:text-accent transition"
            >
              <Heart className="size-5" />
              {wishCount > 0 && (
                <span className="absolute -top-1.5 -right-2 bg-accent text-accent-foreground text-[10px] font-medium rounded-full size-4 flex items-center justify-center">
                  {wishCount}
                </span>
              )}
            </Link>
            <button
              onClick={openCart}
              aria-label="Cart"
              className="relative hover:text-accent transition"
            >
              <ShoppingBag className="size-5" />
              {cartCount > 0 && (
                <span className="absolute -top-1.5 -right-2 bg-accent text-accent-foreground text-[10px] font-medium rounded-full size-4 flex items-center justify-center">
                  {cartCount}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Mobile-only tagline bar */}
      <div className="md:hidden bg-background border-b border-border px-4 py-2 text-center">
        <p className="text-[10px] tracking-[0.22em] uppercase text-muted-foreground">
          The strong Decision · నిర్ణయం మీది నాణ్యత మాది
        </p>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-[80] lg:hidden">
          <div
            className="absolute inset-0 bg-foreground/50 animate-fade-in"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <aside
            className="absolute left-0 top-0 h-dvh w-[85%] max-w-sm bg-background overflow-y-auto animate-slide-in-left shadow-2xl flex flex-col relative"
            aria-label="Mobile navigation"
          >
            <div
              className="absolute inset-0 overflow-hidden pointer-events-none"
              aria-hidden="true"
            >
              <NavJewelleryBgMobile />
            </div>
            <div className="relative z-10 flex justify-between items-center p-6 pb-0">
              <img src={markAsset} alt="Hadha" className="h-9 w-auto" />
              <button onClick={() => setMobileOpen(false)} aria-label="Close menu">
                <X className="size-5" />
              </button>
            </div>
            <div className="relative z-10 space-y-4 text-sm tracking-[0.14em] uppercase px-6 flex-1 pt-6">
              {GENDER_TABS.map(({ key, label }) => (
                <MobileAccordion
                  key={key}
                  gender={key}
                  label={label}
                  items={categories[key]}
                  isLoading={isInitialLoading}
                  isError={isError}
                  onClose={() => setMobileOpen(false)}
                />
              ))}
              <Link
                to="/products"
                search={{ deals: "true" }}
                onClick={() => setMobileOpen(false)}
                className="block border-b border-border pb-3"
              >
                Deals
              </Link>
              <Link
                to="/products"
                search={{ sort: "newest" }}
                onClick={() => setMobileOpen(false)}
                className="block border-b border-border pb-3"
              >
                New Arrivals
              </Link>
              <Link
                to="/wishlist"
                onClick={() => setMobileOpen(false)}
                className="block border-b border-border pb-3"
              >
                Wishlist
              </Link>
              <Link
                to="/account"
                onClick={() => setMobileOpen(false)}
                className="block border-b border-border pb-3"
              >
                Account
              </Link>
            </div>
            <div className="relative z-10 mt-10 px-6 pb-8 pt-6 border-t border-border flex flex-col items-center gap-2 text-center">
              <img src={logoAsset} alt="Hadha" className="h-16 w-24 opacity-90" />
              <p className="text-[10px] tracking-[0.32em] uppercase text-muted-foreground">
                Since 2025
              </p>
              <p className="text-[10px] tracking-[0.32em] uppercase text-muted-foreground">
                The strong Decision
              </p>
              <p className="text-[10px] tracking-[0.32em] uppercase text-muted-foreground">
                నిర్ణయం మీది నాణ్యత మాది
              </p>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

// ─── Desktop mega-menu item ───────────────────────────────────────────────────

interface MegaItemProps {
  gender: NavGender;
  label: string;
  items: NavCategoryItem[];
  isLoading: boolean;
  isError: boolean;
  openMega: NavGender | null;
  setOpenMega: (v: NavGender | null) => void;
}

const MegaItem = memo(function MegaItem({
  gender,
  label,
  items,
  isLoading,
  isError,
  openMega,
  setOpenMega,
}: MegaItemProps) {
  const open = openMega === gender;
  const dropdownId = `mega-${gender}`;
  const triggerRef = useRef<HTMLAnchorElement>(null);

  return (
    <div
      onMouseEnter={() => setOpenMega(gender)}
      onMouseLeave={() => setOpenMega(null)}
      onFocus={() => setOpenMega(gender)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setOpenMega(null);
        }
      }}
      className="relative py-2"
    >
      {/* Clicking the label navigates to /products?gender=<gender> */}
      <Link
        ref={triggerRef}
        to="/products"
        search={{ gender }}
        className="flex items-center gap-1 hover:text-primary transition"
        aria-expanded={open}
        aria-haspopup="true"
        aria-controls={dropdownId}
      >
        {label}
        <ChevronDown
          className={`size-3 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </Link>

      {open && (
        <div
          id={dropdownId}
          role="region"
          aria-label={`${label} categories`}
          className="absolute left-1/2 -translate-x-1/2 top-full pt-3 z-50"
        >
          <div className="bg-background border border-border shadow-[0_24px_60px_-30px_rgba(17,24,39,0.35)] w-[560px] p-8 animate-fade-in">
            <p className="text-[10px] tracking-[0.32em] uppercase text-muted-foreground pb-3 border-b border-border mb-3">
              {label}
            </p>

            {isLoading ? (
              <MegaMenuSkeleton />
            ) : isError ? (
              <p className="text-[12px] text-muted-foreground tracking-normal normal-case">
                Categories unavailable
              </p>
            ) : items.length === 0 ? (
              <p className="text-[12px] text-muted-foreground tracking-normal normal-case">
                No categories available
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-x-8 gap-y-1">
                {items.map((cat) => (
                  <Link
                    key={cat.id}
                    to="/products"
                    search={{ gender, category: cat.slug }}
                    className="text-[12px] tracking-[0.18em] uppercase text-foreground/80 hover:text-primary hover:translate-x-1 transition py-2"
                  >
                    {cat.name}
                  </Link>
                ))}
              </div>
            )}

            <Link
              to="/products"
              search={{ gender }}
              className="block mt-4 pt-4 border-t border-border text-[11px] tracking-[0.24em] uppercase text-primary hover:underline"
            >
              View all {label.toLowerCase()} →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
});

// ─── Mobile accordion item ────────────────────────────────────────────────────

interface MobileAccordionProps {
  gender: NavGender;
  label: string;
  items: NavCategoryItem[];
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
}

const MobileAccordion = memo(function MobileAccordion({
  gender,
  label,
  items,
  isLoading,
  isError,
  onClose,
}: MobileAccordionProps) {
  return (
    <details className="border-b border-border pb-3">
      <summary className="flex justify-between cursor-pointer py-1 list-none">
        <span>{label}</span>
        <ChevronDown className="size-4" aria-hidden="true" />
      </summary>
      <div className="pt-3 pl-2 space-y-2 normal-case tracking-normal">
        {isLoading ? (
          <>
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-28" />
          </>
        ) : isError ? (
          <p className="text-foreground/50 text-xs">Unavailable</p>
        ) : items.length === 0 ? (
          <p className="text-foreground/50 text-xs">No categories available</p>
        ) : (
          items.map((cat) => (
            <Link
              key={cat.id}
              to="/products"
              search={{ gender, category: cat.slug }}
              onClick={onClose}
              className="block text-foreground/80 hover:text-primary"
            >
              {cat.name}
            </Link>
          ))
        )}
        <Link
          to="/products"
          search={{ gender }}
          onClick={onClose}
          className="block text-primary text-xs mt-1"
        >
          View all →
        </Link>
      </div>
    </details>
  );
});

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function MegaMenuSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-x-8 gap-y-3">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-4 w-24" />
      ))}
    </div>
  );
}
