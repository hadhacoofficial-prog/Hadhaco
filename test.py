from pathlib import Path
from base64 import b64encode

from jinja2 import Environment, FileSystemLoader
from livereload import Server

# ======================================================
# PATHS
# ======================================================

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_DIR = BASE_DIR / "Backend" / "app" / "templates"
TEMPLATE_NAME = "packing_slip.html"

OUTPUT_FILE = BASE_DIR / "preview.html"

LOGO_FILE = TEMPLATE_DIR / "hadha-logo.png"

# ======================================================
# JINJA
# ======================================================

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=False,
)

# ======================================================
# FAKE DATA
# ======================================================

company = {
    "name": "Hadha Silver Jewellery",
    "tagline": "Crafted with Elegance",
    "address_line1": "2nd Floor, Jubilee Hills",
    "address_line2": "Road No. 36",
    "city": "Hyderabad",
    "state": "Telangana",
    "postal_code": "500033",
    "country": "India",
    "phone": "+91 9876543210",
    "support_email": "support@hadha.co",
    "website": "https://hadha.co",
}

order = {
    "order_number": "HD250628001",
    "created_at": "28 Jun 2026",
    "shipping_provider": "DeliveryOne",
    "tracking_number": "DO123456789IN",
    "shipping_full_name": "Hari Sai Kumar",
    "shipping_line1": "Flat 302, Sri Lakshmi Residency",
    "shipping_line2": "Madhapur",
    "shipping_landmark": "Near Inorbit Mall",
    "shipping_city": "Hyderabad",
    "shipping_state": "Telangana",
    "shipping_postal": "500081",
    "shipping_phone": "+91 9876543210",
    "shipping_alternate_phone": "+91 9123456780",
    "subtotal": 7498.00,
    "tax_amount": 0.00,
    "shipping_charge": 0.00,
    "discount": 499.00,
    "total": 6999.00,
}

items = [
    {
        "product_name": "925 Silver Floral Necklace",
        "variant_name": "18 Inch",
        "product_sku": "HD-NCK-001",
        "quantity": 1,
        "line_total": 3499.00,
    },
    {
        "product_name": "925 Silver Butterfly Earrings",
        "variant_name": "Rose Gold Finish",
        "product_sku": "HD-ERG-021",
        "quantity": 2,
        "line_total": 3000.00,
    },
    {
        "product_name": "925 Silver Adjustable Ring",
        "variant_name": "Size Adjustable",
        "product_sku": "HD-RNG-105",
        "quantity": 1,
        "line_total": 999.00,
    },
]

# ======================================================
# HELPERS
# ======================================================

def get_logo_data_uri():
    if not LOGO_FILE.exists():
        print("Logo not found:", LOGO_FILE)
        return ""

    mime = "image/png"

    encoded = b64encode(LOGO_FILE.read_bytes()).decode()

    return f"data:{mime};base64,{encoded}"


def build():
    print("Rendering template...")

    html = env.get_template(TEMPLATE_NAME).render(
        company=company,
        order=order,
        items=items,
        logo_data_uri=get_logo_data_uri(),
    )

    OUTPUT_FILE.write_text(html, encoding="utf-8")

    print("Preview updated:", OUTPUT_FILE)


# ======================================================
# INITIAL BUILD
# ======================================================

build()

# ======================================================
# LIVE RELOAD
# ======================================================

server = Server()

server.watch(str(TEMPLATE_DIR / TEMPLATE_NAME), build)

server.serve(
    root=str(BASE_DIR),
    host="127.0.0.1",
    port=5500,
    open_url_delay=True,
)