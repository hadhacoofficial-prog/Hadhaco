import { Eye, Heart, ShoppingBag, Star, Bell } from "lucide-react";
import { Link } from "@tanstack/react-router";
import type { Product } from "@/types/shop";
import { useCart } from "@/stores/cart";
import { useWishlist } from "@/stores/wishlist";
import { formatINR } from "@/lib/format";
import { StockPill } from "@/components/site/InventoryBadge";

export function ProductCard({ p }: { p: Product }) {
  const add = useCart((s) => s.add);
  const toggleWishlist = useWishlist((s) => s.toggle);
  const wished = useWishlist((s) => s.items.some((i) => i.id === p.id));

  const isSoldOut = p.availableStock === 0;

  function handleAddToCart(e: React.MouseEvent) {
    e.preventDefault();
    if (isSoldOut) return;
    add(p.id, 1, {
      name: p.name,
      image: p.image,
      slug: p.slug,
      sku: p.sku,
      price: p.price,
    });
  }

  return (
    <article className="group relative hover-lift">
      <Link
        to="/products/$slug"
        params={{ slug: p.slug }}
        className="block relative aspect-square overflow-hidden bg-muted"
        aria-label={`View ${p.name}${isSoldOut ? " — Sold Out" : ""}`}
      >
        <img
          src={p.image}
          alt={p.name}
          loading="lazy"
          width={800}
          height={800}
          className={`absolute inset-0 w-full h-full object-cover transition-all duration-[900ms] ease-out group-hover:scale-110 group-hover:opacity-0 ${isSoldOut ? "opacity-60" : ""}`}
        />
        <img
          src={p.altImage ?? p.image}
          alt=""
          aria-hidden
          loading="lazy"
          width={800}
          height={800}
          className={`absolute inset-0 w-full h-full object-cover opacity-0 transition-all duration-[900ms] ease-out group-hover:opacity-100 scale-105 group-hover:scale-110 ${isSoldOut ? "opacity-60" : ""}`}
        />

        {/* Sold-out overlay */}
        {isSoldOut && (
          <div
            className="absolute inset-0 bg-background/40 flex items-center justify-center"
            aria-hidden
          >
            <span className="bg-foreground/80 text-background text-[10px] tracking-[0.28em] uppercase px-4 py-1.5">
              Sold Out
            </span>
          </div>
        )}

        <div className="absolute inset-0 bg-gradient-to-t from-foreground/15 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

        {p.badge && !isSoldOut && (
          <span className="absolute top-3 left-3 bg-primary text-primary-foreground text-[10px] tracking-[0.22em] uppercase px-2.5 py-1 font-cinzel shadow-sm">
            {p.badge}
          </span>
        )}

        {/* Stock pill (only when not sold out — sold-out overlay covers it) */}
        {!isSoldOut && <StockPill availableStock={p.availableStock} />}

        <div className="absolute top-3 right-3 flex flex-col gap-2">
          <button
            aria-label={wished ? `Remove ${p.name} from wishlist` : `Add ${p.name} to wishlist`}
            onClick={(e) => {
              e.preventDefault();
              toggleWishlist({
                id: p.id,
                slug: p.slug,
                name: p.name,
                image: p.image,
                price: p.price,
                sku: p.sku,
              });
            }}
            className={`size-9 rounded-full bg-background/90 backdrop-blur flex items-center justify-center transition-all hover:text-accent shadow-sm ${wished ? "opacity-100 text-accent" : "opacity-0 -translate-y-1 group-hover:opacity-100 group-hover:translate-y-0"}`}
          >
            <Heart className={`size-4 ${wished ? "fill-accent" : ""}`} />
          </button>
          <span
            aria-hidden
            className="size-9 rounded-full bg-background/90 backdrop-blur flex items-center justify-center opacity-0 -translate-y-1 group-hover:opacity-100 group-hover:translate-y-0 transition-all delay-75 shadow-sm hover:text-primary"
          >
            <Eye className="size-4" />
          </span>
        </div>

        {/* Add to cart / Notify Me */}
        {isSoldOut ? (
          <Link
            to="/products/$slug"
            params={{ slug: p.slug }}
            onClick={(e) => e.stopPropagation()}
            className="absolute bottom-0 left-0 right-0 bg-muted-foreground/80 text-background text-[11px] tracking-[0.24em] uppercase py-3.5 flex items-center justify-center gap-2 translate-y-full group-hover:translate-y-0 transition-transform duration-500 font-cinzel"
            aria-label={`Notify me when ${p.name} is back in stock`}
          >
            <Bell className="size-3.5" /> Notify Me
          </Link>
        ) : (
          <button
            onClick={handleAddToCart}
            className="absolute bottom-0 left-0 right-0 bg-primary text-primary-foreground text-[11px] tracking-[0.24em] uppercase py-3.5 flex items-center justify-center gap-2 translate-y-full group-hover:translate-y-0 transition-transform duration-500 font-cinzel"
            aria-label={`Add ${p.name} to cart`}
          >
            <ShoppingBag className="size-3.5" /> Add to cart
          </button>
        )}
      </Link>

      <div className="pt-4 pb-2 px-1">
        <div className="flex items-center gap-0.5 mb-1.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Star
              key={i}
              className={`size-3 ${i < (p.rating ?? 5) ? "fill-accent text-accent" : "text-border"}`}
            />
          ))}
        </div>
        <h3 className="text-sm leading-snug line-clamp-2 min-h-[2.5rem] font-medium">
          <Link
            to="/products/$slug"
            params={{ slug: p.slug }}
            className="hover:text-primary transition-colors"
          >
            {p.name}
          </Link>
        </h3>
        <div className="mt-2 flex items-baseline gap-2">
          <span
            className={`font-cinzel text-base ${isSoldOut ? "text-muted-foreground" : "text-foreground"}`}
          >
            {formatINR(p.price)}
          </span>
          {p.compareAt && !isSoldOut && (
            <span className="text-xs text-muted-foreground line-through">
              {formatINR(p.compareAt)}
            </span>
          )}
          {isSoldOut && (
            <span className="text-[10px] uppercase tracking-[0.18em] text-destructive font-medium">
              Sold Out
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
