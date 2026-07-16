"""Email design system — a faithful, email-safe recreation of the storefront.

Every token below is extracted from the storefront, not invented:

- Colors: `Frontend_whole/packages/shared-ui/src/globals.css` (:root oklch
  tokens converted to sRGB hex; .dark tokens drive the dark-mode overrides).
- Typography: Cinzel (display/CTAs), Cormorant Garamond (decorative), Inter
  (body) — same stacks as `--font-serif-display/--font-serif-body/--font-sans`.
- Radius: `--radius: 0rem` — the storefront is sharp-cornered; so are these
  emails.
- CTA style: ProductCard "Add to cart" bar — solid primary, Cinzel,
  11px/uppercase/letter-spacing .24em (`tracking-[0.24em]`).
- Badges: ProductCard badge — solid primary, 10px Cinzel, tracking .22em.
- Header mirrors `site/Header.tsx`: cream utility bar with the brand motto,
  centered logo/wordmark, bordered nav row.
- Footer mirrors `site/Footer.tsx`: dark slate (foreground token) panel, cream
  70% text, gold accents, square bordered social boxes, Shopping/Company link
  columns, bottom legal bar.
- Prices: "Rs. 1,299.00" — matches `formatINR` in packages/shared-utils.

Each function returns an HTML fragment that may contain Jinja2 placeholders;
`catalog.py` composes fragments into complete standalone documents (the admin
Template Editor previews raw bodies client-side, so no {% extends %}).

Email-engineering: 600px tables, inline CSS, MSO conditionals, hidden
preheader, bulletproof table CTAs, mobile + dark-mode <style> enhancements,
alt text everywhere, styled fallback when a product image is missing.
"""

from __future__ import annotations

# ── Storefront tokens (globals.css :root, oklch → hex) ────────────────────────

PAGE_BG = "#faf6f1"  # --background
INK = "#1f2733"  # --foreground
CARD = "#ffffff"  # --card
NAVY = "#21334f"  # --primary
NAVY_FG = "#faf8f5"  # --primary-foreground
SILVER = "#c3c8cc"  # --secondary
MUTED = "#f1ece4"  # --muted
MUTED_FG = "#575e68"  # --muted-foreground
GOLD = "#c99846"  # --accent
GOLD_FG = "#faf8f5"  # --accent-foreground
DESTRUCTIVE = "#be2323"  # --destructive
BORDER = "#cdd1d6"  # --border
INPUT = "#e1e5ea"  # --input

# --gradient-luxury (navy) / --gradient-gold — exact hex stops from globals.css
GRADIENT_LUXURY = "linear-gradient(135deg,#2e4a6e 0%,#243b5a 60%,#1b2f4a 100%)"
GRADIENT_GOLD = "linear-gradient(135deg,#e1b868 0%,#c89b3c 50%,#9e7a2c 100%)"
LUXURY_SOLID = "#243b5a"  # gradient midpoint fallback for Outlook

# Tints of storefront tokens (token color over the cream background — no new
# hues, only opacity mixes the storefront itself uses, e.g. bg-foreground/…).
DESTRUCTIVE_TINT = "#f6e7e2"  # destructive @ ~10% over background
GOLD_TINT = "#f6ecda"  # accent @ ~15% over background
FOOTER_TEXT = "#c3c4c7"  # background @ 70% over foreground (text-background/70)
FOOTER_FAINT = "#9fa2a8"  # background @ 60%
FOOTER_BORDER = "#454d59"  # background @ 15% border (border-background/15)

# .dark tokens (oklch → hex) for the prefers-color-scheme enhancement
DARK_BG = "#0a121c"
DARK_CARD = "#111b28"
DARK_FG = "#e4ecf3"
DARK_MUTED = "#1a2532"
DARK_MUTED_FG = "#97a7b3"
DARK_BORDER = "#2b3542"

