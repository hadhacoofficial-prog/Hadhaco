import { Mail } from "lucide-react";
import type { NewsletterConfig } from "@/types/cms";

const DEFAULTS: NewsletterConfig = {
  heading: "Be first to know.",
  description:
    "Join the Hadha circle for early access to drops, members-only edits, and quiet little gifts.",
  placeholder: "Your email address",
  btn_text: "Subscribe",
  success_message: "Welcome to the Hadha Circle!",
};

interface NewsletterProps {
  config?: Partial<NewsletterConfig>;
}

export function Newsletter({ config }: NewsletterProps) {
  const c = { ...DEFAULTS, ...config };

  return (
    <section className="bg-primary text-primary-foreground px-6 py-20 md:py-24">
      <div className="max-w-3xl mx-auto text-center">
        <Mail className="size-7 mx-auto text-accent mb-5" />
        <h2 className="font-display text-3xl md:text-5xl leading-tight">{c.heading}</h2>
        <p className="mt-4 text-primary-foreground/80 max-w-lg mx-auto">{c.description}</p>
        <form
          onSubmit={(e) => e.preventDefault()}
          className="mt-8 flex flex-col sm:flex-row gap-3 max-w-md mx-auto"
        >
          <input
            type="email"
            required
            placeholder={c.placeholder}
            className="flex-1 bg-transparent border border-primary-foreground/40 px-4 py-3 outline-none placeholder:text-primary-foreground/50 focus:border-accent transition"
          />
          <button className="bg-accent text-accent-foreground px-7 py-3 text-xs tracking-[0.22em] uppercase hover:bg-primary-foreground hover:text-primary transition-colors">
            {c.btn_text}
          </button>
        </form>
      </div>
    </section>
  );
}
