# Runtime Validation — Pre-deployment & Post-deployment Checks

**Date:** 2026-07-21
**Status:** Implemented

## Overview

Hadha.co deployment includes multiple validation layers to catch issues before they cause downtime:

1. **Pre-deployment** (`validate-network.sh`) — Run before deploy.sh
2. **In-deployment** (`deploy.sh` pre-flight) — Automatic checks within deploy pipeline
3. **Post-deployment** (`verify.sh`) — Full health verification
4. **Quick smoke** (`smoke-tests.sh`) — Fast HTTP checks

## Pre-deployment: validate-network.sh

Run manually or via CI before deployment:

```bash
./validate-network.sh
```

### Checks Performed

| Check | Critical | Description |
|-------|----------|-------------|
| IPv4 support | Yes | `ip -4 addr` + ping 8.8.8.8 |
| IPv6 support | No | `ip -6 route` + ping Google DNS |
| DNS resolution | Yes | All 5 service domains + database host |
| Docker daemon | Yes | Docker installed, running, Compose available |
| Docker network | No | `hadha` network exists |
| Database TCP | Yes | TCP connectivity to Supabase PostgreSQL |
| GHCR access | Yes | `ghcr.io/v2/` reachable |
| Resend API | No | `api.resend.com` reachable |
| Supabase API | No | REST API reachable |
| Cloudflare R2 | No | S3 endpoint reachable |
| SSL certificate | No | Valid for >30 days |
| Disk space | Yes | >5GB available |
| IPv4 URL hint | No | Suggests IPv4 DATABASE_URL if IPv6 non-functional |

### Exit Codes

- `0` — All checks passed (or warnings only)
- `1` — Critical failures detected — do NOT deploy

## In-deployment: deploy.sh Pre-flight

Automatic checks at the start of deploy.sh:

1. **File existence** — All compose files, env files exist
2. **Tool availability** — docker, curl, jq installed
3. **Secret presence** — All required env vars set
4. **Network detection** — IPv4/IPv6 functional status
5. **Database pre-flight** — TCP connectivity to Supabase

If any critical check fails, deployment aborts with:
- `die()` for missing prerequisites
- `rollback_and_exit()` for runtime failures (after attempting rollback)

## Post-deployment: verify.sh

Full verification after deployment completes:

```bash
./verify.sh
```

### Container Health (18 containers)

| Container | Health Check | Expected |
|-----------|-------------|----------|
| hadha-backend | Python httpx → /health/live | healthy |
| hadha-storefront | curl → localhost:3000 | healthy |
| hadha-admin | curl → localhost:3000 | healthy |
| hadha-redis | redis-cli ping | healthy |
| hadha-nginx | nginx -t + wget health | healthy |
| hadha-prometheus | wget → /-/healthy | healthy |
| hadha-grafana | wget → /api/health | healthy |
| hadha-loki | wget → /ready | healthy |
| hadha-promtail | wget → /ready | healthy |
| hadha-node-exporter | wget → /metrics | healthy |
| hadha-cadvisor | wget → /healthz | healthy |
| hadha-uptime-kuma | node http check | healthy |
| hadha-glitchtip | python urllib → /_health/ | healthy |
| hadha-glitchtip-worker | python urllib → localhost | healthy |
| hadha-glitchtip-db | pg_isready | healthy |
| hadha-redis-commander | node http check | healthy |
| hadha-dozzle | /dozzle healthcheck | healthy |
| hadha-redis-exporter | (no healthcheck) | running |

### Additional Checks

- **CrashLoop detection** — Restart count >5 = fail, >2 = warn
- **OOMKilled detection** — Any OOM kill = fail
- **Redis connectivity** — `redis-cli ping` → PONG
- **Nginx config** — `nginx -t` → syntax OK
- **HTTP probes** — 9 endpoints checked (2xx-3xx = pass, 4xx = warn, 000 = fail)
- **Prometheus targets** — All scrape targets UP
- **Loki readiness** — `/ready` returns "ready"

### Report Generation

Generates markdown report at:
```
/opt/hadha/backups/verify-YYYYMMDD-HHMMSS.md
```

## Quick Smoke: smoke-tests.sh

Fast verification (subset of verify.sh):

```bash
./smoke-tests.sh
```

Checks:
- 9 HTTP endpoints (Storefront, API, Admin, Grafana, Prometheus, Uptime Kuma, GlitchTip, Redis Commander, Dozzle)
- 9 container statuses
- Redis PONG
- SSL certificate expiry

## Running Validation

### Full Validation Pipeline

```bash
# 1. Pre-deployment network check
./validate-network.sh

# 2. Deploy (includes automatic pre-flight)
./deploy.sh sha-abc12345

# 3. Post-deployment verification
./verify.sh

# 4. Quick smoke test
./smoke-tests.sh
```

### CI/CD Integration

The GitHub Actions workflow (`production.yml`) runs:
1. CI validation (lint, test, build)
2. Image manifest verification
3. SCP deploy artifacts to VPS
4. SSH deploy (calls deploy.sh which includes pre-flight)
5. On failure: Resend email notification

## Troubleshooting

### validate-network.sh fails on database TCP

```bash
# Check what IP the database resolves to
getent ahostsv4 db.xxxxx.supabase.co
getent ahostsv6 db.xxxxx.supabase.co

# If AAAA record exists but IPv6 is broken, force IPv4:
echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

# Or update DATABASE_URL to use IPv4 address:
sed -i 's/db.xxxxx.supabase.co/<ipv4>/g' /opt/hadha/.env.production
```

### verify.sh shows containers not healthy

```bash
# Check container logs
docker logs hadha-backend --tail 50

# Check container health details
docker inspect hadha-backend --format='{{json .State.Health}}'

# Restart specific container
docker compose -f /opt/hadha/docker-compose.application.yml up -d backend
```

### Loki container conflict

```bash
# Check if Loki is already running
docker ps | grep loki

# If stuck, remove and let compose recreate
docker rm -f hadha-loki
docker compose -f /opt/hadha/docker-compose.infrastructure.yml up -d loki
```

## Files

- `Infra/deployment/validate-network.sh` — Pre-deployment validation
- `Infra/deployment/verify.sh` — Post-deployment verification
- `Infra/deployment/smoke-tests.sh` — Quick smoke tests
- `Infra/deployment/deploy.sh` — Deployment pipeline with built-in checks
