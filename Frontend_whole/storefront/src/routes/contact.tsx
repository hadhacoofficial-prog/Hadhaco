import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Mail, Phone, MapPin, MessageCircle, Clock } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

export const Route = createFileRoute("/contact")({
  head: () => ({
    meta: [
      { title: "Contact Us · Hadha" },
      {
        name: "description",
        content:
          "Talk to the Hadha team — by phone, email, WhatsApp, or visit our Visakhapatnam atelier.",
      },
    ],
  }),
  component: ContactPage,
});

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

function ContactPage() {
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const form = e.currentTarget;
    const fd = new FormData(form);
    const name = (fd.get("name") as string).trim();
    const email = (fd.get("email") as string).trim();
    const phone = (fd.get("phone") as string).trim();
    const subject = (fd.get("subject") as string).trim();
    const message = (fd.get("message") as string).trim();

    if (!name || !email || !message) {
      setError("Please fill in all required fields.");
      return;
    }

    setSubmitting(true);
    try {
      const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
      const res = await fetch(`${base}/enquiries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          email,
          phone: phone || null,
          subject: subject || "General Enquiry",
          message,
          website: "",
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.message ?? `Request failed (${res.status})`);
      }
      setSent(true);
      form.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

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
          <form onSubmit={handleSubmit} className="space-y-5 border border-border p-8 bg-card">
            {sent && (
              <div className="bg-accent/10 text-accent text-sm px-4 py-3">
                Thanks! We'll get back to you within 24 hours.
              </div>
            )}
            {error && (
              <div className="bg-destructive/10 text-destructive text-sm px-4 py-3">{error}</div>
            )}
            <div className="grid sm:grid-cols-2 gap-4">
              <F label="Name" name="name" required />
              <F label="Email" name="email" type="email" required />
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <F label="Phone" name="phone" type="tel" />
              <F label="Subject" name="subject" />
            </div>
            <label className="block">
              <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Message
              </span>
              <textarea
                name="message"
                required
                rows={6}
                className="mt-1.5 w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition"
              />
            </label>
            {/* Honeypot — hidden from humans, bots will fill it */}
            <div
              style={{
                position: "absolute",
                left: "-9999px",
                opacity: 0,
                height: 0,
                width: 0,
                overflow: "hidden",
              }}
              aria-hidden="true"
            >
              <label htmlFor="website">Website</label>
              <input type="text" name="website" id="website" tabIndex={-1} autoComplete="off" />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] px-8 py-3.5 hover:bg-accent hover:text-accent-foreground disabled:opacity-50 transition"
            >
              {submitting ? "Sending..." : "Send Message"}
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

function F({ label, ...rest }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
      <input
        {...rest}
        className="mt-1.5 w-full bg-background border border-border px-3 py-2.5 text-sm outline-none focus:border-foreground transition"
      />
    </label>
  );
}
