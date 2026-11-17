import { useEffect, useRef, useState } from "react";
import { Loader2, Star, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { prepareReviewPhoto, ReviewPhotoError } from "@/lib/reviewPhoto";

// File inputs fire `cancel` when the picker is dismissed (Chrome 113+,
// Safari 16.4+); older browsers fall back to a focus timer.
const SUPPORTS_FILE_CANCEL =
  typeof HTMLInputElement !== "undefined" && "oncancel" in HTMLInputElement.prototype;
const PICKER_FALLBACK_MS = 4000;
const MAX_REVIEW_PHOTOS = 3;
const REVIEW_UPLOAD_TIMEOUT_MS = 60_000;

type ReviewPhoto = { file: File; preview: string };

// Shared review widgets — used by the product page's Reviews tab and the
// account page's post-delivery review reminders.

export function StarRating({
  value,
  onChange,
  size = "md",
}: {
  value: number;
  onChange?: (v: number) => void;
  size?: "sm" | "md" | "lg";
}) {
  const [hovered, setHovered] = useState(0);
  const sz = size === "lg" ? "size-7" : size === "md" ? "size-5" : "size-3.5";
  return (
    <div className="flex gap-1">
      {Array.from({ length: 5 }).map((_, i) => {
        const filled = i < (hovered || value);
        return (
          <button
            key={i}
            type="button"
            onClick={() => onChange?.(i + 1)}
            onMouseEnter={() => onChange && setHovered(i + 1)}
            onMouseLeave={() => onChange && setHovered(0)}
            className={`${onChange ? "cursor-pointer" : "cursor-default pointer-events-none"}`}
            aria-label={`Rate ${i + 1} star${i > 0 ? "s" : ""}`}
          >
            <Star
              className={`${sz} ${filled ? "fill-accent text-accent" : "text-border"} transition-colors`}
            />
          </button>
        );
      })}
    </div>
  );
}

export function WriteReviewModal({
  productId,
  orderId,
  productName,
  onClose,
  onSuccess,
}: {
  productId: string;
  /** Links the review to the delivered order (verified purchase context). */
  orderId?: string;
  /** Shown under the heading so multi-item orders stay unambiguous. */
  productName?: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [photos, setPhotos] = useState<ReviewPhoto[]>([]);
  // "picking": the file picker is open, or closed but the browser has not
  // delivered the files yet (mobile pickers close well before `change` fires
  // for cloud-backed photos). "preparing": reading the picked files.
  const [photoState, setPhotoState] = useState<"idle" | "picking" | "preparing">("idle");
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoBusy = photoState !== "idle";
  const slotsLeft = MAX_REVIEW_PHOTOS - photos.length;

  // Revoke preview URLs when the modal closes; removePhoto revokes its own.
  const photosRef = useRef(photos);
  photosRef.current = photos;
  useEffect(() => () => photosRef.current.forEach((p) => URL.revokeObjectURL(p.preview)), []);

  // Browsers without the input `cancel` event: when focus comes back and no
  // file has arrived after a grace period, treat the picker as dismissed.
  useEffect(() => {
    if (photoState !== "picking" || SUPPORTS_FILE_CANCEL) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onFocus = () => {
      timer = setTimeout(() => {
        if (!fileInputRef.current?.files?.length) setPhotoState("idle");
      }, PICKER_FALLBACK_MS);
    };
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      clearTimeout(timer);
    };
  }, [photoState]);

  useEffect(() => {
    const input = fileInputRef.current;
    if (!input) return;
    const onCancel = () => setPhotoState("idle");
    input.addEventListener("cancel", onCancel);
    return () => input.removeEventListener("cancel", onCancel);
  }, []);

  const openPicker = () => {
    const input = fileInputRef.current;
    if (!input || slotsLeft <= 0) return;
    // Cleared so picking the same file again still fires `change`.
    input.value = "";
    setPhotoState("picking");
    input.click();
  };

  const removePhoto = (index: number) => {
    setPhotos((prev) => {
      const removed = prev[index];
      if (removed) URL.revokeObjectURL(removed.preview);
      return prev.filter((_, i) => i !== index);
    });
  };

  const handleImageChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    if (picked.length === 0) {
      setPhotoState("idle");
      return;
    }
    if (picked.length > slotsLeft) {
      toast.error(`You can add up to ${MAX_REVIEW_PHOTOS} photos.`);
    }
    setPhotoState("preparing");
    // Decoding each photo also downloads cloud-backed ones and rejects bad
    // ones now, before the customer can submit.
    const results = await Promise.allSettled(
      picked.slice(0, slotsLeft).map(async (file): Promise<ReviewPhoto> => {
        const ready = await prepareReviewPhoto(file);
        return { file: ready, preview: URL.createObjectURL(ready) };
      }),
    );
    const loaded = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
    const failure = results.find((r) => r.status === "rejected");
    if (failure) {
      const reason = failure.reason;
      toast.error(
        reason instanceof ReviewPhotoError
          ? reason.message
          : "We couldn't read this photo. Please choose a JPG, PNG or WebP image.",
      );
    }
    setPhotos((prev) => [...prev, ...loaded]);
    setPhotoState("idle");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (photoBusy) {
      toast.error("Please wait for your photos to finish attaching.");
      return;
    }
    if (rating === 0) {
      toast.error("Please select a rating.");
      return;
    }
    if (!body.trim()) {
      toast.error("Please write a review description.");
      return;
    }
    setSubmitting(true);
    try {
      const form = new FormData();
      form.append("product_id", productId);
      form.append("rating", String(rating));
      form.append("body", body.trim());
      if (orderId) form.append("order_id", orderId);
      photos.forEach((p) => form.append("images", p.file));

      // Photos are already shrunk, but a slow mobile link can still need
      // longer than the default 20s for three of them.
      await api.upload("/reviews", form, { timeoutMs: REVIEW_UPLOAD_TIMEOUT_MS });
      toast.success("Review posted!");
      onSuccess();
      onClose();
    } catch (err: unknown) {
      toast.error(toUserMessage(err, "We couldn't post your review. Please try again."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-background border border-border w-full max-w-md p-6 relative">
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
          aria-label="Close"
        >
          <X className="size-5" />
        </button>
        <h2 className="font-display text-2xl mb-1">Write a Review</h2>
        {productName && <p className="text-sm font-medium mb-1">{productName}</p>}
        <p className="text-sm text-muted-foreground mb-6">
          Your review will be posted on the product page right away.
        </p>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground block mb-2">
              Rating <span className="text-destructive">*</span>
            </label>
            <StarRating value={rating} onChange={setRating} size="lg" />
          </div>
          <div>
            <label
              htmlFor="review-body"
              className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground block mb-2"
            >
              Review <span className="text-destructive">*</span>
            </label>
            <textarea
              id="review-body"
              rows={4}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Share your experience with this product…"
              className="w-full border border-border bg-background px-3 py-2.5 text-sm resize-none focus:outline-none focus:border-foreground transition"
              maxLength={2000}
            />
            <p className="text-[11px] text-muted-foreground mt-1 text-right">{body.length}/2000</p>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground block mb-2">
              Photos (optional, up to {MAX_REVIEW_PHOTOS})
            </label>
            <div className="flex flex-wrap gap-3">
              {photos.map((p, i) => (
                <div key={p.preview} className="relative">
                  <img
                    src={p.preview}
                    alt={`Photo ${i + 1} preview`}
                    className="size-20 object-cover border border-border"
                  />
                  <button
                    type="button"
                    onClick={() => removePhoto(i)}
                    disabled={submitting}
                    className="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full size-5 flex items-center justify-center"
                    aria-label={`Remove photo ${i + 1}`}
                  >
                    <X className="size-3" />
                  </button>
                </div>
              ))}
              {slotsLeft > 0 && (
                <button
                  type="button"
                  onClick={openPicker}
                  disabled={photoBusy || submitting}
                  aria-busy={photoBusy}
                  className="size-20 flex flex-col items-center justify-center gap-1 border border-dashed border-border text-[11px] text-muted-foreground hover:border-foreground hover:text-foreground transition disabled:cursor-wait"
                >
                  {photoBusy ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Upload className="size-4" />
                  )}
                  {photoBusy ? "Attaching…" : photos.length ? "Add photo" : "Upload photo"}
                </button>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={handleImageChange}
            />
          </div>
          <button
            type="submit"
            disabled={submitting || photoBusy}
            className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Submitting…" : photoBusy ? "Attaching photos…" : "Submit Review"}
          </button>
        </form>
      </div>
    </div>
  );
}
