import { memo } from "react";
import { Eye, Heart, ShoppingBag, Star, Bell, Clock } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { ResponsiveImage } from "@hadha/shared-media";
import type { Product } from "@/types/shop";
import { useCart } from "@/stores/cart";
import { useWishlist } from "@/stores/wishlist";
import { useActiveReservations } from "@/hooks/useActiveReservations";
import { formatINR } from "@/lib/format";
import { StockPill } from "@/components/site/InventoryBadge";

const CARD_IMAGE_SIZES = "(min-width: 1280px) 25vw, (min-width: 768px) 33vw, 50vw";

export const ProductCard = memo(function ProductCard({ p }: { p: Product }) {
  const add = useCart((s) => s.add);
  const toggleWishlist = useWishlist((s) => s.toggle);
  const wished = useWishlist((s) => s.items.some((i) => i.id === p.id));
  const { isReserved: hasReservation } = useActiveReservations();

  const isSoldOut = p.availableStock === 0;
  const reserved = isSoldOut && hasReservation(p.id);

  function handleAddToCart(e: React.MouseEvent) {
    e.preventDefault();
    if (isSoldOut && !reserved) return;
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
        className="block relative aspect-square bg-white overflow-hidden"
        aria-label={`View ${p.name}${isSoldOut && !reserved ? " — Sold Out" : reserved ? " — Reserved for You" : ""}`}
      >
        {p.imageBundle ? (
          <ResponsiveImage
            bundle={p.imageBundle}
            sizes={CARD_IMAGE_SIZES}
            className="w-full h-full"
            imgClassName={`w-full h-full object-contain transition-transform duration-500 ease-out group-hover:scale-105 ${isSoldOut && !reserved ? "opacity-60" : ""}`}
          />
        ) : (
          <img
            src={p.image}
            alt={p.name}
            loading="lazy"
            width={800}
            height={800}
            className={`w-full h-full object-contain transition-transform duration-500 ease-out group-hover:scale-105 ${isSoldOut && !reserved ? "opacity-60" : ""}`}
          />
        )}

        {/* Sold-out / Reserved overlay */}
        {isSoldOut && !reserved && (
          <div
            className="absolute inset-0 bg-background/40 flex items-center justify-center"
            aria-hidden
          >
            <span className="bg-foreground/80 text-background text-[10px] tracking-[0.28em] uppercase px-4 py-1.5">
              Sold Out
            </span>
          </div>
        )}
        {reserved && (
          <div
            className="absolute inset-0 bg-blue-500/10 flex items-center justify-center"
            aria-hidden
          >
            <span className="bg-blue-600/90 text-white text-[10px] tracking-[0.28em] uppercase px-4 py-1.5 flex items-center gap-1.5">
              <Clock className="size-3" />
              Reserved for You
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
        {reserved && <StockPill availableStock={0} isReserved />}

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
      </Link>

      {/* Add to Cart / Notify Me / Reserved — always visible below the image */}
      {isSoldOut && !reserved ? (
        <Link
          to="/products/$slug"
          params={{ slug: p.slug }}
          className="flex items-center justify-center gap-2 w-full bg-muted-foreground/80 text-background text-[11px] tracking-[0.24em] uppercase py-3.5 font-cinzel hover:bg-muted-foreground transition-colors"
          aria-label={`Notify me when ${p.name} is back in stock`}
        >
          <Bell className="size-3.5" /> Notify Me
        </Link>
      ) : reserved ? (
        <button
          onClick={handleAddToCart}
          className="flex items-center justify-center gap-2 w-full bg-blue-600 text-white text-[11px] tracking-[0.24em] uppercase py-3.5 font-cinzel hover:bg-blue-700 transition-colors"
          aria-label={`Add reserved ${p.name} to cart`}
        >
          <ShoppingBag className="size-3.5" /> Add Reserved to Cart
        </button>
      ) : (
        <button
          onClick={handleAddToCart}
          className="flex items-center justify-center gap-2 w-full bg-primary text-primary-foreground text-[11px] tracking-[0.24em] uppercase py-3.5 font-cinzel hover:bg-accent hover:text-accent-foreground transition-colors"
          aria-label={`Add ${p.name} to cart`}
        >
          <ShoppingBag className="size-3.5" /> Add to cart
        </button>
      )}

      <div className="pt-4 pb-2 px-1">
        {(p.reviewCount ?? 0) > 0 && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <div className="flex items-center gap-0.5">
              {Array.from({ length: 5 }).map((_, i) => (
                <Star
                  key={i}
                  className={`size-3 ${i < Math.round(p.rating ?? 0) ? "fill-accent text-accent" : "text-border"}`}
                />
              ))}
            </div>
            <span className="text-[11px] text-muted-foreground">{p.reviewCount}</span>
          </div>
        )}
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
            className={`font-sans font-bold text-base ${isSoldOut && !reserved ? "text-muted-foreground" : "text-foreground"}`}
          >
            {formatINR(p.price)}
          </span>
          {p.compareAt && !isSoldOut && (
            <span className="text-xs text-muted-foreground line-through">
              {formatINR(p.compareAt)}
            </span>
          )}
          {isSoldOut && !reserved && (
            <span className="text-[10px] uppercase tracking-[0.18em] text-destructive font-medium">
              Sold Out
            </span>
          )}
          {reserved && (
            <span className="text-[10px] uppercase tracking-[0.18em] text-blue-600 font-medium">
              Reserved
            </span>
          )}
        </div>
      </div>
    </article>
  );
});
