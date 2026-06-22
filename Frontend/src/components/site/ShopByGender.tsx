import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useNavigationCategories } from "@/hooks/categories/useNavigationCategories";
import { Skeleton } from "@/components/ui/skeleton";
import men from "@/assets/p1.jpg";
import women from "@/assets/cat-bugadi.jpg";
import unisex from "@/assets/p3.jpg";
import kids from "@/assets/cat-bracelets.jpg";
import fallback from "@/assets/p2.jpg";

type Gender = "women" | "men" | "unisex" | "kids";

const TABS: { id: Gender; label: string; image: string }[] = [
  { id: "women",  label: "Women",  image: women  },
  { id: "men",    label: "Men",    image: men    },
  { id: "unisex", label: "Unisex", image: unisex },
  { id: "kids",   label: "Kids",   image: kids   },
];

export function ShopByGender() {
  const [active, setActive] = useState<Gender>("women");
  const { data, isLoading } = useNavigationCategories();
  const categories = data?.[active] ?? [];
  const activeLabel = TABS.find((t) => t.id === active)!.label;

  return (
    <section className="relative px-4 md:px-12 py-20 md:py-28 overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_0%,oklch(0.94_0.012_80)_0%,transparent_60%),radial-gradient(ellipse_60%_50%_at_50%_100%,oklch(0.92_0.015_80)_0%,transparent_70%)]" />
      <div className="relative">
        <div className="text-center mb-12 md:mb-14">
          <p className="text-[11px] tracking-[0.32em] uppercase text-accent mb-3 font-cinzel">
            Shop by Collection
          </p>
          <h2 className="font-cinzel text-3xl md:text-5xl">Crafted for everyone in your story.</h2>
          <p className="mt-4 text-muted-foreground max-w-xl mx-auto font-cormorant text-lg md:text-xl">
            Choose a chapter — silver pieces designed for women, men, unisex and little ones.
          </p>
        </div>

        <div className="flex items-center justify-center gap-6 md:gap-14 mb-14 flex-wrap">
          {TABS.map((t) => {
            const isActive = active === t.id;
            return (
              <button
                key={t.id}
                onMouseEnter={() => setActive(t.id)}
                onClick={() => setActive(t.id)}
                className="group flex flex-col items-center gap-3"
              >
                <motion.span
                  whileHover={{ scale: 1.04 }}
                  transition={{ type: "spring", stiffness: 220, damping: 18 }}
                  className={`relative size-24 md:size-44 rounded-full overflow-hidden transition-shadow duration-500 ${
                    isActive
                      ? "ring-2 ring-primary ring-offset-4 ring-offset-background shadow-[0_24px_60px_-24px_oklch(0.32_0.055_258/0.55)]"
                      : "ring-1 ring-border ring-offset-2 ring-offset-background opacity-75 hover:opacity-100"
                  }`}
                >
                  <img
                    src={t.image}
                    alt={t.label}
                    className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                  />
                  <span
                    className={`absolute inset-0 transition-colors ${isActive ? "bg-primary/10" : "bg-foreground/10 group-hover:bg-foreground/0"}`}
                  />
                </motion.span>
                <span
                  className={`font-cinzel text-xs md:text-base tracking-[0.24em] uppercase transition-colors ${isActive ? "text-primary" : "text-foreground/70"}`}
                >
                  {t.label}
                </span>
              </button>
            );
          })}
        </div>

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
                          src={cat.image_url ?? fallback}
                          alt={cat.name}
                          loading="lazy"
                          className="absolute inset-0 w-full h-full object-cover transition-transform duration-[1400ms] ease-out group-hover:scale-110"
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
            View all {active} jewellery <ArrowUpRight className="size-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}
