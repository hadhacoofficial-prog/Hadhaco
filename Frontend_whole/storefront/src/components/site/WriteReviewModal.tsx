import { useRef, useState } from "react";
import { Star, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";

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
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImage(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
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
      if (image) form.append("images", image);

      await api.upload("/reviews", form);
      toast.success("Review submitted! It will appear after approval.");
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message ?? "Failed to submit review.";
      toast.error(msg);
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
          Your review will be visible after admin approval.
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
              Photo (optional)
            </label>
            {imagePreview ? (
              <div className="relative inline-block">
                <img
                  src={imagePreview}
                  alt="Preview"
                  className="size-20 object-cover border border-border"
                />
                <button
                  type="button"
                  onClick={() => {
                    setImage(null);
                    setImagePreview(null);
                  }}
                  className="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full size-5 flex items-center justify-center"
                  aria-label="Remove image"
                >
                  <X className="size-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 border border-dashed border-border px-4 py-3 text-sm text-muted-foreground hover:border-foreground hover:text-foreground transition"
              >
                <Upload className="size-4" />
                Upload photo
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleImageChange}
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-primary text-primary-foreground text-[11px] uppercase tracking-[0.22em] py-3.5 hover:bg-accent hover:text-accent-foreground transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Submitting…" : "Submit Review"}
          </button>
        </form>
      </div>
    </div>
  );
}
