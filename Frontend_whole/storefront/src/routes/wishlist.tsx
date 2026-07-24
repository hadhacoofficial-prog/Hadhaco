import { useEffect } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueries } from "@tanstack/react-query";
import { Heart, Trash2, ShoppingBag, Bell } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { EmptyState } from "@/components/site/EmptyState";
import { StockPill } from "@/components/site/InventoryBadge";
import { useWishlist } from "@/stores/wishlist";
import { useCart } from "@/stores/cart";
import { useInventoryStore, inventoryKey } from "@/stores/inventory";
import { hydrateInventoryFromProduct } from "@/hooks/inventory/hydrateInventory";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { formatINR } from "@/lib/format";
import type { WishlistItem } from "@/stores/wishlist";
import type { ProductDetail } from "@/types/public";

export const Route = createFileRoute("/wishlist")({
  head: () => ({ meta: [{ title: "Wishlist · Hadha" }] }),
  component: WishlistPage,
});

function WishlistPage() {
  const items = useWishlist((s) => s.items);
  const remove = useWishlist((s) => s.remove);
  const addToCart = useCart((s) => s.add);

  // Wishlist items only carry id/slug/name/image/price/sku (no stock) — fetch
  // each one's current detail so this page can show real availability
  // instead of an always-enabled "Move to Cart" regardless of stock.
  const stockQueries = useQueries({
    queries: items.map((item) => ({
      queryKey: queryKeys.products.stock(item.slug),
      queryFn: () => api.get<ProductDetail>(`/products/${item.slug}`),
      staleTime: 30_000,
      refetchInterval: 60_000,
      refetchOnWindowFocus: true,
    })),
  });

  useEffect(() => {
    for (const q of stockQueries) {
      if (q.data) hydrateInventoryFromProduct(q.data);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stockQueries.map((q) => q.dataUpdatedAt).join(",")]);

  const inventoryEntries = useInventoryStore((s) => s.entries);

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Wishlist" }]} />
        <header className="text-center my-10">
          <h1 className="font-display text-4xl md:text-5xl">Your Wishlist</h1>
          <p className="text-sm text-muted-foreground mt-2">
            {items.length} {items.length === 1 ? "piece" : "pieces"} saved for later
          </p>
        </header>

        {items.length === 0 ? (
          <EmptyState
            icon={<Heart className="size-5" />}
            title="Your wishlist is empty"
            description="Save your favourite pieces here as you browse."
            action={
              <Link
                to="/collections"
                className="inline-block bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
              >
                Explore Collections
              </Link>
            }
          />
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-5 gap-y-10">
            {items.map((item: WishlistItem) => {
              const entry = inventoryEntries[inventoryKey(item.id, null)];
              const isSoldOut = entry?.availableStock === 0;
              return (
                <article key={item.id} className="group">
                  <Link
                    to="/products/$slug"
                    params={{ slug: item.slug }}
                    className="block relative aspect-square bg-secondary overflow-hidden"
                  >
                    <img
                      src={item.image}
                      alt={item.name}
                      className={`w-full h-full object-cover transition-transform duration-700 group-hover:scale-105 ${isSoldOut ? "opacity-60" : ""}`}
                    />
                    {entry && !isSoldOut && <StockPill availableStock={entry.availableStock} />}
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
                  </Link>
                  <h3 className="text-sm leading-snug line-clamp-2 mt-4 min-h-[2.5rem]">
                    <Link
                      to="/products/$slug"
                      params={{ slug: item.slug }}
                      className="hover:text-accent"
                    >
                      {item.name}
                    </Link>
                  </h3>
                  <div className="font-sans font-bold mt-1">{formatINR(item.price)}</div>
                  <div className="grid grid-cols-[1fr_auto] gap-2 mt-3">
                    {isSoldOut ? (
                      <Link
                        to="/products/$slug"
                        params={{ slug: item.slug }}
                        className="bg-muted-foreground/80 text-background text-[10px] tracking-[0.22em] uppercase py-2.5 flex items-center justify-center gap-1.5"
                      >
                        <Bell className="size-3" /> Notify Me
                      </Link>
                    ) : (
                      <button
                        onClick={() => {
                          addToCart(item.id, 1, {
                            name: item.name,
                            image: item.image,
                            slug: item.slug,
                            sku: item.sku,
                            price: item.price,
                          });
                          remove(item.id);
                        }}
                        className="bg-primary text-primary-foreground text-[10px] tracking-[0.22em] uppercase py-2.5 flex items-center justify-center gap-1.5"
                      >
                        <ShoppingBag className="size-3" /> Move to Cart
                      </button>
                    )}
                    <button
                      onClick={() => remove(item.id)}
                      aria-label="Remove"
                      className="border border-border size-9 flex items-center justify-center hover:bg-secondary"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </SiteLayout>
  );
}
