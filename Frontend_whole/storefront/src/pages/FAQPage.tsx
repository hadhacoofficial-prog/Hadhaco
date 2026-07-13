import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

const groups = [
  {
    title: "Orders & Payment",
    items: [
      {
        q: "What payment methods do you accept?",
        a: "We accept all major credit and debit cards, UPI, and net banking via Razorpay.",
      },
      {
        q: "Can I modify or cancel my order?",
        a: "You can modify or cancel your order within 2 hours of placing it by contacting us. Once dispatched, the order can no longer be cancelled.",
      },
    ],
  },
  {
    title: "Shipping & Delivery",
    items: [
      {
        q: "How long does delivery take?",
        a: "Standard delivery takes 3–5 business days. Express delivery is available at checkout and arrives in 1–2 business days.",
      },
      {
        q: "Do you ship internationally?",
        a: "Currently we ship across India. International shipping is coming soon.",
      },
      {
        q: "Is shipping free?",
        a: "Yes — standard shipping is complimentary on all orders above ₹999.",
      },
    ],
  },
  {
    title: "Returns & Exchange",
    items: [
      {
        q: "What is your return policy?",
        a: "Return eligibility depends on the individual product — please check the return information on each product page before ordering. Customised, engraved or pierced items are non-returnable for hygiene reasons.",
      },
      {
        q: "How do I initiate a return?",
        a: "Email hello@hadha.co with your order ID and reason. Our team will arrange a reverse pickup within 48 hours.",
      },
      {
        q: "When will I receive my refund?",
        a: "Refunds are processed within 5–7 business days after the returned item is received and quality-checked.",
      },
    ],
  },
  {
    title: "Product & Care",
    items: [
      {
        q: "Is your jewellery genuine 92.5 silver?",
        a: "Yes, every Hadha piece is crafted in 92.5 sterling silver and BIS-hallmarked for purity.",
      },
      {
        q: "How do I care for my silver?",
        a: "Avoid contact with perfumes, lotions and water. Wipe gently with a soft dry cloth and store in the pouch provided.",
      },
      {
        q: "Do you offer a warranty?",
        a: "Yes, all Hadha pieces come with a 6-month manufacturing warranty and a lifetime buyback on the silver value.",
      },
    ],
  },
];

function Item({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <button onClick={() => setOpen((v) => !v)} className="w-full text-left py-5 group">
      <div className="flex justify-between items-start gap-4">
        <span className="font-display text-base md:text-lg">{q}</span>
        <ChevronDown
          className={`size-5 shrink-0 transition ${open ? "rotate-180 text-accent" : "text-muted-foreground"}`}
        />
      </div>
      {open && <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{a}</p>}
    </button>
  );
}

export default function FAQPage() {
  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-3xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "FAQ" }]} />
        <div className="mt-6 mb-12 text-center">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
            Help Centre
          </p>
          <h1 className="font-display text-4xl md:text-5xl mt-2">Frequently Asked Questions</h1>
        </div>

        {groups.map((g) => (
          <div key={g.title} className="mb-10">
            <h2 className="font-display text-2xl mb-4 border-b border-border pb-3">{g.title}</h2>
            <div className="divide-y divide-border">
              {g.items.map((it) => (
                <Item key={it.q} q={it.q} a={it.a} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </SiteLayout>
  );
}
