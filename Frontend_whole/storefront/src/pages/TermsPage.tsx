import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

const sections = [
  {
    t: "Acceptance of terms",
    b: "By accessing or using Hadha's website and services you agree to be bound by these Terms of Service. If you do not agree, please discontinue use of our website.",
  },
  {
    t: "Products & pricing",
    b: "All product descriptions, weights and images are indicative. Slight variations may occur due to the handcrafted nature of our jewellery. Prices are inclusive of GST unless stated otherwise and may change without prior notice.",
  },
  {
    t: "Orders & payment",
    b: "Placing an order constitutes an offer to purchase, which Hadha may accept or decline at its discretion. Payment must be successfully completed for the order to be confirmed.",
  },
  {
    t: "Shipping & risk",
    b: "Risk in the goods passes to you on delivery to the address you provide. Please ensure address details are accurate; we are not liable for delays caused by incorrect information.",
  },
  {
    t: "Intellectual property",
    b: "All content on this website — including images, design, text and trademarks — is the property of Hadha and is protected by applicable IP laws. Unauthorised use is prohibited.",
  },
  {
    t: "Limitation of liability",
    b: "To the extent permitted by law, Hadha's liability for any claim is limited to the value of the order in question. We are not liable for indirect or consequential losses.",
  },
  {
    t: "Governing law",
    b: "These terms are governed by the laws of India. Any disputes shall be subject to the exclusive jurisdiction of the courts at Visakhapatnam, Andhra Pradesh.",
  },
];

export default function Page() {
  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-3xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Terms" }]} />
        <h1 className="font-display text-4xl md:text-5xl mt-6 mb-3">Terms of Service</h1>
        <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground mb-10">
          Last updated: January 2026
        </p>
        <div className="space-y-8">
          {sections.map((s, i) => (
            <section key={s.t}>
              <h2 className="font-display text-xl md:text-2xl mb-3">
                {i + 1}. {s.t}
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">{s.b}</p>
            </section>
          ))}
        </div>
      </div>
    </SiteLayout>
  );
}