# ── Storefront typography (--font-serif-display / --font-sans) ────────────────

DISPLAY = "'Cinzel','Times New Roman',Georgia,serif"
DECOR = "'Cormorant Garamond',Georgia,'Times New Roman',serif"
BODY = "'Inter','Helvetica Neue',Helvetica,Arial,sans-serif"

# ProductCard CTA / badge letterforms: tracking-[0.24em] and tracking-[0.22em]
TRACK_CTA = "letter-spacing:0.24em"
TRACK_BADGE = "letter-spacing:0.22em"
TRACK_LABEL = "letter-spacing:0.18em"

SHADOW_PREMIUM = "0 18px 50px -24px rgba(31,39,51,0.3)"  # --shadow-premium


# ── Document shell ─────────────────────────────────────────────────────────────


def document(*, title: str, preheader: str, body_html: str) -> str:
    return (
        "<!DOCTYPE html>"
        '<html lang="en" dir="auto" xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="X-UA-Compatible" content="IE=edge">'
        '<meta name="color-scheme" content="light dark">'
        '<meta name="supported-color-schemes" content="light dark">'
        f"<title>{title}</title>"
        "<!--[if mso]><noscript><xml><o:OfficeDocumentSettings>"
        "<o:PixelsPerInch>96</o:PixelsPerInch>"
        "</o:OfficeDocumentSettings></xml></noscript><![endif]-->"
        "<style>"
        # Same Google faces the storefront loads; clients that block remote
        # fonts fall back to the serif/sans stacks inlined on every element.
        "@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;600;700"
        "&family=Cormorant+Garamond:ital,wght@0,500;1,500&family=Inter:wght@400;500;600;700"
        "&display=swap');"
        "body,table,td,a{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}"
        "img{-ms-interpolation-mode:bicubic;border:0;outline:none;text-decoration:none;}"
        "table{border-collapse:collapse!important;}"
        f"body{{margin:0!important;padding:0!important;width:100%!important;background:{PAGE_BG};}}"
        "a{color:inherit;}"
        "@media only screen and (max-width:620px){"
        ".container{width:100%!important;max-width:100%!important;}"
        ".px{padding-left:20px!important;padding-right:20px!important;}"
        ".stack{display:block!important;width:100%!important;max-width:100%!important;}"
        ".stack-pad{padding-left:0!important;padding-top:16px!important;}"
        ".hide-sm{display:none!important;}"
        ".btn a{display:block!important;width:auto!important;}"
        "}"
        "@media (prefers-color-scheme: dark){"
        f".dm-page{{background:{DARK_BG}!important;}}"
        f".dm-card{{background:{DARK_CARD}!important;}}"
        f".dm-well{{background:{DARK_MUTED}!important;}}"
        f".dm-ink{{color:{DARK_FG}!important;}}"
        f".dm-muted{{color:{DARK_MUTED_FG}!important;}}"
        f".dm-border{{border-color:{DARK_BORDER}!important;}}"
        "}"
        "</style>"
        "</head>"
        f'<body class="dm-page" style="margin:0;padding:0;background:{PAGE_BG};">'
        '<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">'
        f"{preheader}" + "&nbsp;&zwnj;" * 40 + "</div>"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'class="dm-page" style="background:{PAGE_BG};">'
        '<tr><td align="center" style="padding:28px 12px;">'
        "<!--[if mso]>"
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0"><tr><td>'
        "<![endif]-->"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'class="container dm-card" '
        f'style="max-width:600px;background:{CARD};border:1px solid {BORDER};'
        f'box-shadow:{SHADOW_PREMIUM};">'
        f"{body_html}"
        "</table>"
        "<!--[if mso]></td></tr></table><![endif]-->"
        "</td></tr></table>"
        "</body></html>"
    )


# ── Header — quiet luxury: just the mark. Wordmark + tagline, hairline rule ────


