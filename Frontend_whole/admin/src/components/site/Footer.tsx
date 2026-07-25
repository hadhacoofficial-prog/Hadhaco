import { Instagram, Youtube, Facebook, MapPin, Phone, Mail } from "lucide-react";
import logoAsset from "@/assets/hadha-logo-w.png";
import type { FooterConfig } from "@/types/cms";
import { useCompanyConfig } from "@hadha/shared-api";

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
  const { data: companyConfig } = useCompanyConfig();
  const c = config ?? {};
  const cols = c.columns ?? DEFAULT_COLS;
  const logoUrl = c.logo_url ?? companyConfig?.logo_url;

  const companyName = companyConfig?.brand_name || companyConfig?.name || "Hadha Silver Jewellery";
  const description = c.description ?? companyConfig?.description ?? "";
  const fullAddress = companyConfig
    ? [
        companyConfig.address_line_1,
        companyConfig.address_line_2,
        companyConfig.city,
        companyConfig.state,
        companyConfig.postal_code,
      ]
        .filter(Boolean)
        .join(", ")
    : "";
  const phone = c.phone ?? companyConfig?.phone ?? "";
  const email = c.email ?? companyConfig?.support_email ?? "";
  const copyrightName =
    c.copyright_name ??
    companyConfig?.legal_name ??
    companyConfig?.brand_name ??
    companyConfig?.name ??
    "Hadha Silver Jewellery";

  return (
    <footer className="bg-foreground text-background pt-20 pb-8 px-6 md:px-12">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-10 md:gap-12 max-w-7xl mx-auto">
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
            {(c.instagram || companyConfig?.instagram_url) && (
              <a
                href={c.instagram || companyConfig?.instagram_url || "#"}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Instagram className="size-4" />
              </a>
            )}
            {(c.youtube || companyConfig?.youtube_url) && (
              <a
                href={c.youtube || companyConfig?.youtube_url || "#"}
                target="_blank"
                rel="noreferrer"
                className="size-9 border border-background/30 flex items-center justify-center hover:bg-accent hover:border-accent hover:text-accent-foreground transition"
              >
                <Youtube className="size-4" />
              </a>
            )}
            {((c.facebook as string | undefined) || companyConfig?.facebook_url) && (
              <a
                href={(c.facebook as string) || companyConfig?.facebook_url || "#"}
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

      <div className="max-w-7xl mx-auto mt-16 pt-6 border-t border-background/15 flex flex-col md:flex-row items-center justify-between gap-3 text-xs text-background/60">
        <p>
          © {new Date().getFullYear()} {copyrightName}. All rights reserved.
        </p>
        <div className="flex items-center gap-5">
          <a href="/privacy" className="hover:text-accent">
            Privacy
          </a>
          <a href="/terms" className="hover:text-accent">
            Terms
          </a>
          <a href="/shipping-returns" className="hover:text-accent">
            Refund Policy
          </a>
        </div>
      </div>
    </footer>
  );
}
