import { createFileRoute } from "@tanstack/react-router";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

export const Route = createFileRoute("/privacy")({
  head: () => ({ meta: [{ title: "Privacy Policy · Hadha" }] }),
  component: Page,
});

const sections = [
  {
    t: "Information we collect",
    b: "We collect information you provide directly — such as name, email, phone, shipping address and payment details — in order to process orders and provide customer support. We also collect limited technical data (device, browser, usage patterns) to improve our website.",
  },
  {
    t: "How we use information",
    b: "Information is used to fulfil your orders, communicate about purchases, send service updates, personalise your experience, and — only with your consent — share marketing communications.",
  },
  {
    t: "Sharing & disclosure",
    b: "We never sell your personal data. We share information only with trusted service providers (logistics, payments, analytics) under strict confidentiality, or where required by law.",
  },
  {
    t: "Cookies",
    b: "We use cookies to remember your cart, preferences and login state, and to analyse site usage. You can disable cookies from your browser settings; some features may not work as expected.",
  },
  {
    t: "Data security",
    b: "All payments are processed via PCI-DSS compliant gateways. Your account is protected by industry-standard encryption and access controls.",
  },
  {
    t: "Your rights",
    b: "You can access, update or request deletion of your personal data at any time by writing to hello@hadha.co. We respond within 30 days.",
  },
];

function Page() {
  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-3xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Privacy Policy" }]} />
        <h1 className="font-display text-4xl md:text-5xl mt-6 mb-3">Privacy Policy</h1>
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
