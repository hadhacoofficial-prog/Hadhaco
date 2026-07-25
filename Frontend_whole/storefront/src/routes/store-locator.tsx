import { useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { MapPin, Phone, Clock, Navigation } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";
import { usePublicCompanyConfig } from "@/hooks/company/useCompanyConfig";

export const Route = createFileRoute("/store-locator")({
  head: () => ({
    meta: [
      { title: "Store Locator · Hadha" },
      {
        name: "description",
        content:
          "Visit our flagship atelier — try on our complete silver jewellery collection in person.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  const { data: config } = usePublicCompanyConfig();
  const companyName = config?.brand_name || config?.name || "Hadha";

  const stores = useMemo(() => {
    if (!config) return [];
    const result: {
      city: string;
      name: string;
      address: string;
      phone: string;
      hours: string;
      flagship: boolean;
    }[] = [];

    // Primary store from company config
    const fullAddress = [
      config.address_line_1,
      config.address_line_2,
      config.city,
      config.state,
      config.postal_code,
    ]
      .filter(Boolean)
      .join(", ");
    if (fullAddress) {
      result.push({
        city: config.city || "",
        name: `${companyName} Flagship Atelier`,
        address: fullAddress,
        phone: config.phone || "",
        hours: config.business_hours || "10:00 AM – 8:00 PM · Open all days",
        flagship: true,
      });
    }

    return result;
  }, [config, companyName]);

  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-6xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Store Locator" }]} />
        <div className="mt-6 mb-12">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Visit us</p>
          <h1 className="font-display text-4xl md:text-5xl mt-2">Find our store</h1>
          <p className="text-sm text-muted-foreground mt-3 max-w-xl">
            Step into our atelier and try on our complete silver jewellery collection.
          </p>
        </div>

        {stores.length === 0 ? (
          <p className="text-muted-foreground text-sm">Store information coming soon.</p>
        ) : (
          <div className="grid md:grid-cols-2 gap-5">
            {stores.map((s) => (
              <div
                key={s.name}
                className={`border p-6 bg-card relative ${s.flagship ? "border-foreground" : "border-border"}`}
              >
                {s.flagship && (
                  <span className="absolute -top-2.5 left-6 bg-accent text-accent-foreground text-[10px] uppercase tracking-[0.22em] px-3 py-0.5">
                    Flagship
                  </span>
                )}
                <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
                  {s.city}
                </p>
                <h2 className="font-display text-2xl mt-1">{s.name}</h2>
                <ul className="mt-5 space-y-2.5 text-sm">
                  <li className="flex gap-3">
                    <MapPin className="size-4 mt-0.5 shrink-0 text-accent" />
                    {s.address}
                  </li>
                  {s.phone && (
                    <li className="flex gap-3">
                      <Phone className="size-4 mt-0.5 shrink-0 text-accent" />
                      {s.phone}
                    </li>
                  )}
                  {s.hours && (
                    <li className="flex gap-3">
                      <Clock className="size-4 mt-0.5 shrink-0 text-accent" />
                      {s.hours}
                    </li>
                  )}
                </ul>
                <a
                  href={
                    config?.google_maps_url ||
                    `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(s.address)}`
                  }
                  target="_blank"
                  rel="noreferrer"
                  className="mt-5 inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] border border-foreground px-4 py-2 hover:bg-foreground hover:text-background transition"
                >
                  <Navigation className="size-3.5" />
                  Get Directions
                </a>
              </div>
            ))}
          </div>
        )}
      </div>
    </SiteLayout>
  );
}
