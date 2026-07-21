# Network Analysis — IPv4/IPv6 Root Cause

**Date:** 2026-07-21
**Status:** Implemented

## Problem Statement

Database connections to Supabase PostgreSQL intermittently failed during deployment, causing Alembic migrations to fail and deployment to abort.

## Root Cause

Supabase PostgreSQL hostnames (e.g., `db.xxxxx.supabase.co`) resolve to both **A (IPv4)** and **AAAA (IPv6)** DNS records. When the VPS has IPv6 configured but non-functional (common on many VPS providers), the system resolver or psycopg may attempt to connect via IPv6 first, which silently fails.

### Evidence

1. Backend container already had `sysctls: net.ipv6.conf.all.disable_ipv6: "1"` in `docker-compose.application.yml` — indicating prior IPv6 issues were encountered
2. Migration container (`hadha-migration`) was run via `docker run` without the same `sysctls` setting, meaning migrations used the default (broken) IPv6
3. Many VPS providers configure IPv6 at the OS level but don't route traffic — the interface has a link-local address but no default route or no internet connectivity

### Resolution Flow

```
DNS query for db.xxxxx.supabase.co
  → Returns: A record (IPv4) + AAAA record (IPv6)
  → System resolver may prefer IPv6 (Happy Eyeballs algorithm)
  → IPv6 connection attempt to PostgreSQL port 5432
  → Times out or connection refused (no routing)
  → psycogp falls back (or doesn't, depending on configuration)
  → Migration fails
```

## Fix Applied

### deploy.sh Changes

1. **IPv4/IPv6 detection at startup** (`detect_ip_support` function):
   - Pings `8.8.8.8` for IPv4, `2001:4860:4860::8888` for IPv6
   - Sets `IPV4_FUNCTIONAL` and `IPV6_FUNCTIONAL` flags

2. **Database pre-flight check** (`preflight_database` function):
   - Extracts host/port from `DATABASE_URL`
   - Tests TCP connectivity via multiple methods (`nc -4`, `nc`, `bash /dev/tcp`)
   - Provides actionable fix instructions if connection fails

3. **IPv4-only migration container**:
   - When IPv6 is non-functional, passes `--sysctl net.ipv6.conf.all.disable_ipv6=1` to migration container
   - Matches the setting already on the backend container

4. **Migration retry with backoff**:
   - Retries migration up to 3 times with 10-second delays
   - Transient network failures no longer cause immediate deployment abort

### validate-network.sh

New pre-deployment validation script that checks:
- IPv4/IPv6 interface presence and internet connectivity
- DNS resolution for all service domains
- Docker daemon and network state
- Database TCP connectivity (with IPv4 preference)
- External service reachability (GHCR, Resend, Supabase, Cloudflare R2)
- SSL certificate validity
- Disk space

## Manual Fix (if needed)

If the database pre-flight fails on the VPS, apply this fix:

```bash
# Force glibc to prefer IPv4 for all connections
echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

# Or set DATABASE_URL to use the IPv4 address directly:
# Find the IPv4 address:
dig A db.xxxxx.supabase.co +short
# Replace hostname in .env.production:
sed -i 's/db.xxxxx.supabase.co/<ipv4-address>/g' /opt/hadha/.env.production
```

## Files Changed

- `Infra/deployment/deploy.sh` — IPv4/IPv6 detection, pre-flight, migration retry
- `Infra/deployment/validate-network.sh` — New network validation script
