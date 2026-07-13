import { useHomepage } from "@/hooks/cms/useHomepage";
import type { FooterConfig } from "@/types/cms";

const MESSAGE = "Hi Hadha, I'd like to know more about your silver jewellery.";

/**
 * Accepts either a raw phone number (with or without country code / punctuation)
 * or a full wa.me / api.whatsapp.com URL, since the CMS field accepts both.
 */
function buildWhatsAppUrl(rawNumber: string, message: string): string {
  const trimmed = rawNumber.trim();

  if (/^https?:\/\//i.test(trimmed)) {
    const url = new URL(trimmed);
    if (!url.searchParams.has("text")) {
      url.searchParams.set("text", message);
    }
    return url.toString();
  }

  const digits = trimmed.replace(/\D/g, "");
  return `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
}

export function WhatsAppFab() {
  const { data: homepage } = useHomepage();
  const footerConfig = homepage?.sections["footer"]?.config as Partial<FooterConfig> | undefined;
  const whatsappNumber = footerConfig?.whatsapp?.trim();

  if (!whatsappNumber) return null;

  const href = buildWhatsAppUrl(whatsappNumber, MESSAGE);

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Chat with us on WhatsApp"
      className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-40 group"
    >
      <span className="absolute inset-0 rounded-full bg-[#25D366] opacity-40 animate-ping" />
      <span className="absolute -inset-1 rounded-full bg-[#25D366]/30 blur-md" />
      <span className="relative flex items-center justify-center size-12 md:size-14 rounded-full bg-[#25D366] text-white shadow-[0_8px_24px_-4px_rgba(37,211,102,0.6)] hover:scale-110 active:scale-95 transition">
        <svg
          viewBox="0 0 32 32"
          className="size-6 md:size-7"
          aria-hidden="true"
          fill="currentColor"
        >
          <path d="M19.11 17.205c-.372 0-1.088 1.39-1.518 1.39a.63.63 0 0 1-.315-.1c-.802-.402-1.504-.817-2.163-1.447-.545-.516-1.146-1.29-1.46-1.963a.426.426 0 0 1-.073-.215c0-.33.99-.945.99-1.49 0-.143-.73-2.09-.832-2.335-.143-.372-.214-.487-.6-.487-.187 0-.36-.043-.53-.043-.302 0-.53.115-.715.315-.53.573-.945 1.146-.945 2.061 0 .932.43 1.834.945 2.62 1.49 2.262 3.466 3.967 5.927 4.857.385.143 1.49.452 1.92.452.673 0 1.504-.187 1.953-.715.315-.372.6-1.117.6-1.59 0-.115-.043-.215-.072-.315-.087-.187-.302-.302-.6-.502-.327-.215-1.504-.687-1.776-.687z M16 .047c8.78 0 15.95 7.17 15.95 15.95 0 8.78-7.17 15.95-15.95 15.95-2.78 0-5.43-.7-7.78-2.05L0 32l2.15-7.95C.7 21.65 0 19 0 16 0 7.22 7.22.047 16 .047zm0 2.65C8.68 2.697 2.65 8.726 2.65 16c0 2.74.8 5.39 2.36 7.65l.36.5-1.43 5.25 5.4-1.4.46.27c2.21 1.32 4.74 2.04 7.2 2.04 7.32 0 13.35-6.03 13.35-13.35S23.32 2.697 16 2.697z" />
        </svg>
      </span>
    </a>
  );
}
