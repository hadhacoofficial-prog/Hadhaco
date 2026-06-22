# ── Dependency installer ───────────────────────────────────────────────────────
FROM node:20-slim AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

# ── Development ───────────────────────────────────────────────────────────────
FROM node:20-slim AS development

RUN groupadd --gid 1001 hadha && \
    useradd --uid 1001 --gid hadha --shell /bin/bash --create-home hadha

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-populate node_modules so the named volume is seeded on first run.
# The docker-compose volume mount at /app/node_modules takes precedence over
# the host bind-mount at /app, keeping the Docker-installed modules intact.
COPY --from=deps --chown=hadha:hadha /app/node_modules /app/node_modules

USER hadha

# @lovable.dev/vite-tanstack-config starts the Nitro dev server on port 8080.
# This is confirmed by "Local: http://localhost:8080/" in the Vite startup log.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080 || exit 1

CMD ["npm", "run", "dev", "--", "--host"]

# ── Production builder ─────────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY . .

# NITRO_PRESET=node produces a standalone Node.js server in .output/
# The vercel preset (default) is incompatible with Docker deployments.
ENV NITRO_PRESET=node
RUN npm run build

# ── Production ────────────────────────────────────────────────────────────────
FROM node:20-slim AS production

RUN groupadd --gid 1001 hadha && \
    useradd --uid 1001 --gid hadha --shell /bin/bash --create-home hadha

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder --chown=hadha:hadha /app/.output ./.output

USER hadha

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

CMD ["node", ".output/server/index.mjs"]
