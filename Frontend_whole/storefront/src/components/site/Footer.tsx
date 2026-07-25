import { Link } from "@tanstack/react-router";
import { Instagram, Youtube, Facebook, MapPin, Phone, Mail } from "lucide-react";
import logoAsset from "@/assets/hadha-logo-w.png";
import type { FooterConfig } from "@/types/cms";
import { NavJewelleryBgMobile } from "@/components/site/NavJewelleryBgMobile";
import { usePublicCompanyConfig } from "@/hooks/company/useCompanyConfig";

const DEFAULT_COLS = [
  {
    title: "Shopping",
    links: [
      { label: "Women", url: "/search?gender=women" },
      { label: "Men", url: "/search?gender=men" },
      { label: "Kids", url: "/search?gender=kids" },
      { label: "New Arrivals", url: "/search?filter=new" },
      { label: "Deals Of The Day", url: "/search?filter=deals" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About Us", url: "/about" },
      { label: "Contact Us", url: "/contact" },
      { label: "Privacy Policy", url: "/privacy" },
      { label: "Shipping Policy", url: "/shipping-returns" },
      { label: "Returns Policy", url: "/shipping-returns" },
      { label: "Terms & Conditions", url: "/terms" },
    ],
  },
];

interface FooterProps {
  config?: Partial<FooterConfig>;
}

export function Footer({ config }: FooterProps) {
  const { data: company } = usePublicCompanyConfig();
  const c = config ?? {};
  const cols = c.columns ?? DEFAULT_COLS;
  const logoUrl = c.logo_url ?? company?.logo_url;

  const companyName = company?.brand_name || company?.name || "Hadha Silver Jewellery";
  const description = c.description ?? company?.description ?? "";
  const fullAddress = company
    ? [
        company.address_line_1,
        company.address_line_2,
        company.city,
        company.state,
        company.postal_code,
      ]
        .filter(Boolean)
        .join(", ")
    : "";
  const phone = c.phone ?? company?.phone ?? "";
  const email = c.email ?? company?.support_email ?? "";
  const copyrightName =
    c.copyright_name ??
    company?.legal_name ??
    company?.brand_name ??
    company?.name ??
    "Hadha Silver Jewellery";

  return (
    <footer className="relative bg-foreground text-background pt-20 pb-8 px-6 md:px-12">
      {/* Same jewellery line-art as the navbar, recolored to cream so it reads against the dark footer */}
      <div
        className="absolute inset-0 overflow-hidden pointer-events-none"
        style={{ "--primary": "var(--background)" } as React.CSSProperties}
        aria-hidden="true"
      >
        <NavJewelleryBgMobile />
      </div>

      <div className="relative z-10 grid grid-cols-2 md:grid-cols-4 gap-10 md:gap-12 max-w-7xl mx-auto">
        <div className="col-span-2">
          <a href="/" className="inline-flex items-center" aria-label={companyName}>
            {logoUrl ? (
              <img src={logoUrl} alt={companyName} className="h-28 md:h-36 w-auto object-contain" />
            ) : (
              <img
                src={logoAsset}
                alt={companyName}
                className="h-28 md:h-36 w-auto object-contain"
              />
            )}
          </a>
          {description && (
            <p className="mt-6 text-background/70 leading-relaxed max-w-sm text-sm">
              {description}
            </p>
          )}
          <div className="mt-6 space-y-2.5 text-sm text-background/70">
            {fullAddress && (
              <p className="flex items-start gap-3">
                <MapPin className="size-4 mt-0.5 shrink-0 text-accent" />
                {fullAddress}
              </p>
            )}
            {phone && (
              <p className="flex items-center gap-3">
                <Phone className="size-4 text-accent" />
                {phone}
              </p>
            )}
            {email && (
              <p className="flex items-center gap-3">
                <Mail className="size-4 text-accent" />
                {email}
              </p>
            )}
          </div>
          <div className="mt-6 flex items-center gap-3">
            {c.instagram && (
              <a
                href={c.instagram}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Instagram className="size-4" />
              </a>
            )}
            {c.youtube && (
              <a
                href={c.youtube}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Youtube className="size-4" />
              </a>
            )}
            {(c.facebook as string | undefined) && (
              <a
                href={c.facebook as string}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Facebook className="size-4" />
              </a>
            )}
            {/* Fallback social icons from company config */}
            {!c.instagram && !c.youtube && !c.facebook && company?.instagram_url && (
              <a
                href={company.instagram_url}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Instagram className="size-4" />
              </a>
            )}
            {!c.instagram && !c.youtube && !c.facebook && company?.youtube_url && (
              <a
                href={company.youtube_url}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Youtube className="size-4" />
              </a>
            )}
            {!c.instagram && !c.youtube && !c.facebook && company?.facebook_url && (
              <a
                href={company.facebook_url}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Facebook className="size-4" />
              </a>
            )}
          </div>
        </div>

        {cols.map((col) => (
          <div key={col.title}>
            <h4 className="font-display text-lg mb-5">{col.title}</h4>
            <ul className="space-y-3 text-sm text-background/70">
              {col.links.map((l) => (
                <li key={l.label}>
                  <a href={l.url} className="hover:text-accent transition">
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="relative z-10 max-w-7xl mx-auto mt-16 pt-6 border-t border-background/15 flex flex-col md:flex-row items-center justify-between gap-3 text-xs text-background/60">
        <p>
          © {new Date().getFullYear()} {copyrightName}. All rights reserved.
        </p>
        <div className="flex items-center gap-5">
          <Link to="/privacy" className="hover:text-accent">
            Privacy
          </Link>
          <Link to="/terms" className="hover:text-accent">
            Terms
          </Link>
          <Link to="/shipping-returns" className="hover:text-accent">
            Refund Policy
          </Link>
        </div>
      </div>
    </footer>
  );
}