def header() -> str:
    return (
        "<tr><td>"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'class="dm-well" style="background:{PAGE_BG};">'
        f'<tr><td align="center" class="dm-border" '
        f'style="padding:30px 24px 26px;border-bottom:1px solid {BORDER};">'
        f'<a href="{{{{ frontend_url }}}}" style="text-decoration:none;">'
        "{% if brand_logo_url %}"
        '<img src="{{ brand_logo_url }}" alt="{{ brand_name }}" height="56" '
        'style="height:56px;max-width:260px;display:block;margin:0 auto;">'
        "{% else %}"
        f'<span class="dm-ink" style="font-family:{DISPLAY};font-weight:600;'
        f'font-size:30px;letter-spacing:0.14em;color:{INK};text-transform:uppercase;">'
        "{{ brand_short_name }}</span>"
        f'<br><span style="font-family:{DISPLAY};font-size:10px;letter-spacing:0.3em;'
        f'text-transform:uppercase;color:{GOLD};">{{{{ brand_tagline }}}}</span>'
        "{% endif %}"
        "</a></td></tr>"
        "</table>"
        "</td></tr>"
    )


# ── Footer — quiet luxury: brand, contact, help, legal. Nothing else. ──────────


def footer() -> str:
    social_link = (
        f'<a href="{{href}}" style="font-family:{DISPLAY};font-size:11px;'
        f"letter-spacing:0.22em;text-transform:uppercase;color:{GOLD};"
        'text-decoration:none;">{label}</a>'
    )
    dot = f'<span style="color:{FOOTER_BORDER};">&nbsp;&nbsp;·&nbsp;&nbsp;</span>'

    return (
        "<tr><td>"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{INK};">'
        # Brand mark — centered
        '<tr><td align="center" class="px" style="padding:40px 40px 0;">'
        "{% if brand_logo_dark_url %}"
        '<img src="{{ brand_logo_dark_url }}" alt="{{ brand_name }}" height="48" '
        'style="height:48px;max-width:220px;display:block;margin:0 auto;">'
        "{% else %}"
        f'<span style="font-family:{DISPLAY};font-weight:600;font-size:22px;'
        f'letter-spacing:0.14em;text-transform:uppercase;color:{NAVY_FG};">'
        "{{ brand_short_name }}</span>"
        f'<br><span style="font-family:{DISPLAY};font-size:10px;letter-spacing:0.3em;'
        f'text-transform:uppercase;color:{GOLD};">{{{{ brand_tagline }}}}</span>'
        "{% endif %}"
        f'<p style="margin:16px auto 0;font-family:{DECOR};font-style:italic;'
        f"font-size:15px;line-height:1.7;color:{FOOTER_TEXT};max-width:380px;"
        '">{{ brand_description }}</p>'
        "</td></tr>"
        # Contact: email · phone · website
        '<tr><td align="center" class="px" style="padding:22px 40px 0;">'
        f'<span style="font-family:{BODY};font-size:13px;line-height:2;color:{FOOTER_TEXT};">'
        f'<a href="mailto:{{{{ support_email }}}}" style="color:{FOOTER_TEXT};'
        'text-decoration:none;">{{ support_email }}</a>'
        "{% if support_phone %}" + dot + f'<a href="tel:{{{{ support_phone }}}}" '
        f'style="color:{FOOTER_TEXT};text-decoration:none;">{{{{ support_phone }}}}</a>'
        "{% endif %}" + dot + f'<a href="{{{{ frontend_url }}}}" '
        f'style="color:{FOOTER_TEXT};text-decoration:none;">{{{{ website_label }}}}</a>'
        "</span></td></tr>"
        # Social — spaced gold wordmarks, no boxes
        '<tr><td align="center" style="padding:18px 40px 0;">'
        "{% if social_instagram %}"
        + social_link.format(href="{{ social_instagram }}", label="Instagram")
        + "{% endif %}"
        "{% if social_youtube %}{% if social_instagram %}"
        + dot
        + "{% endif %}"
        + social_link.format(href="{{ social_youtube }}", label="YouTube")
        + "{% endif %}"
        "{% if social_facebook %}"
        "{% if social_instagram or social_youtube %}"
        + dot
        + "{% endif %}"
        + social_link.format(href="{{ social_facebook }}", label="Facebook")
        + "{% endif %}"
        "</td></tr>"
        # Need help?
        '<tr><td align="center" class="px" style="padding:24px 40px 0;">'
        f'<span style="font-family:{BODY};font-size:12px;color:{FOOTER_FAINT};">'
        "Need help?&nbsp;&nbsp;"
        f'<a href="{{{{ contact_url }}}}" style="color:{NAVY_FG};'
        'text-decoration:underline;">Contact Support</a>'
        + dot
        + f'<a href="{{{{ orders_url }}}}" style="color:{NAVY_FG};'
        'text-decoration:underline;">Track Order</a>'
        "</span></td></tr>"
        # Legal
        '<tr><td align="center" class="px" style="padding:22px 40px 32px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-top:1px solid {FOOTER_BORDER};"><tr>'
        f'<td align="center" style="padding-top:16px;font-family:{BODY};font-size:11px;'
        f'line-height:1.9;color:{FOOTER_FAINT};">'
        f'<a href="{{{{ privacy_url }}}}" style="color:{FOOTER_FAINT};">Privacy</a>'
        + dot
        + f'<a href="{{{{ terms_url }}}}" style="color:{FOOTER_FAINT};">Terms</a><br>'
        "© {{ current_year }} {{ brand_legal_name }}. All rights reserved."
        "</td></tr></table></td></tr>"
        "</table>"
        "</td></tr>"
    )


