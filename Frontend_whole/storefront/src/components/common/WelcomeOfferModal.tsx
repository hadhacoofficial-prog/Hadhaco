import logoAsset from "@/assets/hadha-logo.png";
import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { X, Gift } from "lucide-react";

const KEY = "hadha-welcome-offer-seen";

export function WelcomeOfferModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem(KEY)) return;
    const t = setTimeout(() => setOpen(true), 1200);
    return () => clearTimeout(t);
  }, []);

  const close = () => {
    setOpen(false);
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      // ignore storage errors (private browsing, quota exceeded)
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center px-4 animate-fade-in"
      role="dialog"
      aria-modal="true"
    >
      <div className="absolute inset-0 bg-foreground/60 backdrop-blur-sm" onClick={close} />
      <div className="relative w-full max-w-md bg-background border border-border shadow-[0_30px_80px_-30px_rgba(17,24,39,0.45)] animate-scale-in">
        <button
          onClick={close}
          aria-label="Close"
          className="absolute top-3 right-3 p-2 text-muted-foreground hover:text-foreground transition"
        >
          <X className="size-4" />
        </button>

        <div className="px-8 pt-10 pb-8 text-center">

            <img src={logoAsset} alt="Hadha" className="h-26 w-46 mx-auto" />

          <p className="text-[11px] tracking-[0.32em] uppercase text-primary mb-3 font-cinzel">
            A gift from Hadha
          </p>
          <h2 className="font-cinzel text-2xl md:text-3xl mb-3">Complimentary Gift Offer</h2>
          <p className="text-sm text-foreground/70 leading-relaxed">
            For orders above <span className="font-semibold text-foreground">₹2,000</span>, choose
            one complimentary item during checkout:
          </p>
          <ul className="mt-5 inline-flex flex-col gap-2 text-sm">
            <li className="px-4 py-2 border border-border bg-accent/40">🍬 Traditional Sweet</li>
            <li className="text-[10px] tracking-[0.3em] uppercase text-muted-foreground">— or —</li>
            <li className="px-4 py-2 border border-border bg-accent/40">
              🥟 Traditional Hot Snack
            </li>
          </ul>
          <p className="mt-5 text-xs text-muted-foreground">
            Your complimentary gift can be selected during checkout.
          </p>

          <div className="mt-7 flex flex-col sm:flex-row gap-3">
            <Link
              to="/collections"
              onClick={close}
              className="flex-1 bg-primary text-primary-foreground text-xs tracking-[0.24em] uppercase py-3.5 hover:bg-foreground transition"
            >
              Continue Shopping
            </Link>
            <button
              onClick={close}
              className="flex-1 border border-border text-xs tracking-[0.24em] uppercase py-3.5 hover:bg-secondary transition"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
