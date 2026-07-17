import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useNavigationCategories } from "@/hooks/categories/useNavigationCategories";
import { Skeleton } from "@/components/ui/skeleton";
import defaultCategoryImage from "@/assets/p3.jpg";

const DEFAULT_CATEGORY_IMAGE = defaultCategoryImage;

type Gender = "women" | "men" | "unisex" | "kids";
const GENDER_KEYS: Gender[] = ["women", "men", "unisex", "kids"];

export function ShopByGender() {
  const [active, setActive] = useState<Gender>("women");
  const { data, isLoading } = useNavigationCategories();

  const categories = data?.[active] ?? [];
  const activeLabel = data?.gender_meta?.[active]?.name ?? active;

  // Build sorted tab list from backend gender_meta; fall back to fixed order
  const tabs = GENDER_KEYS.map((key) => ({
    id: key,
    label: data?.gender_meta?.[key]?.name ?? key.charAt(0).toUpperCase() + key.slice(1),
    image_url: data?.gender_meta?.[key]?.image_url ?? null,
    sort_order: data?.gender_meta?.[key]?.sort_order ?? GENDER_KEYS.indexOf(key),
  })).sort((a, b) => a.sort_order - b.sort_order);

  return (
    <section className="relative px-4 md:px-12 py-20 md:py-28 overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_0%,oklch(0.94_0.012_80)_0%,transparent_60%),radial-gradient(ellipse_60%_50%_at_50%_100%,oklch(0.92_0.015_80)_0%,transparent_70%)]" />
      <div className="relative">
        {/* Gender selector circles — always exactly 4 across, even on
            mobile, rather than wrapping to 2x2 (which forced the circles
            larger than the row could comfortably hold two of). */}
        <div className="grid grid-cols-4 gap-2 sm:gap-4 md:gap-16 justify-items-center mb-14">
          {isLoading
            ? GENDER_KEYS.map((k) => (
                <div key={k} className="flex flex-col items-center gap-2 md:gap-3">
                  <Skeleton className="size-16 sm:size-24 md:size-56 rounded-full" />
                  <Skeleton className="h-3 w-12 md:w-16" />
                </div>
              ))
            : tabs.map((t) => {
                const isActive = active === t.id;
                return (
                  <button
                    key={t.id}
                    onMouseEnter={() => setActive(t.id)}
                    onClick={() => setActive(t.id)}
                    className="group flex flex-col items-center gap-2 md:gap-3"
                  >
                    <motion.span
                      whileHover={{ scale: 1.04 }}
                      transition={{ type: "spring", stiffness: 220, damping: 18 }}
                      className={`relative size-16 sm:size-24 md:size-56 rounded-full overflow-hidden transition-shadow duration-500 ${
                        isActive
                          ? "ring-2 ring-primary ring-offset-2 md:ring-offset-4 ring-offset-background shadow-[0_24px_60px_-24px_oklch(0.32_0.055_258/0.55)]"
                          : "ring-1 ring-border ring-offset-1 md:ring-offset-2 ring-offset-background opacity-75 hover:opacity-100"
                      }`}
                    >
                      <img
                        src={t.image_url ?? DEFAULT_CATEGORY_IMAGE}
                        alt={t.label}
                        loading="lazy"
                        className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                        onError={(e) => {
                          e.currentTarget.src = DEFAULT_CATEGORY_IMAGE;
                        }}
                      />
                      <span
                        className={`absolute inset-0 transition-colors ${isActive ? "bg-primary/10" : "bg-foreground/10 group-hover:bg-foreground/0"}`}
                      />
                    </motion.span>
                    <span
                      className={`font-cinzel text-[9px] sm:text-xs md:text-base tracking-[0.14em] md:tracking-[0.24em] uppercase text-center transition-colors ${isActive ? "text-primary" : "text-foreground/70"}`}
                    >
                      {t.label}
                    </span>
                  </button>
                );
              })}
        </div>

        {/* Sub-category cards */}
        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 md:gap-7 max-w-6xl mx-auto"
          >
            {isLoading
              ? Array.from({ length: 9 }).map((_, i) => (
                  <Skeleton key={i} className="aspect-[4/5] w-full" />
                ))
              : categories.map((cat, i) => (
                  <motion.div
                    key={cat.id}
                    initial={{ opacity: 0, y: 24 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.55, delay: i * 0.06, ease: [0.2, 0.7, 0.2, 1] }}
                  >
                    <Link
                      to="/products"
                      search={{ gender: active, category: cat.slug }}
                      className="group relative block overflow-hidden bg-card border border-border hover:border-primary/40 transition-all duration-500 hover:-translate-y-1.5 hover:shadow-[0_30px_60px_-30px_oklch(0.27_0.025_258/0.45)]"
                    >
                      <div className="relative aspect-[4/5] overflow-hidden">
                        <img
                          src={cat.image_url ?? DEFAULT_CATEGORY_IMAGE}
                          alt={cat.name}
                          loading="lazy"
                          className="absolute inset-0 w-full h-full object-cover transition-transform duration-[1400ms] ease-out group-hover:scale-110"
                          onError={(e) => {
                            e.currentTarget.src = DEFAULT_CATEGORY_IMAGE;
                          }}
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-foreground/85 via-foreground/25 to-transparent" />
                        <div className="absolute inset-x-0 bottom-0 p-6 md:p-7 text-background">
                          <p className="text-[10px] tracking-[0.32em] uppercase text-accent mb-2 font-cinzel">
                            {activeLabel}
                          </p>
                          <h3 className="font-cinzel text-2xl md:text-3xl mb-3">{cat.name}</h3>
                          <span className="inline-flex items-center gap-2 text-[11px] tracking-[0.28em] uppercase border-b border-background/60 pb-1 group-hover:border-accent group-hover:text-accent transition-all">
                            Shop now
                            <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                          </span>
                        </div>
                      </div>
                    </Link>
                  </motion.div>
                ))}
          </motion.div>
        </AnimatePresence>

        <div className="mt-12 text-center">
          <Link
            to="/products"
            search={{ gender: active }}
            className="inline-flex items-center gap-2 text-xs tracking-[0.24em] uppercase border-b border-primary text-primary pb-1 hover:gap-3 transition-all"
          >
            View all {activeLabel.toLowerCase()} jewellery <ArrowUpRight className="size-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}
