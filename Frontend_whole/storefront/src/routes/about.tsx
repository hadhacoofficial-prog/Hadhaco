import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { Sparkles, ShieldCheck, Heart, Award, ArrowUpRight } from "lucide-react";
import banner from "@/assets/banner.jpg";
import hero from "@/assets/hero.jpg";
import { usePublicCompanyConfig } from "@/hooks/company/useCompanyConfig";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "Our Story · Hadha Silver Jewellery" },
      {
        name: "description",
        content:
          "Handcrafted 92.5 sterling silver jewellery — designed for everyday, made to last a lifetime.",
      },
      { property: "og:title", content: "Our Story · Hadha" },
    ],
  }),
  component: AboutPage,
});

function AboutPage() {
  const { data: config } = usePublicCompanyConfig();
  const companyName = config?.brand_name || config?.name || "Hadha";
  const city = config?.city || "Visakhapatnam";
  const country = config?.country === "IN" ? "India" : config?.country || "India";
  const addressLine1 = config?.address_line_1 || "MVP Colony";

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
          alt={`${companyName} atelier`}
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-foreground/40" />
        <div className="relative h-full flex flex-col items-center justify-center text-center text-background px-4">
          <p className="text-[11px] uppercase tracking-[0.3em]">
            Est. {city} · {country}
          </p>
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
          {companyName} was born from a simple promise — to make sterling silver jewellery that
          feels personal, honest and timeless. Every piece is hallmarked, hand-finished and made to
          live with you. From the temple-inspired bugadi to delicate everyday chains, our pieces are
          designed in-house and crafted by master karigars at our atelier in {city}.
        </p>
      </section>

      <section className="px-4 md:px-8 pb-20 max-w-6xl mx-auto grid md:grid-cols-2 gap-10 items-center">
        <img
          src={hero}
          alt="Atelier"
          loading="lazy"
          decoding="async"
          className="aspect-[4/5] w-full object-cover"
        />
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-accent">Craft</p>
          <h2 className="font-display text-3xl md:text-4xl mt-3">
            Made in {city}, Made for {country}
          </h2>
          <p className="mt-5 text-muted-foreground leading-relaxed">
            We use only 92.5 sterling silver, BIS-hallmarked and finished with anti-tarnish coating.
            Each piece is checked by hand at every stage — from casting to polish — and presented in
            a signature {companyName} gift box.
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
                s: `On every ${companyName} piece`,
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
          {`Step into our flagship atelier in ${addressLine1}, ${city} — and try on our entire collection.`}
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

      {/* Maker's mark — signed like a hallmark, with a slow silver glint */}
      <section className="px-4 pt-10 pb-12 md:pt-12 md:pb-14 flex flex-col items-center text-center">
        <div className="flex items-center gap-3 text-accent" aria-hidden>
          <span className="h-px w-14 md:w-24 bg-gradient-to-r from-transparent to-accent/70" />
          <Sparkles className="size-3.5" />
          <span className="h-px w-14 md:w-24 bg-gradient-to-l from-transparent to-accent/70" />
        </div>
        <p className="mt-4 text-[10px] uppercase tracking-[0.35em] text-muted-foreground">
          Website designed &amp; crafted by
        </p>
        <a
          href="https://github.com/Hari-r31"
          target="_blank"
          rel="noopener noreferrer nofollow"
          aria-label="coDer on GitHub (opens in a new tab)"
          className="group mt-2 inline-flex items-start gap-1.5"
        >
          <span className="font-display italic text-4xl md:text-5xl leading-none pb-1 bg-[linear-gradient(110deg,var(--foreground)_42%,oklch(0.82_0.012_250)_50%,var(--foreground)_58%)] bg-[length:250%_100%] bg-clip-text text-transparent animate-[shimmer_6s_linear_infinite]">
            coDer
          </span>
          <ArrowUpRight className="size-4 mt-1 text-muted-foreground transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-accent" />
        </a>
        <p className="mt-4 max-w-md text-sm leading-relaxed text-muted-foreground">
          Every page of this website was designed and engineered end to end — from the storefront
          you&apos;re browsing to the live stock, checkout and store tools working behind it.
          Hand-built, line by line, with the same care as the silver it showcases.
        </p>
        <ul className="mt-5 flex flex-wrap justify-center gap-x-5 gap-y-2 text-[10px] uppercase tracking-[0.22em] text-foreground/70">
          {[
            "Designed from scratch",
            "Live stock updates",
            "Secure checkout",
            "Made for mobile",
          ].map((h) => (
            <li key={h} className="flex items-center gap-2">
              <span className="size-1 rotate-45 bg-accent/80" aria-hidden />
              {h}
            </li>
          ))}
        </ul>
      </section>
    </SiteLayout>
  );
}
