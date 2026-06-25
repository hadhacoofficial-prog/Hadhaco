import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { Sparkles, ShieldCheck, Heart, Award } from "lucide-react";
import banner from "@/assets/banner.jpg";
import hero from "@/assets/hero.jpg";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "Our Story · Hadha Silver Jewellery" },
      {
        name: "description",
        content:
          "Handcrafted 92.5 sterling silver jewellery from our Visakhapatnam atelier — designed for everyday, made to last a lifetime.",
      },
      { property: "og:title", content: "Our Story · Hadha" },
    ],
  }),
  component: AboutPage,
});

function AboutPage() {
  return (
    <SiteLayout>
      <div className="px-4 md:px-8 pt-8">
        <div className="max-w-6xl mx-auto">
          <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Our Story" }]} />
        </div>
      </div>

      <section className="relative h-[55vh] min-h-[420px] mt-6 overflow-hidden">
        <img
          src={banner}
          alt="Hadha atelier"
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-foreground/40" />
        <div className="relative h-full flex flex-col items-center justify-center text-center text-background px-4">
          <p className="text-[11px] uppercase tracking-[0.3em]">Est. Visakhapatnam · India</p>
          <h1 className="font-display text-5xl md:text-7xl mt-3">Our Story</h1>
          <p className="mt-4 max-w-xl text-sm md:text-base text-background/85">
            Honest silver, handcrafted with love — designed to be worn every day, and treasured for
            a lifetime.
          </p>
        </div>
      </section>

      <section className="px-4 md:px-8 py-20 max-w-4xl mx-auto text-center">
        <p className="text-[11px] uppercase tracking-[0.3em] text-accent">The Beginning</p>
        <h2 className="font-display text-3xl md:text-4xl mt-3">A Promise Cast in Silver</h2>
        <p className="mt-6 text-muted-foreground leading-relaxed">
          Hadha was born from a simple promise — to make sterling silver jewellery that feels
          personal, honest and timeless. Every piece is hallmarked, hand-finished and made to live
          with you. From the temple-inspired bugadi to delicate everyday chains, our pieces are
          designed in-house and crafted by master karigars at our atelier in Visakhapatnam.
        </p>
      </section>

      <section className="px-4 md:px-8 pb-20 max-w-6xl mx-auto grid md:grid-cols-2 gap-10 items-center">
        <img src={hero} alt="Atelier" className="aspect-[4/5] w-full object-cover" />
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-accent">Craft</p>
          <h2 className="font-display text-3xl md:text-4xl mt-3">
            Made in Visakhapatnam, Made for India
          </h2>
          <p className="mt-5 text-muted-foreground leading-relaxed">
            We use only 92.5 sterling silver, BIS-hallmarked and finished with anti-tarnish coating.
            Each piece is checked by hand at every stage — from casting to polish — and presented in
            a signature Hadha gift box.
          </p>
          <div className="grid grid-cols-2 gap-4 mt-8">
            {[
              {
                icon: <ShieldCheck className="size-5" />,
                t: "BIS Hallmarked",
                s: "Certified 92.5 purity",
              },
              { icon: <Sparkles className="size-5" />, t: "Anti-Tarnish", s: "Lasting brilliance" },
              { icon: <Heart className="size-5" />, t: "Handcrafted", s: "By master karigars" },
              {
                icon: <Award className="size-5" />,
                t: "Lifetime Buyback",
                s: "On every Hadha piece",
              },
            ].map((f) => (
              <div key={f.t} className="border border-border p-4">
                <span className="text-accent">{f.icon}</span>
                <p className="font-display mt-2">{f.t}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{f.s}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-secondary px-4 md:px-8 py-20 text-center">
        <p className="text-[11px] uppercase tracking-[0.3em] text-accent">Visit</p>
        <h2 className="font-display text-3xl md:text-4xl mt-3">Come see us in person</h2>
        <p className="mt-4 text-sm text-muted-foreground max-w-md mx-auto">
          Step into our flagship atelier in MVP Colony, Visakhapatnam — and try on our entire
          collection.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link
            to="/store-locator"
            className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
          >
            Find a Store
          </Link>
          <Link
            to="/contact"
            className="border border-foreground text-[11px] uppercase tracking-[0.22em] px-6 py-3"
          >
            Contact Us
          </Link>
        </div>
      </section>
    </SiteLayout>
  );
}
