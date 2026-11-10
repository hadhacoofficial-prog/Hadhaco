# ── Base ──────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

RUN groupadd --gid 1001 hadha && \
    useradd --uid 1001 --gid hadha --shell /bin/bash --create-home hadha

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Prefer IPv4 over IPv6 for all outbound connections.
#
# Python/asyncpg resolves hostnames via glibc getaddrinfo(). By default,
# glibc sorts IPv6 (AAAA) addresses before IPv4 (A) addresses per RFC 6724.
# Docker's bridge network on WSL2/Windows has no IPv6 egress, so asyncpg's
# first connection attempt (IPv6) fails with EADDRNOTAVAIL or ENETUNREACH and
# — depending on how the DNS response is shaped — the IPv4 fallback may never
# be reached. Setting precedence 100 on the ::ffff:0:0/96 prefix (IPv4-mapped)
# causes getaddrinfo() to return IPv4 addresses first. asyncpg then succeeds
# on its first attempt without touching IPv6 at all.
RUN echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

# ── Builder ───────────────────────────────────────────────────────────────────
FROM base AS builder

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Source is mounted at runtime via docker-compose volume — nothing to COPY here.

USER hadha

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
