# Deployment Fixes — Complete Changelog

**Date:** 2026-07-21
**Status:** Implemented

## Summary

This document records all fixes applied to the Hadha.co deployment infrastructure to achieve permanent network and deployment reliability.

## Fix Categories

### 1. IPv4/IPv6 Database Connectivity (CRITICAL)

**File:** `Infra/deployment/deploy.sh`

| Change | Before | After |
|--------|--------|-------|
| IPv4/IPv6 detection | None | `detect_ip_support()` at startup |
| Database pre-flight | None | `preflight_database()` before migrations |
| Migration IPv6 handling | No `sysctls` on migration container | `--sysctl net.ipv6.conf.all.disable_ipv6=1` when IPv6 non-functional |
| Migration retry | Single attempt, immediate abort | 3 attempts with 10s backoff |
| GLITCHTIP_DSN passthrough | Not exported | Exported from env file and passed to compose |

### 2. Infrastructure Idempotency (HIGH)

**File:** `Infra/deployment/deploy.sh`

| Change | Before | After |
|--------|--------|-------|
| Infra container lifecycle | `docker rm -f` for monitoring containers | `docker compose up -d --wait` (idempotent) |
| Loki container conflict | Recreated on every deploy | Only started if not already running |
| Stale container handling | Force-removed all 4 monitoring containers | Only removed containers in non-running state |

### 3. GLITCHTIP_DSN / GLITCHTIP_FRONTEND_DSN Passthrough (HIGH)

**Files:** `Infra/deployment/deploy.sh`, `.github/workflows/production.yml`

| Change | Before | After |
|--------|--------|-------|
| DSN export from env | Not loaded | `grep` from `.env.production` if not already set |
| CI workflow envs | Not included in `envs:` list | Added `GLITCHTIP_DSN,GLITCHTIP_FRONTEND_DSN` |
| CI workflow exports | Not exported in inline script | Added `export GLITCHTIP_DSN GLITCHTIP_FRONTEND_DSN` |
| Compose wrapper | Did not pass DSN vars | Added to `export` list in compose section |

### 4. Migration Container Robustness (HIGH)

**File:** `Infra/deployment/deploy.sh`

- Added `--sysctl net.ipv6.conf.all.disable_ipv6=1` when IPv6 is non-functional
- Added retry logic: 3 attempts, 10s delay between retries
- Added pre-flight database connectivity check before attempting migration

### 5. Production Workflow Secrets (MEDIUM)

**File:** `.github/workflows/production.yml`

- Added `GLITCHTIP_DSN` and `GLITCHTIP_FRONTEND_DSN` to:
  - SSH action `env:` section (passed as SSH environment)
  - SSH action `envs:` list (forwarded to remote)
  - Inline deploy script `export` list

## Files Changed (Total: 3)

1. `Infra/deployment/deploy.sh` — IPv4/IPv6 detection, pre-flight, retry, idempotent infra, GLITCHTIP_DSN
2. `Infra/deployment/validate-network.sh` — New pre-deployment network validation script
3. `.github/workflows/production.yml` — GLITCHTIP_DSN/FRONTEND_DSN passthrough

## Verification

After deployment, run:

```bash
# Network validation
/opt/hadha/scripts/validate-network.sh

# Post-deployment verification
/opt/hadha/scripts/verify.sh

# Quick smoke tests
/opt/hadha/scripts/smoke-tests.sh
```

## Rollback

All changes are backward-compatible. If any issue arises:

1. The deploy script automatically rolls back to previous images on failure
2. IPv4/IPv6 detection is additive — if detection fails, original behavior is preserved
3. Migration retry is conservative — only retries on failure, not on success
