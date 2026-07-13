import { MapPin, Phone, Clock, Navigation } from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

const stores = [
  {
    city: "Visakhapatnam",
    name: "Hadha Flagship Atelier",
    address: "MVP Sector 1, MVP Colony, Visakhapatnam 530017",
    phone: "+91 98765 43210",
    hours: "10:00 AM – 8:00 PM · Open all days",
    flagship: true,
  },
  {
    city: "Hyderabad",
    name: "Hadha Studio Banjara Hills",
    address: "Road No. 12, Banjara Hills, Hyderabad 500034",
    phone: "+91 98765 43211",
    hours: "11:00 AM – 9:00 PM · Open all days",
  },
  {
    city: "Bengaluru",
    name: "Hadha Studio Indiranagar",
    address: "100 Feet Road, Indiranagar, Bengaluru 560038",
    phone: "+91 98765 43212",
    hours: "11:00 AM – 9:00 PM · Open all days",
  },
  {
    city: "Chennai",
    name: "Hadha Studio Nungambakkam",
    address: "Khader Nawaz Khan Road, Nungambakkam, Chennai 600006",
    phone: "+91 98765 43213",
    hours: "11:00 AM – 9:00 PM · Closed Tuesdays",
  },
];

export default function Page() {
  return (
    <SiteLayout>
      <div className="px-4 md:px-8 py-10 max-w-6xl mx-auto">
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "Store Locator" }]} />
        <div className="mt-6 mb-12">
          <p className="text-[11px] uppercase tracking-[0.3em] text-muted-foreground">Visit us</p>
          <h1 className="font-display text-4xl md:text-5xl mt-2">Find a Hadha store</h1>
          <p className="text-sm text-muted-foreground mt-3 max-w-xl">
            Step into one of our ateliers and try on our complete silver jewellery collection.
          </p>
        </div>

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
                <li className="flex gap-3">
                  <Phone className="size-4 mt-0.5 shrink-0 text-accent" />
                  {s.phone}
                </li>
                <li className="flex gap-3">
                  <Clock className="size-4 mt-0.5 shrink-0 text-accent" />
                  {s.hours}
                </li>
              </ul>
              <a
                href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(s.address)}`}
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
      </div>
    </SiteLayout>
  );
}
