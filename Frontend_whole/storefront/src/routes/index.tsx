import { createFileRoute } from "@tanstack/react-router";
import { AnnouncementBar } from "@/components/site/AnnouncementBar";
import { Header } from "@/components/site/Header";
import { Hero } from "@/components/site/Hero";
import { ShopByCategory } from "@/components/site/ShopByCategory";
import { ShopByGender } from "@/components/site/ShopByGender";
import { NewArrivals } from "@/components/site/NewArrivals";
import { CraftsmanshipVideo } from "@/components/site/CraftsmanshipVideo";
import { FeaturedCollection } from "@/components/site/FeaturedCollection";
import { FeaturedProducts } from "@/components/site/FeaturedProducts";
import { PromoBanner } from "@/components/site/PromoBanner";
import { Trending } from "@/components/site/Trending";
import { WhyChooseUs } from "@/components/site/WhyChooseUs";
import { Reviews } from "@/components/site/Reviews";
import { InstagramSection } from "@/components/site/InstagramSection";
import { Newsletter } from "@/components/site/Newsletter";
import { Footer } from "@/components/site/Footer";
import { OrnamentalDivider } from "@/components/common/OrnamentalDivider";
import { useHomepage } from "@/hooks/cms/useHomepage";
import type {
  AnnouncementConfig,
  FooterConfig,
  HeroCarouselConfig,
  ImageBannerConfig,
  InstagramGalleryConfig,
  NewsletterConfig,
  ProductGridConfig,
  SectionItem,
  VideoSectionConfig,
} from "@/types/cms";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Hadha · Handcrafted 92.5 Silver Jewellery" },
      {
        name: "description",
        content:
          "Quietly luxurious sterling silver jewellery — bugadi, chains, anklets, nakshi mala and more. Handcrafted in Visakhapatnam.",
      },
      { property: "og:title", content: "Hadha · Handcrafted 92.5 Silver Jewellery" },
      {
        property: "og:description",
        content: "Timeless 92.5 sterling silver pieces — handpicked for every chapter of you.",
      },
    ],
  }),
  component: Index,
});

function useSection<T = Record<string, unknown>>(
  sections: Record<string, { config: Record<string, unknown>; items: SectionItem[] }>,
  key: string,
): { config: Partial<T>; items: SectionItem[] } {
  const data = sections[key];
  return {
    config: (data?.config ?? {}) as Partial<T>,
    items: data?.items ?? [],
  };
}

function Index() {
  const { data: homepage } = useHomepage();
  const sections = homepage?.sections ?? {};

  const announcement = useSection<AnnouncementConfig>(sections, "announcement_bar");
  const hero = useSection<HeroCarouselConfig>(sections, "hero_carousel");
  const featuredCollection = useSection(sections, "featured_collection");
  const craftsmanship = useSection<VideoSectionConfig>(sections, "craftsmanship_video");
  const featuredProducts = useSection<ProductGridConfig>(sections, "featured_products");
  const newArrivals = useSection<ProductGridConfig>(sections, "new_arrivals");
  const trending = useSection<ProductGridConfig>(sections, "trending");
  const promoBanner = useSection<ImageBannerConfig>(sections, "promo_banner");
  const whyChoose = useSection(sections, "why_choose_us");
  const reviews = useSection(sections, "reviews");
  const instagram = useSection<InstagramGalleryConfig>(sections, "instagram_gallery");
  const newsletter = useSection<NewsletterConfig>(sections, "newsletter");
  const footer = useSection<FooterConfig>(sections, "footer");

  return (
    <div className="min-h-screen flex flex-col text-foreground">
      <AnnouncementBar config={announcement.config} items={announcement.items} />
      <Header />
      <main className="flex-1 pb-16 lg:pb-0">
        <Hero config={hero.config} items={hero.items} />
        <div>
          <ShopByGender />
        </div>
        <div className="hidden md:block bg-card">
          <FeaturedCollection items={featuredCollection.items} />
        </div>
        <div className="bg-muted">
          <FeaturedProducts config={featuredProducts.config} />
        </div>
        <CraftsmanshipVideo config={craftsmanship.config} />
        <div>
          <NewArrivals />
        </div>
        <div className="bg-card">
          <ShopByCategory />
        </div>
        <PromoBanner config={promoBanner.config} />
        <div className="bg-muted">
          <Trending />
        </div>
        <OrnamentalDivider className="py-10" />
        <WhyChooseUs items={whyChoose.items} />
        <div className="bg-card">
          <Reviews items={reviews.items} />
        </div>
        <div>
          <InstagramSection config={instagram.config} items={instagram.items} />
        </div>
        <Newsletter config={newsletter.config} />
      </main>
      <Footer config={footer.config} />
    </div>
  );
}
