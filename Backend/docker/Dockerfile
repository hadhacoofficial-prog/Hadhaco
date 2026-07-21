FROM python:3.12-slim AS base

# Security: run as non-root
RUN groupadd --gid 1001 hadha && \
    useradd --uid 1001 --gid hadha --shell /bin/bash --create-home hadha

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Force IPv4 preference for DNS resolution (prevents IPv6 connection failures
# to external databases like Supabase when IPv6 is configured but non-functional).
# The default glibc policy table gives native IPv6 (::/0) label 3, while
# IPv4-mapped (::ffff:0:0/96) gets label 1. We also lower native IPv6 precedence
# so glibc sorts A records before AAAA records even when labels tie.
RUN echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf && \
    echo 'precedence ::/0            10' >> /etc/gai.conf

# ── Builder stage ──────────────────────────────────────────────────────────────
FROM base AS builder
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Production image ───────────────────────────────────────────────────────────
FROM base AS production
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=hadha:hadha . .

USER hadha

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
