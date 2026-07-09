# ── Dependency installer ────────────────────────────────────────────────────────
FROM node:20-slim AS deps

WORKDIR /app

# Copy root workspace manifest + lock file
COPY package.json package-lock.json ./
# Copy shared package manifests so npm ci can resolve workspaces
COPY packages/shared-types/package.json ./packages/shared-types/
COPY packages/shared-utils/package.json ./packages/shared-utils/
COPY packages/shared-api/package.json   ./packages/shared-api/
COPY packages/shared-ui/package.json    ./packages/shared-ui/
COPY packages/shared-media/package.json ./packages/shared-media/
COPY storefront/package.json            ./storefront/

RUN npm ci --legacy-peer-deps

# ── Development ──────────────────────────────────────────────────────────────────
FROM node:20-slim AS development

RUN groupadd --gid 1001 hadha && \
    useradd --uid 1001 --gid hadha --shell /bin/bash --create-home hadha

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=deps --chown=hadha:hadha /app/node_modules /app/node_modules

USER hadha

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080 || exit 1

CMD ["npm", "-w", "storefront", "run", "dev", "--", "--host"]

# ── Production builder ────────────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
COPY packages/shared-types/package.json ./packages/shared-types/
COPY packages/shared-utils/package.json ./packages/shared-utils/
COPY packages/shared-api/package.json   ./packages/shared-api/
COPY packages/shared-ui/package.json    ./packages/shared-ui/
COPY packages/shared-media/package.json ./packages/shared-media/
COPY storefront/package.json            ./storefront/

RUN npm ci --legacy-peer-deps

COPY packages/ ./packages/
COPY storefront/ ./storefront/

ARG VITE_API_BASE_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY

WORKDIR /app/storefront

RUN npx vite build --config vite.config.docker.ts

# ── Production ────────────────────────────────────────────────────────────────────
FROM node:20-slim AS production

RUN groupadd --gid 1001 hadha && \
    useradd --uid 1001 --gid hadha --shell /bin/bash --create-home hadha

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder --chown=hadha:hadha /app/storefront/.output ./.output

USER hadha

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

CMD ["node", ".output/server/index.mjs"]