# ── Content primitives ─────────────────────────────────────────────────────────


def hero(*, badge_text: str, badge_bg: str, title: str, subtitle: str) -> str:
    """Status hero. Badge = ProductCard badge treatment: solid ground, Cinzel,
    10px, tracking .22em, sharp corners. Headline = site h1..h4 treatment:
    Cinzel 600."""
    return (
        f'<tr><td class="px" align="center" style="padding:38px 40px 8px;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="background:{badge_bg};padding:6px 14px;">'
        f'<span style="font-family:{DISPLAY};font-size:10px;font-weight:600;'
        f'color:{NAVY_FG};{TRACK_BADGE};text-transform:uppercase;">{badge_text}</span>'
        "</td></tr></table>"
        f'<h1 class="dm-ink" style="margin:20px 0 10px;font-family:{DISPLAY};'
        f"font-weight:600;font-size:25px;line-height:1.35;letter-spacing:0.01em;"
        f'color:{INK};">{title}</h1>'
        f'<p class="dm-muted" style="margin:0;font-family:{BODY};font-size:14px;'
        f'line-height:1.75;color:{MUTED_FG};">{subtitle}</p>'
        "</td></tr>"
    )


def paragraph(text: str, *, align: str = "left") -> str:
    return (
        f'<tr><td class="px" style="padding:8px 40px;" align="{align}">'
        f'<p class="dm-muted" style="margin:0;font-family:{BODY};font-size:14px;'
        f'line-height:1.8;color:{MUTED_FG};">{text}</p></td></tr>'
    )


def spacer(height: int = 24) -> str:
    return (
        f'<tr><td style="height:{height}px;font-size:0;line-height:0;">&nbsp;</td></tr>'
    )


def divider() -> str:
    return (
        f'<tr><td class="px" style="padding:20px 40px;">'
        f'<div class="dm-border" style="border-top:1px solid {BORDER};font-size:0;">&nbsp;</div>'
        "</td></tr>"
    )


