## Hadha.co — UX/UI Refinement Plan

Existing layout and architecture are preserved. Work is grouped into 5 rounds so each one ships cleanly and can be reviewed in the preview before the next.

---

### Round 1 — Brand foundation
1. **Color palette** — refresh `src/styles.css` tokens to the silver-blue palette (`#5E9FCB` primary, `#89B8D9` secondary, `#DCEAF5` accent, `#111827` luxury dark, `#FAFAF8` background). Add soft silver gradients and stronger CTA contrast tokens. Stay subtle, not bright.
2. **Typography** — load **Cinzel** + **Cormorant Garamond** (headings) and **Inter** (body) via Google Fonts. Wire to `--font-display` / `--font-serif` / `--font-sans`. Apply to existing heading scale.
3. **Header logo** — increase logo width (~2×) without changing navbar height; scale proportionally, premium presence.
4. **Footer logo** — replace favicon+text with the uploaded primary logo, large with proper spacing.

### Round 2 — Navigation + mega menu
5. **Main nav items** — replace current items with: Shop Men · Shop Women · Kids · Deals Of The Day · New Arrivals · Collections · About Us · Contact.
6. **Mega menu re-wire** — hover opens an elegant dropdown; subcategory clicks go **directly to `/search?cat=…&gender=…`** (the existing product listing route) instead of collection landing pages. One click less to product results.

### Round 3 — Homepage sections
7. **Shop By Collection (gender switcher)** — new premium section: 3 circular cards (Men / Women / Kids). Hover or click animates the panel below with that gender's category tiles (smooth fade + slide, no reload, mobile-friendly).
8. **New Arrivals** — dedicated horizontal-scroll slider section with "View All" → `/search?filter=new`.
9. **Our Craftsmanship video** — new section placed after Featured Collections: autoplay-muted-loop video banner with elegant overlay copy. CMS-controlled (wire to `useCms`). Uses a placeholder MP4 the user can swap.

### Round 4 — Conversion UX
10. **Return policy copy** — remove all "7-day return / Easy returns" claims; replace with "Return eligibility depends on the individual product." Show return info only when the product config allows it.
11. **WhatsApp FAB** — swap Lucide icon for the official WhatsApp SVG glyph, brand green `#25D366`, pulse ring, polished mobile placement.
12. **Welcome offer modal** — first-visit modal with the complimentary-gift copy (₹2000+ → sweet or hot snack). Dismissal persisted in `localStorage` (one-time).
13. **Search overlay** — replace `/search` page entry with fullscreen overlay opened by the header search icon: instant search, suggestions, trending, recent searches, product previews, popular categories. Desktop = right-side results panel, mobile = full screen.

### Round 5 — Auth + polish
14. **Google auth buttons** — add "Continue with Google" / "Sign up with Google" to login & register pages (premium styling, official Google G icon). Wires to a stub `signInWithGoogle()` ready to swap to Supabase OAuth.
15. **Micro-interactions** — hover lift on product cards, button shimmer on primary CTAs, image zoom on hover, route-loading skeleton polish, ornamental temple dividers between sections (subtle Indian luxury cue — not loud).

---

### Technical notes
- All copy and toggles (announcement, hero, promo, gender categories, craftsmanship video src) live in `useCms` and are editable from `/admin/cms`. Round 3 extends `useCms` with `craftsmanshipVideoUrl`, `craftsmanshipTitle`, `craftsmanshipBody`.
- Mega menu links use search params on the existing `/search` route (`?gender=men&cat=rings`), so no new routes / route-tree churn.
- Welcome modal + search overlay are global, rendered from `__root.tsx` next to `WhatsAppFab` so they appear on every page.
- Color/typography changes are token-only — components are not rewritten.
- Google auth button is a stub UI in this phase; Supabase OAuth provider config is a separate dashboard step the user owns.

Reply **"go"** to start Round 1, or tell me to reorder / drop anything.