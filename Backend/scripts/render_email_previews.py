"""Render every default notification template with realistic sample data.

Usage (from Backend/):
    hadha/Scripts/python.exe scripts/render_email_previews.py

Writes one HTML file per email template, one .txt per WhatsApp template, and
an interactive gallery.html to scripts/email_previews/. Serve the directory
with any static server (or the "email-previews" entry in .claude/launch.json)
to review the designs in a browser, including dark mode and mobile widths.

Rendering uses the exact sandboxed Jinja environments the NotificationService
uses in production, so a template that renders here renders in production.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jinja2.sandbox import SandboxedEnvironment  # noqa: E402

from app.modules.notifications.branding import get_brand_context  # noqa: E402
from app.modules.notifications.emails.catalog import (  # noqa: E402
    EMAIL_TEMPLATES,
    WHATSAPP_TEMPLATES,
)

OUT = Path(__file__).parent / "email_previews"

env_html = SandboxedEnvironment(autoescape=True)
env_text = SandboxedEnvironment(autoescape=False)

# In production item.image_url is the real product photo snapshotted onto the
# order line. Previews use self-contained SVG stand-ins (data: URIs render in
# the sandboxed gallery too) so the image layout — not the monogram fallback —
# is what gets reviewed.
_RING_IMG = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E"
    "%3Crect width='160' height='160' fill='%23ffffff'/%3E"
    "%3Ccircle cx='80' cy='92' r='36' fill='none' stroke='%23c3c8cc' stroke-width='9'/%3E"
    "%3Ccircle cx='80' cy='44' r='11' fill='%23c99846'/%3E%3C/svg%3E"
)
_ANKLET_IMG = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E"
    "%3Crect width='160' height='160' fill='%23ffffff'/%3E"
    "%3Cpath d='M20 70 Q80 130 140 70' fill='none' stroke='%23c3c8cc' "
    "stroke-width='7' stroke-dasharray='2 10' stroke-linecap='round'/%3E"
    "%3Ccircle cx='80' cy='100' r='7' fill='%23c99846'/%3E%3C/svg%3E"
)

SAMPLE_ITEMS = [
    {
        "name": "Aria Silver Ring",
        "sku": "HD-RING-014",
        "variant": "Size 7 · Rose Polish",
        "quantity": 1,
        "unit_price": "Rs. 1,299.00",
        "line_total": "Rs. 1,299.00",
        "image_url": _RING_IMG,
        "product_url": "https://hadha.co/products/aria-silver-ring",
    },
    {
        "name": "Luna Anklet",
        "sku": "HD-ANK-002",
        "variant": "",
        "quantity": 2,
        "unit_price": "Rs. 899.00",
        "line_total": "Rs. 1,798.00",
        "image_url": _ANKLET_IMG,
        "product_url": "https://hadha.co/products/luna-anklet",
    },
]

SAMPLE = {
    **get_brand_context(),
    "full_name": "Priya Sharma",
    "customer_name": "Priya",
    "order_number": "HD10023",
    "order_date": "15 Jul 2026",
    "order_url": "https://hadha.co/account?tab=orders",
    "payment_method_label": "Paid Online (Razorpay)",
    "payment_status_label": "Paid ✓",
    "estimated_delivery": "19 Jul 2026",
    "shipping_provider_label": "Delhivery",
    "tracking_number": "DL4429871650",
    "tracking_url": "https://www.delhivery.com/track/DL4429871650",
    "awb": "DL4429871650",
    "items": SAMPLE_ITEMS,
    "order_subtotal": "Rs. 3,097.00",
    "order_discount": "Rs. 300.00",
    "coupon_code": "FESTIVE10",
    "order_shipping": "",
    "order_tax": "Rs. 92.91",
    "order_total": "Rs. 2,889.91",
    "order_savings": "Rs. 300.00",
    "complimentary_gift": "silver polishing cloth",
    "shipping_name": "Priya Sharma",
    "shipping_phone": "+91 98765 43210",
    "shipping_address_lines": (
        "221B Residency Road, Apt 4, Near City Mall, Bengaluru, Karnataka, 560025"
    ),
    "billing_name": "Priya Sharma",
    "billing_address_lines": (
        "221B Residency Road, Apt 4, Bengaluru, Karnataka, 560025"
    ),
    "timeline_stage": 1,
    "cancellation_reason": "requested by customer",
    "total": "2,889.91",
    "amount": "2,889.91",
    "reason": "card declined by issuing bank",
    "refund_id": "rfnd_QX81jd72Ma",
    "admin_order_url": "http://localhost:3001/orders/9c1e2b3a-7f4d-4a1e-8b2c-5d6e7f8a9b0c",
    "item_count": 2,
    "old_status": "confirmed",
    "new_status": "processing",
}

# Timeline stage shown per email so each preview highlights its own step.
STAGE = {
    "order_confirmation_email": 1,
    "order_confirmed_email": 2,
    "order_processing_email": 2,
    "order_packed_email": 3,
    "order_shipped_email": 4,
    "order_delivered_email": 5,
}

GROUPS = {
    "user_registered": "Account",
    "payment_captured": "Payments & Refunds",
    "payment_failed": "Payments & Refunds",
    "refund_created": "Payments & Refunds",
    "refund_processed": "Payments & Refunds",
    "review_request": "Engagement",
    "abandoned_cart": "Engagement",
    "refund_failed_admin_alert": "Admin",
}

_GALLERY_SHELL = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hadha.co Notification Previews</title>
<style>
:root{
  --ink:#1c1b1a; --paper:#f0ede8; --card:#ffffff; --champagne:#c99846;
  --muted:#6b6560; --border:#e2dcd2; --active:#f5efe6; --chip:#efe9df;
}
@media (prefers-color-scheme: dark){:root{
  --ink:#f0ece6; --paper:#161514; --card:#201e1c; --champagne:#d8ac5e;
  --muted:#a89f96; --border:#37332f; --active:#2b2723; --chip:#2b2723;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:14px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.app{display:flex;min-height:100vh}
nav{width:248px;flex:none;border-right:1px solid var(--border);padding:20px 0 40px;
  position:sticky;top:0;height:100vh;overflow-y:auto}
.brand{padding:4px 20px 16px;border-bottom:1px solid var(--border)}
.brand b{font-family:Georgia,serif;font-weight:normal;letter-spacing:3px;font-size:17px}
.brand small{display:block;color:var(--champagne);letter-spacing:1.5px;font-size:10px;
  text-transform:uppercase;margin-top:2px}
.grp{margin:18px 0 4px;padding:0 20px;font-size:10px;letter-spacing:1.6px;
  text-transform:uppercase;color:var(--muted)}
nav button{display:block;width:100%;text-align:left;padding:7px 20px;border:0;
  background:none;color:var(--ink);font:inherit;cursor:pointer;
  border-left:3px solid transparent}
nav button:hover{background:var(--active)}
nav button.on{background:var(--active);border-left-color:var(--champagne);font-weight:600}
nav button:focus-visible{outline:2px solid var(--champagne);outline-offset:-2px}
main{flex:1;padding:22px 28px 60px;min-width:0}
.bar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:14px}
.subject{font-weight:600;font-size:15px;flex:1;min-width:200px}
.subject span{display:block;font-size:11px;color:var(--muted);font-weight:400;
  letter-spacing:1px;text-transform:uppercase;margin-bottom:2px}
.widths{display:flex;gap:6px}
.widths button{border:1px solid var(--border);background:var(--card);color:var(--muted);
  border-radius:14px;padding:4px 14px;font:12px inherit;cursor:pointer}
.widths button.on{border-color:var(--champagne);color:var(--champagne);font-weight:600}
.stage{display:flex;justify-content:center}
iframe{width:640px;max-width:100%;height:80vh;border:1px solid var(--border);
  border-radius:10px;background:#f7f5f2;transition:width .2s ease}
iframe.mobile{width:391px}
.wa{max-width:420px;margin:24px auto;background:var(--card);
  border:1px solid var(--border);border-radius:14px;padding:20px}
.wa .bubble{background:var(--chip);border-radius:4px 14px 14px 14px;padding:12px 14px;
  white-space:pre-wrap;font-size:13.5px}
.wa .meta{font-size:11px;color:var(--muted);margin-bottom:8px;letter-spacing:1px;
  text-transform:uppercase}
@media (max-width:760px){.app{flex-direction:column}
  nav{width:100%;height:auto;position:static}}
@media (prefers-reduced-motion: reduce){iframe{transition:none}}
</style></head><body>
<div class="app">
<nav id="nav"><div class="brand"><b>HADHA.CO</b>
<small>Notification previews · sample order HD10023</small></div></nav>
<main>
  <div class="bar">
    <div class="subject" id="subject"></div>
    <div class="widths" id="widths" hidden>
      <button id="wDesk" class="on">Desktop 600</button>
      <button id="wMob">Mobile 375</button>
    </div>
  </div>
  <div class="stage" id="stage"></div>
</main>
</div>
<script>
const DATA = __DATA__;
const nav = document.getElementById('nav');
const stage = document.getElementById('stage');
const subject = document.getElementById('subject');
const widths = document.getElementById('widths');
let mobile = false;
for (const g of [...new Set(DATA.map(d => d.group))]) {
  const h = document.createElement('div'); h.className = 'grp'; h.textContent = g;
  nav.appendChild(h);
  for (const d of DATA.filter(x => x.group === g)) {
    const b = document.createElement('button');
    b.textContent = d.label; b.dataset.id = d.id;
    b.onclick = () => show(d.id);
    nav.appendChild(b);
  }
}
function show(id) {
  const d = DATA.find(x => x.id === id);
  for (const b of nav.querySelectorAll('button'))
    b.classList.toggle('on', b.dataset.id === id);
  if (d.kind === 'email') {
    widths.hidden = false;
    subject.innerHTML = '<span>Subject</span>';
    subject.appendChild(document.createTextNode(d.subject));
    const f = document.createElement('iframe');
    f.className = mobile ? 'mobile' : '';
    f.setAttribute('sandbox', '');
    f.srcdoc = d.content;
    f.title = d.label;
    stage.replaceChildren(f);
  } else {
    widths.hidden = true;
    subject.innerHTML = '<span>WhatsApp template</span>';
    subject.appendChild(document.createTextNode(d.label));
    const w = document.createElement('div'); w.className = 'wa';
    w.innerHTML = '<div class="meta">Hadha.co · WhatsApp Business</div>';
    const bub = document.createElement('div'); bub.className = 'bubble';
    bub.textContent = d.content;
    w.appendChild(bub);
    stage.replaceChildren(w);
  }
}
document.getElementById('wDesk').onclick = e => setW(false, e.target);
document.getElementById('wMob').onclick = e => setW(true, e.target);
function setW(m, btn) {
  mobile = m;
  for (const b of widths.querySelectorAll('button')) b.classList.remove('on');
  btn.classList.add('on');
  const f = stage.querySelector('iframe'); if (f) f.className = m ? 'mobile' : '';
}
show(DATA[0].id);
</script></body></html>"""


