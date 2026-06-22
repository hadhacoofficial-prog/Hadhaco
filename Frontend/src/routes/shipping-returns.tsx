import { createFileRoute } from "@tanstack/react-router";
import { Truck, RefreshCw, ShieldCheck, Package } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

export const Route = createFileRoute("/shipping-returns")({
  head: () => ({
    meta: [
      { title: "Shipping & Returns · Hadha" },
      {
        name: "description",
        content: "Shipping, returns and buyback policies for Hadha Silver Jewellery.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-4xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Shipping & Returns" }]} />
        <div className="mt-6 mb-12">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Policies</p>
          <h1 className="font-display text-4xl md:text-5xl mt-2">Shipping & Returns</h1>
        </div>

        <div className="grid sm:grid-cols-2 gap-4 mb-12">
          {[
            { icon: <Truck />, t: "Free Shipping", s: "On orders above ₹999" },
            {
              icon: <RefreshCw />,
              t: "Product-specific Returns",
              s: "Eligibility varies by piece",
            },
            { icon: <ShieldCheck />, t: "Authenticity", s: "BIS hallmarked 92.5" },
            { icon: <Package />, t: "Secure Packaging", s: "Insured & tracked" },
          ].map((f) => (
            <div key={f.t} className="border border-border p-5 flex items-center gap-4">
              <span className="text-accent">{f.icon}</span>
              <div>
                <p className="font-display">{f.t}</p>
                <p className="text-xs text-muted-foreground">{f.s}</p>
              </div>
            </div>
          ))}
        </div>

        <article className="prose-hadha space-y-10">
          <Section title="Shipping">
            <P>
              Orders are processed within 24–48 hours of placement. Standard delivery takes 3–5
              business days, while express delivery (available at checkout) reaches you in 1–2
              business days.
            </P>
            <P>
              Shipping is complimentary on all orders above ₹999. A flat fee of ₹99 applies below
              this threshold for standard delivery; express delivery is ₹199 nationwide.
            </P>
            <P>
              Every Hadha order is shipped in tamper-proof, insured packaging with end-to-end
              tracking. You'll receive shipping updates by email and SMS.
            </P>
          </Section>

          <Section title="Returns & Exchange">
            <P>
              Return eligibility depends on the individual product. The applicable return window and
              conditions are listed on each product page — please review them before placing your
              order. Customised, engraved, or pierced items (such as earrings and nose pins) are
              non-returnable for hygiene reasons.
            </P>
            <P>
              For eligible items, email{" "}
              <a className="text-accent underline" href="mailto:hello@hadha.co">
                hello@hadha.co
              </a>{" "}
              with your order ID and our team will arrange a reverse pickup. Refunds are processed
              within 5–7 business days after the returned item passes quality check.
            </P>
          </Section>

          <Section title="Cancellation">
            <P>
              You may cancel your order within 2 hours of placement by contacting our support team.
              Orders that have been dispatched cannot be cancelled but can be returned per our
              return policy.
            </P>
          </Section>

          <Section title="Lifetime Buyback">
            <P>
              Every Hadha piece is eligible for lifetime buyback at the prevailing silver rate,
              minus making charges. Bring your original invoice to our atelier or contact us by
              email.
            </P>
          </Section>
        </article>
      </div>
    </SiteLayout>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-2xl md:text-3xl mb-4">{title}</h2>
      <div className="space-y-3 text-sm text-muted-foreground leading-relaxed">{children}</div>
    </section>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p>{children}</p>;
}