def cta_block(
    primary: tuple[str, str],
    secondary: tuple[str, str] | None = None,
    *,
    variant: str = "primary",
) -> str:
    """One decision per email: a single large primary button (storefront
    ProductCard CTA language — Cinzel, uppercase, tracking .24em, sharp),
    with an optional quiet secondary text link underneath.

    variant: "primary" (navy) | "gold" (accent).
    """
    label, href = primary
    if variant == "gold":
        td_style = f"background:{GOLD};background-image:{GRADIENT_GOLD};"
        a_style = f"color:{GOLD_FG};"
    else:
        td_style = f"background:{NAVY};background-image:{GRADIENT_LUXURY};"
        a_style = f"color:{NAVY_FG};"
    secondary_html = ""
    if secondary:
        s_label, s_href = secondary
        secondary_html = (
            f'<div style="padding-top:16px;">'
            f'<a href="{s_href}" class="dm-muted" style="font-family:{BODY};'
            f"font-size:12px;letter-spacing:0.08em;color:{MUTED_FG};"
            f'text-decoration:underline;text-underline-offset:3px;">{s_label}</a></div>'
        )
    return (
        '<tr><td class="px" align="center" style="padding:28px 40px 8px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr>'
        f'<td class="btn" align="center" style="{td_style}">'
        f'<a href="{href}" style="display:block;padding:16px 28px;'
        f"font-family:{DISPLAY};font-size:12px;font-weight:600;{TRACK_CTA};"
        f'text-transform:uppercase;text-decoration:none;{a_style}">{label}</a></td>'
        "</tr></table>"
        f"{secondary_html}"
        "</td></tr>"
    )


# ── Order components ───────────────────────────────────────────────────────────


def order_meta_grid() -> str:
    def row(label: str, value: str, cond: str | None = None) -> str:
        cell = (
            f'<tr><td class="dm-muted" style="padding:7px 0;font-family:{BODY};'
            f'font-size:13px;color:{MUTED_FG};width:45%;">{label}</td>'
            f'<td class="dm-ink" style="padding:7px 0;font-family:{BODY};font-size:13px;'
            f'color:{INK};font-weight:600;" align="right">{value}</td></tr>'
        )
        return f"{{% if {cond} %}}{cell}{{% endif %}}" if cond else cell

    rows = (
        row("Order number", "{{ order_number }}")
        + row("Order date", "{{ order_date }}", "order_date")
        + row("Customer", "{{ customer_name }}", "customer_name")
        + row("Payment method", "{{ payment_method_label }}", "payment_method_label")
        + row("Payment status", "{{ payment_status_label }}", "payment_status_label")
        + row("Estimated delivery", "{{ estimated_delivery }}", "estimated_delivery")
        + row("Courier", "{{ shipping_provider_label }}", "shipping_provider_label")
        + row(
            "Tracking number",
            '{% if tracking_url %}<a href="{{ tracking_url }}" '
            f'style="color:{GOLD};">{{{{ tracking_number }}}}</a>'
            "{% else %}{{ tracking_number }}{% endif %}",
            "tracking_number",
        )
    )
    return (
        '<tr><td class="px" style="padding:16px 40px 0;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'class="dm-well" style="background:{MUTED};">'
        '<tr><td style="padding:18px 24px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'
        "</td></tr></table></td></tr>"
    )


