import banner from "@/assets/banner.jpg";
import hero from "@/assets/hero.jpg";
import { ArrowRight } from "lucide-react";

export function FeaturedCollection() {
  return (
    <section className="grid md:grid-cols-2">
      <div className="relative aspect-[4/5] md:aspect-auto overflow-hidden group">
        <img
          src={hero}
          alt="Finger rings"
          loading="lazy"
          width={1200}
          height={1500}
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-[1500ms] group-hover:scale-105"
        />
      </div>
      <div className="bg-secondary flex items-center justify-center px-8 py-20 md:py-0">
        <div className="max-w-md">
          <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-4">Featured edit</p>
          <h3 className="font-display text-4xl md:text-5xl leading-tight">
            Finger Rings, redefined.
          </h3>
          <p className="mt-5 text-foreground/75">
            Stylish rings crafted to bring subtle elegance to every look — from stackable everyday
            bands to statement temple stones.
          </p>
          <a
            href="#"
            className="group mt-8 inline-flex items-center gap-3 bg-primary text-primary-foreground px-7 py-3.5 text-xs tracking-[0.22em] uppercase hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            Shop rings{" "}
            <ArrowRight className="size-4 group-hover:translate-x-1 transition-transform" />
          </a>
        </div>
      </div>
      <div className="bg-primary text-primary-foreground flex items-center justify-center px-8 py-20 md:py-0 order-3 md:order-none">
        <div className="max-w-md">
          <p className="text-[11px] tracking-[0.3em] uppercase text-accent mb-4">Bestseller</p>
          <h3 className="font-display text-4xl md:text-5xl leading-tight">The Bugadi edit.</h3>
          <p className="mt-5 text-primary-foreground/80">
            Heritage temple ear cuffs reimagined — non-piercing, press-on, and poised to become your
            new favourite.
          </p>
          <a
            href="#"
            className="group mt-8 inline-flex items-center gap-3 bg-accent text-accent-foreground px-7 py-3.5 text-xs tracking-[0.22em] uppercase hover:bg-primary-foreground hover:text-primary transition-colors"
          >
            Discover Bugadi{" "}
            <ArrowRight className="size-4 group-hover:translate-x-1 transition-transform" />
          </a>
        </div>
      </div>
      <div className="relative aspect-[4/5] md:aspect-auto overflow-hidden group order-4 md:order-none">
        <img
          src={banner}
          alt="Featured"
          loading="lazy"
          width={1200}
          height={1500}
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-[1500ms] group-hover:scale-105"
        />
      </div>
    </section>
  );
}
