from pathlib import Path
from base64 import b64encode

from jinja2 import Environment, FileSystemLoader
from livereload import Server

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_DIR = BASE_DIR / "Backend" / "app" / "templates"
TEMPLATE_NAME = "shipping_label.html"

OUTPUT_FILE = BASE_DIR / "shipping_label_preview.html"

LOGO_FILE = TEMPLATE_DIR / "hadha-logo.png"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=False,
)

company = {
    "name": "HADHA",
    "tagline": "JEWELLERY",
    "city": "Hyderabad",
    "state": "Telangana",
    "postal_code": "500033",
    "phone": "+91 9876543210",
    "support_email": "support@hadha.co",
    "website": "https://hadha.co",
}

order = {
    "order_number": "HD250628001",

    "shipping_full_name": "Hari Sai Kumar",
    "shipping_line1": "Flat 302, Sri Lakshmi Residency",
    "shipping_line2": "Madhapur",
    "shipping_landmark": "Near Inorbit Mall",
    "shipping_city": "Hyderabad",
    "shipping_state": "Telangana",
    "shipping_postal": "500081",
    "shipping_phone": "+91 9876543210",
    "shipping_alternate_phone": "+91 9123456780",
}


def get_logo_data_uri():
    if not LOGO_FILE.exists():
        return ""

    encoded = b64encode(LOGO_FILE.read_bytes()).decode()
    return f"data:image/png;base64,{encoded}"


def build():

    html = env.get_template(TEMPLATE_NAME).render(
        company=company,
        order=order,
        logo_data_uri=get_logo_data_uri(),
    )

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Updated -> {OUTPUT_FILE}")


build()

server = Server()

server.watch(str(TEMPLATE_DIR / TEMPLATE_NAME), build)

server.serve(
    root=str(BASE_DIR),
    host="127.0.0.1",
    port=5500,
    open_url="shipping_label_preview.html",
)