def product_items() -> str:
    """Product rows in the storefront card language: white image tile
    (object-contain feel), Inter medium title, muted variant/SKU line, bold
    Inter price, sharp corners, hairline borders."""
    return (
        "{% if items %}"
        '<tr><td class="px" style="padding:22px 40px 0;">'
        f'<span class="dm-ink" style="font-family:{DISPLAY};font-weight:600;'
        f'font-size:16px;letter-spacing:0.04em;color:{INK};">Your Items</span>'
        "</td></tr>"
        "{% for item in items %}"
        '<tr><td class="px" style="padding:12px 40px 0;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'class="dm-border" style="border:1px solid {BORDER};">'
        '<tr><td style="padding:12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        '<td width="92" valign="top">'
        '{% if item.product_url %}<a href="{{ item.product_url }}">{% endif %}'
        "{% if item.image_url %}"
        '<img src="{{ item.image_url }}" alt="{{ item.name }}" width="80" height="80" '
        f'style="width:80px;height:80px;background:{CARD};display:block;'
        f'border:1px solid {INPUT};object-fit:contain;">'
        "{% else %}"
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td width="80" height="80" align="center" valign="middle" class="dm-well" '
        f'style="width:80px;height:80px;background:{MUTED};'
        f'font-family:{DECOR};font-size:26px;font-style:italic;color:{GOLD};">'
        "{{ item.name[:1] }}</td></tr></table>"
        "{% endif %}"
        "{% if item.product_url %}</a>{% endif %}"
        "</td>"
        '<td valign="top" style="padding-left:6px;">'
        "{% if item.product_url %}"
        '<a href="{{ item.product_url }}" style="text-decoration:none;">'
        "{% endif %}"
        f'<span class="dm-ink" style="font-family:{BODY};font-size:14px;font-weight:500;'
        f'color:{INK};line-height:1.5;">{{{{ item.name }}}}</span>'
        "{% if item.product_url %}</a>{% endif %}"
        f'<br><span class="dm-muted" style="font-family:{BODY};font-size:12px;'
        f'color:{MUTED_FG};line-height:1.8;">'
        "{% if item.variant %}{{ item.variant }} &nbsp;·&nbsp; {% endif %}"
        "SKU {{ item.sku }}<br>"
        "Qty {{ item.quantity }} &times; {{ item.unit_price }}"
        "</span>"
        "{% if item.product_url %}"
        f'<br><a href="{{{{ item.product_url }}}}" style="font-family:{BODY};'
        f"font-size:12px;color:{GOLD};text-decoration:none;"
        'letter-spacing:0.04em;">View Product &rarr;</a>'
        "{% endif %}"
        "</td>"
        '<td valign="top" align="right" width="90">'
        f'<span class="dm-ink" style="font-family:{BODY};font-size:14px;font-weight:700;'
        f'color:{INK};">{{{{ item.line_total }}}}</span></td>'
        "</tr></table>"
        "</td></tr></table>"
        "</td></tr>"
        "{% endfor %}"
        "{% endif %}"
    )


def order_summary() -> str:
    def srow(label: str, value: str, *, cond: str | None = None) -> str:
        cell = (
            f'<tr><td class="dm-muted" style="padding:5px 0;font-family:{BODY};'
            f'font-size:13px;color:{MUTED_FG};">{label}</td>'
            f'<td class="dm-muted" style="padding:5px 0;font-family:{BODY};'
            f'font-size:13px;color:{MUTED_FG};" align="right">{value}</td></tr>'
        )
        return f"{{% if {cond} %}}{cell}{{% endif %}}" if cond else cell

    return (
        "{% if order_total %}"
        '<tr><td class="px" style="padding:22px 40px 0;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'class="dm-well" style="background:{MUTED};">'
        '<tr><td style="padding:18px 24px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        + srow("Subtotal", "{{ order_subtotal }}")
        + srow(
            "Discount{% if coupon_code %} ({{ coupon_code }}){% endif %}",
            f'<span style="color:{GOLD};">&minus;{{{{ order_discount }}}}</span>',
            cond="order_discount",
        )
        + srow(
            "Shipping",
            "{% if order_shipping %}{{ order_shipping }}{% else %}"
            f'<span style="color:{GOLD};font-weight:700;">FREE</span>'
            "{% endif %}",
        )
        + srow("Tax (GST)", "{{ order_tax }}", cond="order_tax")
        + (
            f'<tr><td colspan="2" style="padding:8px 0 4px;">'
            f'<div class="dm-border" style="border-top:1px solid {BORDER};font-size:0;">&nbsp;</div>'
            "</td></tr>"
        )
        + (
            f'<tr><td class="dm-ink" style="padding:4px 0;font-family:{DISPLAY};'
            f"font-weight:600;font-size:14px;letter-spacing:0.06em;"
            f'text-transform:uppercase;color:{INK};">Total</td>'
            f'<td class="dm-ink" style="padding:4px 0;font-family:{BODY};font-size:18px;'
            f'font-weight:700;color:{INK};" align="right">{{{{ order_total }}}}</td></tr>'
        )
        + (
            "{% if order_savings %}"
            f'<tr><td colspan="2" align="center" style="padding:10px 0 0;">'
            f'<span style="font-family:{BODY};font-size:12px;color:{GOLD};'
            f'border:1px solid {GOLD};padding:4px 14px;display:inline-block;">'
            "You saved {{ order_savings }} on this order</span></td></tr>"
            "{% endif %}"
        )
        + (
            "{% if complimentary_gift %}"
            f'<tr><td colspan="2" align="center" style="padding:10px 0 0;">'
            f'<span style="font-family:{DECOR};font-style:italic;font-size:14px;'
            f'color:{GOLD};">Includes a complimentary {{{{ complimentary_gift }}}}</span></td></tr>'
            "{% endif %}"
        )
        + "</table></td></tr></table></td></tr>"
        "{% endif %}"
    )


