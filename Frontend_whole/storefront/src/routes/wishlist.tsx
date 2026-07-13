import { createFileRoute, Link } from "@tanstack/react-router";
import { Heart, Trash2, ShoppingBag } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { EmptyState } from "@/components/site/EmptyState";
import { useWishlist } from "@/stores/wishlist";
import { useCart } from "@/stores/cart";
import { formatINR } from "@/lib/format";
import type { WishlistItem } from "@/stores/wishlist";

export const Route = createFileRoute("/wishlist")({
  head: () => ({ meta: [{ title: "Wishlist · Hadha" }] }),
  component: WishlistPage,
});

function WishlistPage() {
  const items = useWishlist((s) => s.items);
  const remove = useWishlist((s) => s.remove);
  const addToCart = useCart((s) => s.add);

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
            {items.map((item: WishlistItem) => (
              <article key={item.id} className="group">
                <Link
                  to="/products/$slug"
                  params={{ slug: item.slug }}
                  className="block aspect-square bg-secondary overflow-hidden"
                >
                  <img
                    src={item.image}
                    alt={item.name}
                    className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                  />
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
                  <button
                    onClick={() => remove(item.id)}
                    aria-label="Remove"
                    className="border border-border size-9 flex items-center justify-center hover:bg-secondary"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </SiteLayout>
  );
}
