# Hadha.co — DevOps & CI/CD Reference

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Server Bootstrap](#server-bootstrap)
3. [GitHub Setup](#github-setup)
4. [Secrets Configuration](#secrets-configuration)
5. [Deployment Flow](#deployment-flow)
6. [Branch Strategy](#branch-strategy)
7. [Rollback Process](#rollback-process)
8. [Disaster Recovery](#disaster-recovery)
9. [Manual Deployment](#manual-deployment)
10. [Monitoring](#monitoring)
11. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
GitHub Push
    │
    ▼
GitHub Actions CI
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

Production stack (all containers on hadha-internal network):
    Nginx:443 ──► frontend:3000  (TanStack Start / Nitro SSR)
                ►  backend:8000  (/api/*)
                ► /dozzle         (log viewer, basic auth)
                ► /redis-commander (Redis GUI, basic auth)
    Redis:6379  (password-protected, internal only)
```

---

## Server Bootstrap

**One-time setup on a fresh Ubuntu 24.04 VPS:**

```bash
# Set required variables
export DOMAIN=hadha.co
export STAGING_DOMAIN=staging.hadha.co
export ADMIN_EMAIL=admin@hadha.co
export MONITORING_USER=hadha-admin
export MONITORING_PASSWORD="$(openssl rand -base64 24)"
export DEPLOY_USER=deploy

# Run bootstrap
curl -fsSL https://raw.githubusercontent.com/YOUR-ORG/YOUR-REPO/main/deploy/scripts/bootstrap.sh \
  | sudo -E bash
```

The bootstrap script:
- Updates the system and installs Docker, certbot, fail2ban, ufw
- Creates the `deploy` system user (added to `docker` group)
- Creates `/opt/hadha/` and `/opt/hadha-staging/` directory trees
- Generates `htpasswd` for monitoring tools
- Requests Let's Encrypt certificates for both domains
- Configures certbot auto-renewal via cron
- Generates an SSH key pair for GitHub Actions and prints the **private key**

> **Important:** Copy the printed SSH private key to the GitHub Secret `SSH_PRIVATE_KEY` immediately after bootstrap.

### Post-bootstrap: environment files

Create `/opt/hadha/.env.production` from `Backend/.env.production.example`:

```bash
sudo -u deploy cp /path/to/.env.production.example /opt/hadha/.env.production
sudo -u deploy nano /opt/hadha/.env.production
```

Create `/opt/hadha/.env.frontend.production` (frontend-specific):

```env
VITE_API_BASE_URL=https://hadha.co/api/v1
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_xxxx
NODE_ENV=production
PORT=3000
```

Repeat for staging at `/opt/hadha-staging/`.

---

## GitHub Setup

### Repository structure

```
/ (repo root)
├── .github/workflows/
│   ├── ci.yml           — PR validation (no deploy)
│   ├── staging.yml      — develop branch → staging VPS
│   └── production.yml   — main branch → production VPS
├── Backend/             — FastAPI application
├── Frontend/            — TanStack Start application
├── deploy/
│   ├── docker/          — Production compose files
│   ├── nginx/           — Nginx config
│   └── scripts/         — deploy.sh, rollback.sh, backup.sh, …
└── DEVOPS.md
```

### GitHub Environments

Create two environments in Settings → Environments:

| Environment | Branch protection | Required reviewers |
|-------------|------------------|--------------------|
| `staging`   | `develop`        | None               |
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
| `GHCR_TOKEN` | GitHub PAT with `read:packages` scope (or leave unset — `GITHUB_TOKEN` is used automatically) |

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

### Push to `develop` (staging)

```
1. ci.yml runs (lint, tests, type-check, build validation)
2. Docker images built with BuildKit cache:
   • ghcr.io/owner/hadha-backend:develop-SHA
   • ghcr.io/owner/hadha-frontend:develop-SHA
3. SSH into VPS
4. backup.sh staging          — snapshot image metadata, Redis volume, compose file,
                                 nginx config, .env checksums
                                 (no PostgreSQL dump — database is on Supabase)
5. Pull new images from GHCR
6. alembic upgrade head        — runs in isolated container against Supabase PostgreSQL
7. docker compose up -d        — zero-downtime restart (containers replaced one by one)
8. healthcheck.sh staging      — 2-minute timeout, checks backend/frontend/redis/nginx
9a. Success → notify.sh success
9b. Failure → rollback.sh staging → notify.sh failure
```

### Push to `main` (production)

Same flow as staging, plus:
- Images additionally tagged `:latest` and `:vX.Y.Z` (if git tag present)
- Requires `production` GitHub environment approval (if reviewers configured)

### Semver releases

Tag a commit to also publish a versioned image:

```bash
git tag v1.2.3
git push origin v1.2.3
# Triggers production.yml → builds and tags images as sha-XXXX + v1.2.3 + latest
```

---

## Branch Strategy

| Branch | Deploys to | CI |
|--------|-----------|-----|
| `main` | Production | Full CI + deploy |
| `develop` | Staging | Full CI + deploy |
| `feature/*` | — | Full CI (no deploy) |
| `fix/*` | — | Full CI (no deploy) |
| `hotfix/*` | — | Full CI; merge to `main` to deploy |

### Hotfix flow

```bash
git checkout -b hotfix/fix-critical-bug main
# … make fix …
git push origin hotfix/fix-critical-bug
# Open PR to main → CI runs → merge → auto-deploys to production
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

/opt/hadha/scripts/rollback.sh production \
  "${BACKEND_IMAGE}" \
  "${FRONTEND_IMAGE}"
```

**Rollback to last backup (auto-resolves image from metadata):**

```bash
/opt/hadha/scripts/rollback.sh production
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
2. Point DNS to the new IP
3. Run `bootstrap.sh` (generates new SSH key — update GitHub Secret)
4. Copy `.env` files from secure storage / 1Password
5. Restore Redis data from backup:

```bash
# Find the latest backup with redis_data.tar.gz
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

The database is in Supabase — use the Supabase dashboard for point-in-time recovery. Redis is a cache and rate-limit store; losing it is non-fatal (users stay logged in, cache rebuilds automatically).

---

## Manual Deployment

### Deploy latest images without a git push

```bash
ssh deploy@YOUR_VPS_IP

# Re-run with the current image tag
/opt/hadha/scripts/deploy.sh production sha-CURRENT_SHA
```

### Force a fresh deploy of a specific image

```bash
export BACKEND_IMAGE=ghcr.io/owner/hadha-backend:sha-abc1234
export FRONTEND_IMAGE=ghcr.io/owner/hadha-frontend:sha-abc1234
export REDIS_PASSWORD=...
export GHCR_USERNAME=your-github-username
export GHCR_TOKEN=your-ghcr-token
export GIT_COMMIT_SHA=abc1234
export GIT_COMMIT_AUTHOR="Manual deploy"
export RESEND_API_KEY=...
export RESEND_FROM_EMAIL=...
export RESEND_TO_EMAIL=...

/opt/hadha/scripts/deploy.sh production sha-abc1234
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
https://hadha.co/dozzle/
```

- Protected by nginx basic auth (`htpasswd`)
- Username/password set during bootstrap
- Real-time streaming of all container logs
- Filter by container name

### Redis Commander — Redis GUI

```
https://hadha.co/redis-commander/
```

- Protected by nginx basic auth
- Connected automatically to production Redis
- View keys, TTLs, memory usage

### Nginx logs

```bash
# On VPS:
docker exec hadha-nginx tail -f /var/log/nginx/access.log
docker exec hadha-nginx tail -f /var/log/nginx/error.log

# API-specific:
docker exec hadha-nginx tail -f /var/log/nginx/api_access.log
```

### Container status

```bash
ssh deploy@YOUR_VPS_IP
docker compose -f /opt/hadha/docker-compose.production.yml ps
docker stats --no-stream
```

---

## Troubleshooting

### Deployment fails with "health check timed out"

```bash
# Check container logs
docker logs hadha-backend  --tail 100
docker logs hadha-frontend --tail 100

# Check readiness endpoint directly
docker exec hadha-backend python -c "
import httpx, json
r = httpx.get('http://localhost:8000/health/ready')
print(json.dumps(r.json(), indent=2))
"
```

### Migration fails

```bash
# Check migration state
docker run --rm \
  --env-file /opt/hadha/.env.production \
  ghcr.io/owner/hadha-backend:latest \
  python -m alembic current

# Show migration history
docker run --rm \
  --env-file /opt/hadha/.env.production \
  ghcr.io/owner/hadha-backend:latest \
  python -m alembic history --verbose
```

### Redis connection error

```bash
# Check Redis is running and authenticated
docker exec hadha-redis redis-cli -a "${REDIS_PASSWORD}" ping
# Expected: PONG

# Check backend can reach Redis
docker exec hadha-backend python -c "
import asyncio, redis.asyncio as r
async def check():
    client = r.from_url('redis://hadha-redis:6379/0', password='...')
    print(await client.ping())
asyncio.run(check())
"
```

### Rotating the Redis password

Redis passwords are runtime-only configuration — data files are never encrypted by the password, so rotation requires no data migration.

**Step 1 — Generate a new password**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Example output: a3f8c2e1d94b7065f2a1b8c3d4e5f60712345678901234567890abcdef012345
```

**Step 2 — Set the live Redis password without restart (optional zero-downtime)**

```bash
# SSH onto the server and set the new password in the running Redis first.
# This lets the backend keep working while you update config.
docker exec hadha-redis redis-cli -a "${OLD_REDIS_PASSWORD}" \
  CONFIG SET requirepass "${NEW_REDIS_PASSWORD}"
```

**Step 3 — Update server .env files**

```bash
# On the VPS:
sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=${NEW_REDIS_PASSWORD}/" /opt/hadha/.env.production
sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=${NEW_REDIS_PASSWORD}/" /opt/hadha-staging/.env.staging
```

**Step 4 — Update GitHub Secret**

In GitHub → Settings → Secrets and variables → Actions → update `REDIS_PASSWORD` to the new value.

**Step 5 — Redeploy**

```bash
# Trigger a fresh deploy so all containers pick up the new password.
# The deploy will restart Redis (with the new --requirepass) and the backend
# (with the new REDIS_URL containing the new password).
export REDIS_PASSWORD="${NEW_REDIS_PASSWORD}"
/opt/hadha/scripts/deploy.sh production "${CURRENT_IMAGE_TAG}"
```

**Step 6 — Verify**

```bash
docker exec hadha-redis redis-cli -a "${NEW_REDIS_PASSWORD}" ping
# Expected: PONG

docker exec hadha-backend python -c "
import asyncio, os
import redis.asyncio as r
async def check():
    client = r.from_url(os.environ['REDIS_URL'])
    print(await client.ping())
asyncio.run(check())
"
# Expected: True
```

> **Important:** Steps 2 and 5 overlap — Step 2 hot-patches the running Redis; Step 5 makes the new password permanent via `--requirepass` in the compose command. Skipping Step 2 means there will be a brief auth failure window while containers restart (usually < 5 seconds; the circuit breaker handles it gracefully).

### SSL certificate issues

```bash
# Test certificate validity
openssl s_client -connect hadha.co:443 -servername hadha.co < /dev/null 2>/dev/null \
  | openssl x509 -noout -dates

# Manually renew
sudo certbot renew --force-renewal
sudo docker exec hadha-nginx nginx -s reload
```

### Container won't start / OOM

```bash
# Check resource usage
docker stats hadha-backend hadha-frontend hadha-redis

# Adjust memory limits in docker-compose.production.yml
# deploy.resources.limits.memory for each service
```

### Images not available from GHCR

```bash
# Re-login
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin

# List available tags
docker manifest inspect ghcr.io/owner/hadha-backend:sha-abc1234
```

---

## File Reference

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | PR validation: lint, test, build |
| `.github/workflows/staging.yml` | Auto-deploy on `develop` push |
| `.github/workflows/production.yml` | Auto-deploy on `main` push |
| `deploy/docker/docker-compose.production.yml` | Production service definitions |
| `deploy/docker/docker-compose.staging.yml` | Staging service definitions |
| `deploy/nginx/nginx.conf` | Nginx worker/SSL/gzip config |
| `deploy/nginx/hadha.conf` | Nginx server blocks + routes |
| `deploy/scripts/bootstrap.sh` | First-time VPS setup |
| `deploy/scripts/deploy.sh` | Main deployment orchestrator |
| `deploy/scripts/rollback.sh` | Restore previous images |
| `deploy/scripts/backup.sh` | Pre-deploy snapshot |
| `deploy/scripts/healthcheck.sh` | Post-deploy health verification |
| `deploy/scripts/notify.sh` | Resend email notifications |
| `Backend/docker/Dockerfile` | Production backend image |
| `Frontend/Dockerfile` | Dev + production frontend image |
| `Frontend/playwright.config.ts` | Playwright E2E configuration |
| `Frontend/vitest.config.ts` | Vitest unit test configuration |
| `Frontend/e2e/tests/` | E2E test suites |