def addresses() -> str:
    def col(title: str, lines: str, *, first: bool) -> str:
        cls = "stack" if first else "stack stack-pad"
        pad = "padding-right:8px;" if first else "padding-left:8px;"
        return (
            f'<td class="{cls}" width="50%" valign="top" style="{pad}">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'class="dm-well" style="background:{MUTED};">'
            '<tr><td style="padding:16px 20px;">'
            f'<span class="dm-muted" style="font-family:{DISPLAY};font-size:10px;'
            f"font-weight:600;color:{MUTED_FG};{TRACK_LABEL};"
            f'text-transform:uppercase;">{title}</span>'
            f'<p class="dm-muted" style="margin:8px 0 0;font-family:{BODY};font-size:13px;'
            f'line-height:1.8;color:{MUTED_FG};">{lines}</p>'
            "</td></tr></table></td>"
        )

    ship = col(
        "Shipping address",
        f'<span class="dm-ink" style="color:{INK};font-weight:600;">'
        "{{ shipping_name }}</span><br>"
        "{{ shipping_address_lines }}"
        "{% if shipping_phone %}<br>☎ {{ shipping_phone }}{% endif %}",
        first=True,
    )
    bill = col(
        "Billing address",
        f'<span class="dm-ink" style="color:{INK};font-weight:600;">'
        "{{ billing_name }}</span><br>"
        "{{ billing_address_lines }}",
        first=False,
    )
    return (
        "{% if shipping_address_lines %}"
        '<tr><td class="px" style="padding:22px 40px 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        + ship
        + "{% if billing_address_lines %}"
        + bill
        + "{% endif %}"
        + "</tr></table></td></tr>"
        "{% endif %}"
    )


TIMELINE_STAGES = ["Placed", "Confirmed", "Packed", "Shipped", "Delivered"]


