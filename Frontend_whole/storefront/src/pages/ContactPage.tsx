import { useState } from "react";
import { Mail, Phone, MapPin, MessageCircle, Clock } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

const CONTACT_CARDS: { icon: React.ReactNode; t: string; s: string; n: string; href?: string }[] = [
  {
    icon: <Phone className="size-5" />,
    t: "Phone",
    s: "+91 60941 15885",
    n: "Mon–Sat, 10am–7pm",
  },
  {
    icon: <Mail className="size-5" />,
    t: "Email",
    s: "hello@hadha.co",
    n: "Replies within 24 hours",
  },
  {
    icon: <MessageCircle className="size-5" />,
    t: "WhatsApp",
    s: "+91 60941 15885",
    n: "Fastest response",
    href: "https://wa.me/916094115885",
  },
  {
    icon: <MapPin className="size-5" />,
    t: "Atelier",
    s: "MVP Sector 1, MVP Colony",
    n: "Visakhapatnam 530017",
  },
  {
    icon: <Clock className="size-5" />,
    t: "Store hours",
    s: "10:00 AM – 8:00 PM",
    n: "Open all days",
  },
];

function F({ label, ...rest }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
      <input
        aria-label={label}
        {...rest}
        className="mt-1.5 w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition"
      />
    </label>
  );
}

export default function ContactPage() {
  const [sent, setSent] = useState(false);
  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-6xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Contact" }]} />
        <div className="mt-6 mb-12">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
            Get in touch
          </p>
          <h1 className="font-display text-4xl md:text-5xl mt-2">We'd love to hear from you</h1>
        </div>

        <div className="grid lg:grid-cols-[1fr_400px] gap-12">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSent(true);
            }}
            className="space-y-5 border border-border p-8 bg-card"
          >
            {sent && (
              <div className="bg-accent/10 text-accent text-sm px-4 py-3">
                Thanks! We'll get back to you within 24 hours.
              </div>
            )}
            <div className="grid sm:grid-cols-2 gap-4">
              <F label="Name" name="name" required />
              <F label="Email" name="email" type="email" required />
            </div>
            <F label="Subject" name="subject" />
            <label className="block">
              <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Message
              </span>
              <textarea
                name="message"
                aria-label="Message"
                required
                rows={6}
                className="mt-1.5 w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition"
              />
            </label>
            <button className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-8 py-3.5 hover:bg-accent hover:text-accent-foreground transition">
              Send Message
            </button>
          </form>

          <aside className="space-y-4">
            {CONTACT_CARDS.map((c) => {
              const Wrapper = c.href ? "a" : "div";
              return (
                <Wrapper
                  key={c.t}
                  {...(c.href
                    ? { href: c.href, target: "_blank", rel: "noopener noreferrer" }
                    : {})}
                  className="border border-border p-5 bg-card flex gap-4"
                >
                  <span className="text-accent mt-0.5">{c.icon}</span>
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                      {c.t}
                    </p>
                    <p className="font-display text-lg mt-0.5">{c.s}</p>
                    <p className="text-xs text-muted-foreground">{c.n}</p>
                  </div>
                </Wrapper>
              );
            })}
          </aside>
        </div>
      </div>
    </SiteLayout>
  );
}
