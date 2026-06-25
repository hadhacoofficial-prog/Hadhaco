import { ShieldCheck, Heart, Sparkles, Gem } from "lucide-react";
import { motion } from "framer-motion";
import { staggerContainer, staggerItem } from "@/components/common/Reveal";

const items = [
  {
    icon: ShieldCheck,
    title: "92.5 Sterling Silver",
    text: "BIS-hallmarked. Guaranteed purity in every piece we craft.",
  },
  {
    icon: Gem,
    title: "Authentic Craftsmanship",
    text: "Hand-finished by master silversmiths in our Visakhapatnam atelier.",
  },
  {
    icon: Sparkles,
    title: "Trusted Quality",
    text: "Anti-tarnish coating and lifetime polish on every Hadha creation.",
  },
  {
    icon: Heart,
    title: "Made With Love",
    text: "A family heirloom in the making — gift-wrapped and delivered with care.",
  },
];

export function WhyChooseUs() {
  return (
    <section className="relative px-4 md:px-12 py-20 md:py-28 overflow-hidden">
      {/* Layered premium background */}
      <div className="absolute inset-0 bg-gradient-to-b from-muted via-background to-muted" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_45%_55%_at_15%_30%,oklch(0.86_0.012_250/0.45)_0%,transparent_60%),radial-gradient(ellipse_45%_55%_at_85%_70%,oklch(0.86_0.012_250/0.35)_0%,transparent_60%)]" />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage: "radial-gradient(oklch(0.27 0.025 258) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
        }}
      />

      <div className="relative max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-[11px] tracking-[0.32em] uppercase text-accent mb-3 font-cinzel">
            Why Hadha
          </p>
          <h2 className="font-cinzel text-3xl md:text-5xl">
            Crafted with care, worn with confidence.
          </h2>
          <p className="mt-4 text-muted-foreground font-cormorant text-lg md:text-xl max-w-xl mx-auto">
            Heritage techniques. Modern finish. A promise of purity in every gram.
          </p>
        </div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.2 }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 md:gap-7"
        >
          {items.map(({ icon: Icon, title, text }) => (
            <motion.div
              key={title}
              variants={staggerItem}
              whileHover={{ y: -6 }}
              transition={{ type: "spring", stiffness: 220, damping: 18 }}
              className="group relative overflow-hidden p-7 md:p-8 text-center bg-card/70 backdrop-blur-md border border-border/70 shadow-[0_20px_50px_-30px_oklch(0.27_0.025_258/0.25)] hover:border-primary/30 hover:shadow-[0_30px_60px_-30px_oklch(0.27_0.025_258/0.40)] transition-all duration-500"
            >
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="mx-auto size-14 rounded-full bg-gradient-to-br from-muted to-background border border-border flex items-center justify-center mb-5 group-hover:border-accent/50 group-hover:text-accent transition-colors">
                <Icon className="size-6" />
              </div>
              <h3 className="font-cinzel text-base md:text-lg mb-2 tracking-wide">{title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{text}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
