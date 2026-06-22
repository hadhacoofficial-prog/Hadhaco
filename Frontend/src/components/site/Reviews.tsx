import { Star, Quote } from "lucide-react";
import type { Review } from "@/types/shop";

const TESTIMONIALS: Review[] = [
  {
    id: "t1",
    productId: "",
    name: "Priya S.",
    text: "The sterling silver anklet I ordered arrived beautifully packaged. The craftsmanship is exquisite — I've received so many compliments.",
    rating: 5,
    createdAt: "2024-11-15",
  },
  {
    id: "t2",
    productId: "",
    name: "Ananya R.",
    text: "I've been buying jewellery for years and Hadha's quality is truly outstanding. My oxidised silver necklace is stunning.",
    rating: 5,
    createdAt: "2024-12-02",
  },
  {
    id: "t3",
    productId: "",
    name: "Meera K.",
    text: "Fast shipping, gorgeous packaging, and the ring fits perfectly. Will definitely be ordering again for Diwali gifts.",
    rating: 5,
    createdAt: "2025-01-08",
  },
  {
    id: "t4",
    productId: "",
    name: "Divya T.",
    text: "Hadha has become my go-to for silver jewellery. The BIS hallmark gives me complete confidence in the quality.",
    rating: 5,
    createdAt: "2025-02-14",
  },
];

export function Reviews() {
  return (
    <section className="px-4 md:px-12 py-20 md:py-28">
      <div className="text-center mb-12">
        <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-3">
          Loved by customers
        </p>
        <h2 className="font-display text-4xl md:text-5xl">Stories from our family.</h2>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5 md:gap-6">
        {TESTIMONIALS.map((r) => (
          <figure key={r.id} className="bg-card border border-border p-7 relative">
            <Quote className="size-6 text-accent mb-4" />
            <blockquote className="text-foreground/85 leading-relaxed">"{r.text}"</blockquote>
            <figcaption className="mt-5 flex items-center justify-between">
              <span className="font-display text-lg">— {r.name}</span>
              <span className="flex items-center gap-0.5">
                {Array.from({ length: r.rating }).map((_, i) => (
                  <Star key={i} className="size-3.5 fill-accent text-accent" />
                ))}
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