def main() -> int:
    OUT.mkdir(exist_ok=True)
    (OUT / ".gitignore").write_text("*\n", encoding="utf-8")

    failures: list[tuple[str, Exception]] = []
    entries: list[dict[str, str]] = []

    for tpl in EMAIL_TEMPLATES:
        ctx = {
            **SAMPLE,
            "timeline_stage": STAGE.get(tpl.name, SAMPLE["timeline_stage"]),
        }
        try:
            subject = env_text.from_string(tpl.subject or "").render(**ctx)
            html = env_html.from_string(tpl.body).render(**ctx)
            (OUT / f"{tpl.name}.html").write_text(html, encoding="utf-8")
            entries.append(
                {
                    "id": tpl.name,
                    "label": tpl.name.replace("_email", "").replace("_", " ").title(),
                    "group": GROUPS.get(tpl.event_type, "Orders"),
                    "kind": "email",
                    "subject": subject,
                    "content": html,
                }
            )
            print(f"OK  {tpl.name:38s} subject: {subject}")
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append((tpl.name, exc))
            print(f"FAIL {tpl.name}: {exc}")

    for tpl in WHATSAPP_TEMPLATES:
        try:
            body = env_text.from_string(tpl.body).render(**SAMPLE)
            (OUT / f"{tpl.name}.txt").write_text(body, encoding="utf-8")
            entries.append(
                {
                    "id": tpl.name,
                    "label": tpl.name.replace("_whatsapp", "")
                    .replace("_", " ")
                    .title(),
                    "group": "WhatsApp",
                    "kind": "whatsapp",
                    "subject": "",
                    "content": body,
                }
            )
            print(f"OK  {tpl.name}")
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append((tpl.name, exc))
            print(f"FAIL {tpl.name}: {exc}")

    data = json.dumps(entries).replace("</", "<\\/")
    (OUT / "gallery.html").write_text(
        _GALLERY_SHELL.replace("__DATA__", data), encoding="utf-8"
    )

    print(
        f"\n{len(EMAIL_TEMPLATES)} email + {len(WHATSAPP_TEMPLATES)} whatsapp "
        f"rendered to {OUT}; failures: {len(failures)}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
