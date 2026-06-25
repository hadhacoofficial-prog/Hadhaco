/**
 * Polished full-page empty states for inventory / payment error flows.
 * All four variants share the same luxury jewellery aesthetic.
 */
import { Link } from "@tanstack/react-router";
import { SiteLayout } from "@/components/site/SiteLayout";

// ── SVG Illustrations ─────────────────────────────────────────────────────────

function JewelleryIllustration() {
  return (
    <svg viewBox="0 0 200 200" fill="none" className="w-44 h-44 md:w-56 md:h-56" aria-hidden>
      {/* Ring */}
      <ellipse cx="100" cy="130" rx="48" ry="16" stroke="#C9A96E" strokeWidth="2" opacity="0.3" />
      <circle cx="100" cy="90" r="44" stroke="#C9A96E" strokeWidth="2.5" fill="none" />
      <circle
        cx="100"
        cy="90"
        r="36"
        stroke="#C9A96E"
        strokeWidth="1.5"
        fill="none"
        opacity="0.5"
      />
      {/* Gem */}
      <polygon points="100,52 120,80 100,96 80,80" fill="#C9A96E" opacity="0.8" />
      <polygon points="100,52 120,80 100,68" fill="#E5C88A" opacity="0.9" />
      <polygon points="100,52 80,80 100,68" fill="#B8954F" opacity="0.9" />
      {/* Sold-out X */}
      <circle cx="148" cy="52" r="22" fill="#FEF2F2" stroke="#FECACA" strokeWidth="1.5" />
      <path
        d="M140 44l16 16M156 44l-16 16"
        stroke="#EF4444"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function TimerIllustration() {
  return (
    <svg viewBox="0 0 200 200" fill="none" className="w-44 h-44 md:w-56 md:h-56" aria-hidden>
      {/* Shopping bag */}
      <rect
        x="42"
        y="80"
        width="116"
        height="90"
        rx="6"
        stroke="#C9A96E"
        strokeWidth="2.5"
        fill="#FFFBF0"
      />
      <path
        d="M72 80V68a28 28 0 0156 0v12"
        stroke="#C9A96E"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      {/* Handles */}
      <path
        d="M72 80c0-8 6-12 12-12"
        stroke="#B8954F"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.6"
      />
      <path
        d="M128 80c0-8-6-12-12-12"
        stroke="#B8954F"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.6"
      />
      {/* Clock face */}
      <circle cx="100" cy="125" r="28" fill="white" stroke="#C9A96E" strokeWidth="2" />
      <circle cx="100" cy="125" r="2.5" fill="#C9A96E" />
      <path
        d="M100 113v12l8 8"
        stroke="#C9A96E"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Tick marks */}
      {[0, 90, 180, 270].map((deg) => (
        <line
          key={deg}
          x1={100 + 22 * Math.cos((deg * Math.PI) / 180)}
          y1={125 + 22 * Math.sin((deg * Math.PI) / 180)}
          x2={100 + 26 * Math.cos((deg * Math.PI) / 180)}
          y2={125 + 26 * Math.sin((deg * Math.PI) / 180)}
          stroke="#C9A96E"
          strokeWidth="2"
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
}

function PaymentFailedIllustration() {
  return (
    <svg viewBox="0 0 200 200" fill="none" className="w-44 h-44 md:w-56 md:h-56" aria-hidden>
      {/* Card */}
      <rect
        x="28"
        y="64"
        width="144"
        height="92"
        rx="8"
        fill="#FFFBF0"
        stroke="#C9A96E"
        strokeWidth="2"
      />
      <rect x="28" y="82" width="144" height="20" fill="#C9A96E" opacity="0.15" />
      {/* Chip */}
      <rect
        x="44"
        y="98"
        width="22"
        height="18"
        rx="3"
        stroke="#C9A96E"
        strokeWidth="1.5"
        fill="#E5C88A"
        opacity="0.5"
      />
      {/* Lines */}
      <rect x="44" y="126" width="60" height="5" rx="2.5" fill="#C9A96E" opacity="0.25" />
      <rect x="44" y="136" width="40" height="5" rx="2.5" fill="#C9A96E" opacity="0.18" />
      {/* Warning badge */}
      <circle cx="148" cy="68" r="26" fill="#FEF3C7" stroke="#F59E0B" strokeWidth="2" />
      <path d="M148 56v16" stroke="#F59E0B" strokeWidth="3" strokeLinecap="round" />
      <circle cx="148" cy="78" r="2" fill="#F59E0B" />
    </svg>
  );
}

function StockChangedIllustration() {
  return (
    <svg viewBox="0 0 200 200" fill="none" className="w-44 h-44 md:w-56 md:h-56" aria-hidden>
      {/* Cart */}
      <path
        d="M30 60h18l14 70h76l14-54H62"
        stroke="#C9A96E"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="82" cy="148" r="7" stroke="#C9A96E" strokeWidth="2" />
      <circle cx="130" cy="148" r="7" stroke="#C9A96E" strokeWidth="2" />
      {/* Box in cart */}
      <rect
        x="78"
        y="84"
        width="52"
        height="44"
        rx="3"
        stroke="#C9A96E"
        strokeWidth="1.5"
        fill="#FFFBF0"
      />
      <path d="M78 98h52" stroke="#C9A96E" strokeWidth="1.5" opacity="0.5" />
      <path d="M104 84v14" stroke="#C9A96E" strokeWidth="1.5" opacity="0.5" />
      {/* Alert */}
      <circle cx="148" cy="56" r="22" fill="#FEF2F2" stroke="#FECACA" strokeWidth="1.5" />
      <path d="M148 46v11" stroke="#EF4444" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="148" cy="62" r="2" fill="#EF4444" />
    </svg>
  );
}

// ── Shared layout ─────────────────────────────────────────────────────────────

interface OopsLayoutProps {
  illustration: React.ReactNode;
  title: string;
  description: string;
  actions: React.ReactNode;
}

function OopsLayout({ illustration, title, description, actions }: OopsLayoutProps) {
  return (
    <SiteLayout>
      <div className="min-h-[calc(100vh-200px)] flex items-center justify-center px-4 py-16">
        <div className="max-w-md w-full text-center">
          {/* Gold accent line */}
          <div className="w-12 h-px bg-accent mx-auto mb-8" aria-hidden />
          <div className="flex justify-center mb-8">{illustration}</div>
          <h1 className="font-display text-3xl md:text-4xl leading-tight mb-4">{title}</h1>
          <p className="text-muted-foreground text-sm md:text-base leading-relaxed mb-8">
            {description}
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">{actions}</div>
          {/* Bottom gold line */}
          <div className="w-12 h-px bg-accent mx-auto mt-8" aria-hidden />
        </div>
      </div>
    </SiteLayout>
  );
}

// ── Exported page variants ─────────────────────────────────────────────────────

export function SoldOutOopsPage({ onWishlist }: { onWishlist?: () => void }) {
  return (
    <OopsLayout
      illustration={<JewelleryIllustration />}
      title="Oops! This Item Just Sold Out"
      description="We're sorry, this product is currently unavailable. It may return soon or you can continue exploring our latest collections."
      actions={
        <>
          <Link
            to="/collections"
            className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-accent hover:text-accent-foreground transition"
          >
            Continue Shopping
          </Link>
          <Link
            to="/collections"
            className="flex-1 border border-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-foreground hover:text-background transition"
          >
            Browse Collections
          </Link>
          {onWishlist && (
            <button
              onClick={onWishlist}
              className="flex-1 border border-accent text-accent text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-accent hover:text-accent-foreground transition"
            >
              Wishlist This Item
            </button>
          )}
        </>
      }
    />
  );
}

export function ReservationExpiredOopsPage() {
  return (
    <OopsLayout
      illustration={<TimerIllustration />}
      title="Reservation Expired"
      description="Your reserved items have been released because the 10-minute reservation window ended before payment was completed."
      actions={
        <>
          <Link
            to="/cart"
            className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-accent hover:text-accent-foreground transition"
          >
            Return to Cart
          </Link>
          <Link
            to="/collections"
            className="flex-1 border border-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-foreground hover:text-background transition"
          >
            Continue Shopping
          </Link>
        </>
      }
    />
  );
}

export function PaymentFailedOopsPage({ onRetry }: { onRetry?: () => void }) {
  return (
    <OopsLayout
      illustration={<PaymentFailedIllustration />}
      title="Payment Failed"
      description="We couldn't complete your payment. Don't worry — no money was deducted and your reserved stock has been released."
      actions={
        <>
          {onRetry ? (
            <button
              onClick={onRetry}
              className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-accent hover:text-accent-foreground transition"
            >
              Retry Payment
            </button>
          ) : (
            <Link
              to="/checkout"
              className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-accent hover:text-accent-foreground transition"
            >
              Retry Payment
            </Link>
          )}
          <Link
            to="/cart"
            className="flex-1 border border-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-foreground hover:text-background transition"
          >
            Return to Cart
          </Link>
        </>
      }
    />
  );
}

export function StockChangedOopsPage() {
  return (
    <OopsLayout
      illustration={<StockChangedIllustration />}
      title="Oops! Stock Changed"
      description="One or more products in your cart became unavailable while you were checking out. Please review your cart and try again."
      actions={
        <>
          <Link
            to="/cart"
            className="flex-1 bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-accent hover:text-accent-foreground transition"
          >
            Review Cart
          </Link>
          <Link
            to="/collections"
            className="flex-1 border border-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 flex items-center justify-center hover:bg-foreground hover:text-background transition"
          >
            Continue Shopping
          </Link>
        </>
      }
    />
  );
}
