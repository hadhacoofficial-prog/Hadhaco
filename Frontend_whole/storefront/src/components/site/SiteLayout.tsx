import type { ReactNode } from "react";
import { AnnouncementBar } from "@/components/site/AnnouncementBar";
import { Header } from "@/components/site/Header";
import { Footer } from "@/components/site/Footer";
import { useHomepage } from "@/hooks/cms/useHomepage";
import type { FooterConfig } from "@/types/cms";

export function SiteLayout({ children }: { children: ReactNode }) {
  const { data: homepage } = useHomepage();
  const footerConfig = homepage?.sections["footer"]?.config as Partial<FooterConfig> | undefined;

  return (
    <div className="min-h-screen flex flex-col text-foreground">
      <AnnouncementBar />
      <Header />
      <main className="flex-1 pb-16 lg:pb-0">{children}</main>
      <Footer config={footerConfig} />
    </div>
  );
}
