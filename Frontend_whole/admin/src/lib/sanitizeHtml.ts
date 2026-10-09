import DOMPurify from "dompurify";

/**
 * Sanitise admin/stored HTML before it is injected with dangerouslySetInnerHTML.
 *
 * Stored notification templates are editable by any admin and are rendered in
 * other admins' sessions (including super admins), so they must never be
 * trusted as markup: scripts, event-handler attributes, javascript: URLs,
 * iframes/objects and forms are stripped; ordinary email formatting is kept.
 */
export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "form", "iframe", "object", "embed", "base", "meta", "link"],
    FORBID_ATTR: ["srcdoc", "formaction"],
  });
}