def order_timeline() -> str:
    """5-step progress. Done steps take the gold accent; labels use the
    storefront's uppercase tracked micro-type. Sharp squares, not pills."""
    cells = []
    for idx, stage in enumerate(TIMELINE_STAGES, start=1):
        cells.append(
            f"{{% set done = timeline_stage and timeline_stage >= {idx} %}}"
            '<td align="center" valign="top" width="20%">'
            '<table role="presentation" cellpadding="0" cellspacing="0" align="center"><tr>'
            '<td width="26" height="26" align="center" valign="middle" '
            "{% if not done %}"
            'class="dm-well" '
            "{% endif %}"
            f'style="font-size:12px;font-weight:700;font-family:{BODY};'
            "{% if done %}"
            f"background:{GOLD};color:{GOLD_FG};"
            "{% else %}"
            f"background:{MUTED};color:{MUTED_FG};border:1px solid {BORDER};"
            "{% endif %}"
            '">{% if done %}✓{% else %}' + str(idx) + "{% endif %}</td>"
            "</tr></table>"
            f'<div style="font-family:{DISPLAY};font-size:9px;{TRACK_LABEL};'
            "text-transform:uppercase;padding-top:7px;"
            "{% if done %}"
            f"color:{GOLD};font-weight:600;"
            "{% else %}"
            f"color:{MUTED_FG};"
            "{% endif %}"
            f'">{stage}</div></td>'
        )
    return (
        "{% if timeline_stage %}"
        '<tr><td class="px" style="padding:28px 40px 4px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        + "".join(cells)
        + "</tr></table></td></tr>"
        "{% endif %}"
    )


def review_cta() -> str:
    """Post-delivery review prompt: gold-tinted panel with a star row and one
    Write-a-Review button per product, deep-linking to that product page's
    review section (item.review_url). Renders only when items are present."""
    stars = (
        f'<span style="font-size:20px;line-height:1;color:{GOLD};'
        'letter-spacing:6px;">★★★★★</span>'
    )
    item_row = (
        "{% if item.review_url %}"
        '<tr><td style="padding:7px 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td valign="middle" style="font-family:{BODY};font-size:13px;'
        f'font-weight:500;color:{INK};padding-right:12px;">{{{{ item.name }}}}'
        "{% if item.variant %}"
        f'<span style="color:{MUTED_FG};font-weight:400;"> — {{{{ item.variant }}}}</span>'
        "{% endif %}</td>"
        f'<td valign="middle" align="right" style="background:{GOLD};'
        f'background-image:{GRADIENT_GOLD};" width="150" class="btn">'
        f'<a href="{{{{ item.review_url }}}}" style="display:inline-block;'
        f"padding:10px 16px;font-family:{DISPLAY};font-size:10px;font-weight:600;"
        f"{TRACK_BADGE};text-transform:uppercase;text-decoration:none;"
        f'color:{GOLD_FG};white-space:nowrap;">Write a Review</a></td>'
        "</tr></table></td></tr>"
        "{% endif %}"
    )
    return (
        "{% if items %}"
        '<tr><td class="px" style="padding:22px 40px 0;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{GOLD_TINT};border:1px solid {GOLD};">'
        '<tr><td align="center" style="padding:22px 24px 6px;">'
        f"{stars}"
        f'<h2 class="dm-ink" style="margin:12px 0 6px;font-family:{DISPLAY};'
        f'font-weight:600;font-size:18px;letter-spacing:0.04em;color:{INK};">'
        "Enjoying your purchase?</h2>"
        f'<p style="margin:0;font-family:{BODY};font-size:13px;line-height:1.7;'
        f'color:{MUTED_FG};">We’d love to hear your thoughts — your feedback '
        "helps other customers choose with confidence.</p>"
        "</td></tr>"
        '<tr><td style="padding:10px 24px 20px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        "{% for item in items %}" + item_row + "{% endfor %}"
        "</table></td></tr>"
        "</table></td></tr>"
        "{% endif %}"
    )


def info_note(text: str, *, tone: str = "gold") -> str:
    """Callout strip: token-tinted ground with a solid accent edge (sharp)."""
    color, bg = (GOLD, GOLD_TINT) if tone == "gold" else (DESTRUCTIVE, DESTRUCTIVE_TINT)
    return (
        f'<tr><td class="px" style="padding:22px 40px 0;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{bg};border-left:3px solid {color};">'
        f'<tr><td style="padding:14px 20px;font-family:{BODY};font-size:13px;'
        f'line-height:1.7;color:{INK};">{text}</td></tr></table></td></tr>'
    )
