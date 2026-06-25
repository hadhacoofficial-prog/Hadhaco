# Hadha.co — DevOps & CI/CD Reference

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Server Bootstrap](#server-bootstrap)
3. [GitHub Setup](#github-setup)
4. [Secrets Configuration](#secrets-configuration)
5. [Deployment Flow](#deployment-flow)
6. [Rollback Process](#rollback-process)
7. [Disaster Recovery](#disaster-recovery)
8. [Manual Deployment](#manual-deployment)
9. [Monitoring](#monitoring)
10. [Database Connection Architecture](#database-connection-architecture)
11. [GHCR Image Propagation](#ghcr-image-propagation)
12. [Failure Classification](#failure-classification)
13. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
GitHub Push to main
    │
    ▼
GitHub Actions CI (ci.yml)
 ├── Backend: ruff, black, mypy, bandit, pip-audit, pytest --cov
 └── Frontend: ESLint, Prettier, tsc, Vitest, build validation
    │
    ▼
Docker Build (BuildKit cache)
 ├── ghcr.io/owner/hadha-backend:sha-XXXXXXXX
 └── ghcr.io/owner/hadha-frontend:sha-XXXXXXXX
    │
    ▼  SSH
Hostinger KVM 2 VPS (Ubuntu 24.04)
    │
    ├── backup current state
    ├── pull new images
    ├── run alembic migrations
    ├── restart containers
    └── health checks → success / rollback
         │
         ▼
    Resend email notification
```

### Production stack

All containers run on the `hadha-internal` Docker bridge network. Only Nginx is exposed externally.

```
Internet → Cloudflare DNS
              │
              ▼
          Nginx :80/:443
              │
   ┌──────────┼──────────────┬──────────────┬──────────────┐
   │          │              │              │              │
   ▼          ▼              ▼              ▼              ▼
hadha.co  api.hadha.co  admin.hadha.co  redis.hadha.co  dozzle.hadha.co
   │          │              │              │              │
Frontend   FastAPI      Admin Portal   Redis Commander   Dozzle
:3000      :8000        :3000 (same)   :8081             :8080
```

**CDN:** Cloudflare R2 at `cdn.hadha.co`

### Domain map

| Domain | Service | Notes |
|--------|---------|-------|
| `hadha.co` | Frontend (customer site) | www redirects to apex |
| `api.hadha.co` | FastAPI backend | All `/api/v1/*` and `/health` routes |
| `admin.hadha.co` | Admin portal | Served by same frontend container |
| `redis.hadha.co` | Redis Commander | Basic auth required |
| `dozzle.hadha.co` | Dozzle log viewer | Basic auth required |
| `cdn.hadha.co` | Cloudflare R2 | Media / asset storage |

---

## Server Bootstrap

**One-time setup on a fresh Ubuntu 24.04 VPS:**

```bash
export DOMAIN=hadha.co
export ADMIN_EMAIL=admin@hadha.co
export MONITORING_USER=hadha-admin
export MONITORING_PASSWORD="$(openssl rand -base64 24)"
export DEPLOY_USER=deploy

curl -fsSL https://raw.githubusercontent.com/YOUR-ORG/YOUR-REPO/main/deploy/scripts/bootstrap.sh \
  | sudo -E bash
```

The bootstrap script:
- Updates the system and installs Docker, certbot, fail2ban, ufw
- Creates the `deploy` system user (added to `docker` group)
- Creates `/opt/hadha/` directory tree
- Generates `htpasswd` for monitoring tools (redis.hadha.co, dozzle.hadha.co)
- Requests a single Let's Encrypt certificate covering all subdomains:
  `hadha.co`, `www.hadha.co`, `api.hadha.co`, `admin.hadha.co`, `redis.hadha.co`, `dozzle.hadha.co`
- Configures certbot auto-renewal via cron
- Generates an SSH key pair for GitHub Actions and prints the **private key**

> **Important:** Copy the printed SSH private key to the GitHub Secret `SSH_PRIVATE_KEY` immediately after bootstrap.

### Post-bootstrap: DNS

Point the following A records to the VPS IP before issuing SSL certificates:

| Record | Type | Value |
|--------|------|-------|
| `hadha.co` | A | VPS IP |
| `www.hadha.co` | A | VPS IP |
| `api.hadha.co` | A | VPS IP |
| `admin.hadha.co` | A | VPS IP |
| `redis.hadha.co` | A | VPS IP |
| `dozzle.hadha.co` | A | VPS IP |

### Post-bootstrap: environment files

Create `/opt/hadha/.env.production` from `Backend/.env.production.example`:

```bash
sudo -u deploy cp /path/to/.env.production.example /opt/hadha/.env.production
sudo -u deploy nano /opt/hadha/.env.production
```

Create `/opt/hadha/.env.frontend.production`:

```env
NODE_ENV=production
PORT=3000
# SSR server-side API calls go directly to the backend container over Docker internal network
SERVER_API_BASE_URL=http://hadha-backend:8000/api/v1
```

> Note: `VITE_API_BASE_URL` is baked at build time (set in GitHub Actions) and resolves to `https://api.hadha.co/api/v1` for browser-side requests.

---

## GitHub Setup

### Repository structure

```
/ (repo root)
├── .github/workflows/
│   ├── ci.yml           — PR validation (no deploy)
│   └── production.yml   — main branch → production VPS
├── Backend/             — FastAPI application
├── Frontend/            — TanStack Start application
├── deploy/
│   ├── docker/          — Production compose file
│   ├── nginx/           — Nginx config (nginx.conf + conf.d/*.conf)
│   └── scripts/         — deploy.sh, rollback.sh, backup.sh, …
└── DEVOPS.md
```

### GitHub Environments

Create one environment in Settings → Environments:

| Environment | Branch protection | Required reviewers |
|-------------|------------------|--------------------|
| `production`| `main`           | 1 reviewer (recommended) |

---

## Secrets Configuration

Set these in **Settings → Secrets → Actions → New repository secret**:

### SSH / VPS

| Secret | Description |
|--------|-------------|
| `SSH_HOST` | VPS IP address or hostname |
| `SSH_PORT` | SSH port (default: `22`) |
| `SSH_USER` | Deploy user (e.g. `deploy`) |
| `SSH_PRIVATE_KEY` | Private key from bootstrap (the `id_ed25519_github` content) |

### Container Registry

| Secret | Description |
|--------|-------------|
| `GHCR_TOKEN` | GitHub PAT with `read:packages` scope |

### Application

| Secret | Description |
|--------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `JWT_SECRET` | 64-char random hex |
| `REDIS_PASSWORD` | Redis authentication password |

### Payments

| Secret | Description |
|--------|-------------|
| `RAZORPAY_KEY_ID` | Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay key secret |

### Email / Notifications

| Secret | Description |
|--------|-------------|
| `RESEND_API_KEY` | Resend API key (`re_...`) |
| `RESEND_FROM_EMAIL` | Sender address (e.g. `noreply@hadha.co`) |
| `RESEND_TO_EMAIL` | Deployment notification recipient |

---

## Deployment Flow

### Push to `main` (production)

```
1. ci.yml runs (lint, tests, type-check, build validation)
2. Docker images built with BuildKit cache:
   • ghcr.io/owner/hadha-backend:sha-SHA
   • ghcr.io/owner/hadha-frontend:sha-SHA
   (frontend built with VITE_API_BASE_URL=https://api.hadha.co/api/v1)
3. verify-images job confirms both manifests are in GHCR
4. SSH into production VPS
5. backup.sh              — snapshot image metadata, Redis volume, compose file,
                             nginx config, .env checksums
6. Pull new images from GHCR
7. alembic upgrade head   — runs in isolated container against Supabase PostgreSQL
8. docker compose up -d   — zero-downtime restart
9. healthcheck.sh         — checks backend/frontend/redis/nginx + external HTTP probe
9a. Success → notify.sh success
9b. Failure → rollback.sh → notify.sh failure
```

### Semver releases

Tag a commit to also publish a versioned image:

```bash
git tag v1.2.3
git push origin v1.2.3
# Triggers production.yml → builds and tags images as sha-XXXX + v1.2.3 + latest
```

---

## Rollback Process

### Automatic rollback

The `deploy.sh` script automatically rolls back if health checks fail:

1. Health checks run with 120-second timeout
2. On failure: `rollback.sh` restores the previous container images
3. Previous image tags are captured before each deployment
4. Rollback health checks re-run to confirm recovery
5. Email notification sent regardless of rollback success

### Manual rollback

**Quick rollback to a specific image tag:**

```bash
ssh deploy@YOUR_VPS_IP

export BACKEND_IMAGE=ghcr.io/owner/hadha-backend:sha-PREVIOUS
export FRONTEND_IMAGE=ghcr.io/owner/hadha-frontend:sha-PREVIOUS
export REDIS_PASSWORD=your_redis_password

/opt/hadha/scripts/rollback.sh \
  "${BACKEND_IMAGE}" \
  "${FRONTEND_IMAGE}"
```

**Rollback to last backup (auto-resolves image from metadata):**

```bash
/opt/hadha/scripts/rollback.sh
# Reads image tags from most recent backup metadata JSON
```

**List available backups:**

```bash
ls -lt /opt/hadha/backups/
cat /opt/hadha/backups/metadata_TIMESTAMP.json
```

---

## Disaster Recovery

### Full VPS rebuild

1. Provision a new Ubuntu 24.04 VPS
2. Point all DNS subdomains to the new IP
3. Run `bootstrap.sh` (generates new SSH key — update GitHub Secret)
4. Copy `.env` files from secure storage / 1Password
5. Restore Redis data from backup:

```bash
BACKUP=$(ls -t /opt/hadha/backups/*/redis_data.tar.gz | head -1)

docker run --rm \
  -v hadha_redis_data:/data \
  -v $(dirname $BACKUP):/backup \
  alpine:3.20 \
  tar xzf /backup/redis_data.tar.gz -C /data

docker compose -f /opt/hadha/docker-compose.production.yml restart hadha-redis
```

6. Push any commit to `main` to trigger a fresh deployment

### Database recovery

The database is in Supabase — use the Supabase dashboard for point-in-time recovery.
Redis is a cache and rate-limit store; losing it is non-fatal.

---

## Manual Deployment

### Deploy latest images without a git push

```bash
ssh deploy@YOUR_VPS_IP

export BACKEND_IMAGE=ghcr.io/owner/hadha-backend:sha-CURRENT
export FRONTEND_IMAGE=ghcr.io/owner/hadha-frontend:sha-CURRENT
export REDIS_PASSWORD=...
export GHCR_USERNAME=your-github-username
export GHCR_TOKEN=your-ghcr-token
export GIT_COMMIT_SHA=abc1234
export GIT_COMMIT_AUTHOR="Manual deploy"
export RESEND_API_KEY=...
export RESEND_FROM_EMAIL=...
export RESEND_TO_EMAIL=...

/opt/hadha/scripts/deploy.sh sha-CURRENT
```

### Run database migrations only

```bash
docker run --rm \
  --env-file /opt/hadha/.env.production \
  --network hadha-internal \
  ghcr.io/owner/hadha-backend:latest \
  python -m alembic upgrade head
```

---

## Monitoring

### Dozzle — Container Logs

```
https://dozzle.hadha.co
```

- Protected by nginx basic auth (credentials set in bootstrap)
- Real-time streaming of all container logs

### Redis Commander — Redis GUI

```
https://redis.hadha.co
```

- Protected by nginx basic auth
- Connected automatically to production Redis

### Nginx logs

```bash
docker exec hadha-nginx tail -f /var/log/nginx/access.log
docker exec hadha-nginx tail -f /var/log/nginx/error.log
docker exec hadha-nginx tail -f /var/log/nginx/api_access.log
```

### Container status

```bash
ssh deploy@YOUR_VPS_IP
docker compose -f /opt/hadha/docker-compose.production.yml ps
docker stats --no-stream
```

---

## Database Connection Architecture

Supabase exposes three ways to connect to its PostgreSQL server.

### Connection mode comparison

| Mode | Host/Port | PgBouncer mode | Supports SET / PREPARE / LISTEN |
|------|-----------|---------------|--------------------------------|
| **Direct** | `db.PROJECT.supabase.co:5432` | Bypassed | Yes |
| **Session Pooler** | `*.pooler.supabase.com:5432` | Session mode | Yes |
| **Transaction Pooler** | `*.pooler.supabase.com:6543` | Transaction mode | No |

### FastAPI uses the Session Pooler (`DATABASE_URL`, port 5432)

The application uses SQLAlchemy's `AsyncEngine` with a client-side connection pool (`pool_size=5, max_overflow=2`). Session mode is correct because asyncpg caches named prepared statements per connection.

### Alembic uses the Transaction Pooler (`ALEMBIC_DATABASE_URL`, port 6543)

Migrations use `NullPool` and run as a one-shot Docker container. This prevents connection slot contention with the running FastAPI pool.

### Configuration

Add both URLs to `/opt/hadha/.env.production`:

```env
# Session Pooler — used by the FastAPI runtime
DATABASE_URL=postgresql+asyncpg://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres

# Transaction Pooler — used only by Alembic migrations
ALEMBIC_DATABASE_URL=postgresql+asyncpg://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
```

---

## GHCR Image Propagation

`docker buildx build --push` returns success when the GHCR origin accepts the manifest, but edge CDN nodes may not have replicated it yet. The CI/CD pipeline inserts a `verify-images` job between `build-push` and `deploy-production`:

```
ci → version → build-push → verify-images → deploy-production
```

`verify-images` polls both manifests with exponential backoff until confirmed. `deploy.sh` also performs a pre-pull manifest check as a second gate.

---

## Failure Classification

`deploy.sh` classifies every pull failure:

| Class | Description | Recovery |
|---|---|---|
| `MANIFEST_MISSING` | GHCR edge hasn't replicated yet | Wait; `verify-images` usually prevents this |
| `NETWORK_EOF` | TCP dropped mid-stream | Transient; retry |
| `TIMEOUT` | Registry slow | Transient; retry |
| `TLS_ERROR` | Certificate / TLS failure | Check VPS system clock |
| `REGISTRY_500` | GHCR internal error | Transient |
| `REGISTRY_5XX` | GHCR overloaded | Transient |
| `AUTHENTICATION` | Token missing `read:packages` | Verify `GHCR_TOKEN` |
| `DOCKER_DAEMON` | Docker engine problem | `systemctl status docker` |
| `UNKNOWN` | None matched | Inspect `deploy.log` |

```bash
tail -200 /opt/hadha/deploy.log
```

---

## Troubleshooting

### Deployment fails with "health check timed out"

```bash
docker logs hadha-backend  --tail 100
docker logs hadha-frontend --tail 100

docker exec hadha-backend python -c "
import httpx, json
r = httpx.get('http://localhost:8000/health/ready')
print(json.dumps(r.json(), indent=2))
"
```

### Migration fails

```bash
docker run --rm \
  --env-file /opt/hadha/.env.production \
  ghcr.io/owner/hadha-backend:latest \
  python -m alembic current

docker run --rm \
  --env-file /opt/hadha/.env.production \
  ghcr.io/owner/hadha-backend:latest \
  python -m alembic history --verbose
```

### Redis connection error

```bash
docker exec hadha-redis redis-cli -a "${REDIS_PASSWORD}" ping
# Expected: PONG
```

### Rotating the Redis password

1. Generate a new password: `python3 -c "import secrets; print(secrets.token_hex(32))"`
2. (Optional) Hot-patch running Redis: `docker exec hadha-redis redis-cli -a "${OLD}" CONFIG SET requirepass "${NEW}"`
3. Update `/opt/hadha/.env.production`: `sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=${NEW}/" /opt/hadha/.env.production`
4. Update GitHub Secret `REDIS_PASSWORD`
5. Redeploy: `/opt/hadha/scripts/deploy.sh "${CURRENT_IMAGE_TAG}"`

### SSL certificate issues

```bash
openssl s_client -connect hadha.co:443 -servername hadha.co < /dev/null 2>/dev/null \
  | openssl x509 -noout -dates

# Manually renew (covers all subdomains)
sudo certbot renew --force-renewal
sudo docker exec hadha-nginx nginx -s reload
```

### Images not available from GHCR

```bash
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin
docker manifest inspect ghcr.io/hadhacoofficial-prog/hadha-backend:sha-XXXXXXXX
docker manifest inspect ghcr.io/hadhacoofficial-prog/hadha-frontend:sha-XXXXXXXX
```

---

## File Reference

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | PR validation: lint, test, build |
| `.github/workflows/production.yml` | Auto-deploy on `main` push |
| `deploy/docker/docker-compose.production.yml` | Production service definitions |
| `deploy/nginx/nginx.conf` | Nginx worker/SSL/gzip/rate-limit config |
| `deploy/nginx/conf.d/hadha.conf` | `hadha.co` — customer website |
| `deploy/nginx/conf.d/api.hadha.co.conf` | `api.hadha.co` — FastAPI backend |
| `deploy/nginx/conf.d/admin.hadha.co.conf` | `admin.hadha.co` — admin portal |
| `deploy/nginx/conf.d/redis.hadha.co.conf` | `redis.hadha.co` — Redis Commander |
| `deploy/nginx/conf.d/dozzle.hadha.co.conf` | `dozzle.hadha.co` — Dozzle logs |
| `deploy/scripts/bootstrap.sh` | First-time VPS setup |
| `deploy/scripts/deploy.sh` | Main deployment orchestrator |
| `deploy/scripts/rollback.sh` | Restore previous images |
| `deploy/scripts/backup.sh` | Pre-deploy snapshot |
| `deploy/scripts/healthcheck.sh` | Post-deploy health verification |
| `deploy/scripts/notify.sh` | Resend email notifications |
| `Backend/docker/Dockerfile` | Production backend image |
| `Frontend/Dockerfile` | Dev + production frontend image |
