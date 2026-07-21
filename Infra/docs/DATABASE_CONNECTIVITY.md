# Database Connectivity — Pre-flight & Reliability

**Date:** 2026-07-21
**Status:** Implemented

## Overview

Database connectivity is the single most critical dependency for Hadha.co deployments. If the database is unreachable, migrations fail, the backend cannot start, and the deployment aborts.

## Architecture

```
VPS (Ubuntu 24.04)
  └── deploy.sh
        └── docker run hadha-migration
              └── alembic upgrade head
                    └── TCP connection to Supabase PostgreSQL
                          └── db.xxxxx.supabase.co:5432
```

The VPS connects to **Supabase PostgreSQL** (hosted) — not a local database. This means:
- The connection traverses the public internet
- DNS resolution must work correctly
- IPv4 or IPv6 must be functional
- No VPN or firewall rules should block outbound TCP to port 5432

## Pre-flight Checks

### 1. DNS Resolution

Before any database operation, deploy.sh resolves the database hostname:

```bash
db_host=$(echo "${db_url}" | sed -n 's|.*@\([^:/]*\).*|\1|p')
```

If DNS resolution fails, the deployment aborts immediately with actionable instructions.

### 2. TCP Connectivity

Multiple methods are tried in order:
1. `nc -4 -zw5` — Explicit IPv4 TCP check (preferred)
2. `nc -zw5` — Default TCP check (may use IPv6)
3. `bash /dev/tcp` — Fallback if `nc` is unavailable
4. `curl` — Last resort HTTP check

### 3. IPv4 Preference

When IPv6 is detected as non-functional:
- Migration container gets `--sysctl net.ipv6.conf.all.disable_ipv6=1`
- TCP checks prefer IPv4 (`nc -4`)
- `/etc/gai.conf` recommendation provided if needed

## Retry Logic

Migrations are retried up to **3 times** with **10-second delays** between attempts. This handles:
- Transient DNS failures
- Brief network interruptions
- PostgreSQL connection pool exhaustion
- Supabase maintenance windows

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `connection timed out` | IPv6 AAAA record preferred, IPv6 non-functional | Add `precedence ::ffff:0:0/96 100` to `/etc/gai.conf` |
| `name or service not known` | DNS resolution failure | Check `/etc/resolv.conf`, ensure DNS works |
| `connection refused` | PostgreSQL not accepting connections | Check Supabase dashboard for service status |
| `password authentication failed` | Wrong credentials in `DATABASE_URL` | Verify `DATABASE_URL` in `.env.production` |
| `database does not exist` | Wrong database name | Verify database name in `DATABASE_URL` |

## Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `DATABASE_URL` | `.env.production` | Main database connection string |
| `ALEMBIC_DATABASE_URL` | `.env.production` | Migration-specific connection string (optional, falls back to `DATABASE_URL`) |

## Manual Diagnostics

```bash
# Test DNS resolution
getent ahostsv4 db.xxxxx.supabase.co
getent ahostsv6 db.xxxxx.supabase.co

# Test TCP connectivity (IPv4)
nc -4 -zw5 db.xxxxx.supabase.co 5432

# Test TCP connectivity (any)
nc -zw5 db.xxxxx.supabase.co 5432

# Test via PostgreSQL client
docker run --rm --network hadha postgres:16-alpine \
  pg_isready -h db.xxxxx.supabase.co -p 5432

# Check gai.conf
cat /etc/gai.conf | grep -v '^#' | grep -v '^$'

# Test with curl
curl -v --max-time 5 telnet://db.xxxxx.supabase.co:5432
```

## Files Changed

- `Infra/deployment/deploy.sh` — Pre-flight checks, retry logic, IPv4 sysctl
- `Infra/deployment/validate-network.sh` — Network validation script
