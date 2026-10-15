import { useState } from "react";
import { Check, Copy, Mail, Share2 } from "lucide-react";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface ShareButtonProps {
  /** Canonical product URL (no query string). */
  url: string;
  title: string;
  text: string;
}

type Channel = "whatsapp" | "facebook" | "x" | "telegram" | "email";

const CHANNELS: { id: Channel; label: string }[] = [
  { id: "whatsapp", label: "WhatsApp" },
  { id: "facebook", label: "Facebook" },
  { id: "x", label: "X" },
  { id: "telegram", label: "Telegram" },
  { id: "email", label: "Email" },
];

function withUtm(url: string, source: string): string {
  const u = new URL(url);
  u.searchParams.set("utm_source", source);
  u.searchParams.set("utm_medium", "share");
  return u.toString();
}

function channelHref(channel: Channel, url: string, title: string, text: string): string {
  const link = encodeURIComponent(withUtm(url, channel));
  const message = encodeURIComponent(`${title} — ${text}`);
  switch (channel) {
    case "whatsapp":
      return `https://wa.me/?text=${encodeURIComponent(`${title} — ${withUtm(url, channel)}`)}`;
    case "facebook":
      return `https://www.facebook.com/sharer/sharer.php?u=${link}`;
    case "x":
      return `https://twitter.com/intent/tweet?url=${link}&text=${encodeURIComponent(title)}`;
    case "telegram":
      return `https://t.me/share/url?url=${link}&text=${encodeURIComponent(title)}`;
    case "email":
      return `mailto:?subject=${encodeURIComponent(title)}&body=${message}%0A%0A${link}`;
  }
}

export function ShareButton({ url, title, text }: ShareButtonProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  // Native share sheet where available (mobile browsers); the popover is the
  // desktop / unsupported fallback.
  const handleNativeShare = async (): Promise<boolean> => {
    if (typeof navigator === "undefined" || typeof navigator.share !== "function") return false;
    try {
      await navigator.share({ title, text, url: withUtm(url, "native") });
    } catch (e) {
      // AbortError = user dismissed the sheet; nothing to fall back to.
      if ((e as DOMException).name !== "AbortError") return false;
    }
    return true;
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(withUtm(url, "copy"));
      setCopied(true);
      toast.success("Link copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy the link");
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Share this product"
          onClick={async (e) => {
            // Intercept the popover toggle only when the native sheet handled it.
            if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
              e.preventDefault();
              const handled = await handleNativeShare();
              if (!handled) setOpen(true);
            }
          }}
          className="shrink-0 mt-2 p-1 text-muted-foreground hover:text-foreground transition"
        >
          <Share2 className="size-4" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 rounded-none p-2">
        <ul className="flex flex-col">
          {CHANNELS.map((c) => (
            <li key={c.id}>
              <a
                href={channelHref(c.id, url, title, text)}
                target={c.id === "email" ? undefined : "_blank"}
                rel="noopener noreferrer"
                onClick={() => setOpen(false)}
                className="flex items-center gap-2.5 px-3 py-2.5 text-sm hover:bg-secondary transition"
              >
                {c.id === "email" && <Mail className="size-4" aria-hidden />}
                {c.label}
              </a>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={handleCopy}
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-sm hover:bg-secondary transition"
            >
              {copied ? (
                <Check className="size-4" aria-hidden />
              ) : (
                <Copy className="size-4" aria-hidden />
              )}
              {copied ? "Copied" : "Copy link"}
            </button>
          </li>
        </ul>
      </PopoverContent>
    </Popover>
  );
}
