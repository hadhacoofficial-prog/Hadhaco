# Database Connectivity — Pre-flight & Reliability

**Updated:** 2026-11-15 (database moved from Supabase to a local PostgreSQL container)
**Status:** Implemented

## Overview

The application database is PostgreSQL 17 running as the container `hadha-postgres` on the VPS. If it is unreachable, migrations fail, the backend cannot start, and the deployment aborts.

## Architecture

```
VPS (Ubuntu 24.04)
  ├── docker compose project "hadha-database"   (own project — deploys never restart it)
  │     └── hadha-postgres  (postgres:17.6-alpine, volume hadha_postgres_data)
  └── deploy.sh
        ├── db-setup.sh                          (idempotent: ensure container, extensions, backup cron)
        ├── db-backup.sh --pre-deploy <tag>      (encrypted dump -> S3, verified restore)
        └── docker run hadha-migration -> alembic upgrade head
```

The database is reachable only on the internal `hadha` Docker network as `hadha-postgres:5432`; no port is published to the host. This means:
- No public-internet hop, DNS or IPv6 dependency for database traffic
- Credentials live in `/opt/hadha/.env.postgres` (mode 600), the URLs in `/opt/hadha/.env.production`
- Backups are the only copy off the server (see below), so they are part of the reliability story

## Pre-flight Checks

`deploy.sh` (step "Database pre-flight check") calls `preflight_database`. When `DATABASE_URL` points at `hadha-postgres` the host cannot resolve that name, so the check asks the container directly:

```bash
docker exec hadha-postgres pg_isready -q
```

Before that, the deploy runs `db-setup.sh`, which starts the container only if it is down, re-checks the extensions (`pg_trgm`, `btree_gin`, `unaccent`, `pgcrypto`, `pg_stat_statements`) and keeps the hourly backup cron in place. It never recreates the database, regenerates credentials or touches data.

## Pre-deploy backup gate

Right after the pre-flight, `db-backup.sh --pre-deploy <image-tag>` dumps the database, encrypts it, uploads it to the private `db_backup` bucket (Supabase Storage, S3 protocol), downloads it back, decrypts it and runs `pg_restore -l` plus a byte comparison. Any failure stops the deploy **before migrations**. Emergency bypass for a manual deploy: `SKIP_PREDEPLOY_BACKUP=1`. Hourly backups run from `/etc/cron.d/hadha-db-backup`.

## Retry Logic

Migrations are retried up to **3 times** with **10-second delays** between attempts. This handles brief connection-slot exhaustion or a container that is still starting.

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `hadha-postgres is not accepting connections` | Container stopped or unhealthy | `docker ps -a`, `docker logs hadha-postgres`; `scripts/db-setup.sh` restarts it |
| `password authentication failed` | `DATABASE_URL` out of sync with `/opt/hadha/.env.postgres` | Re-copy the password from `.env.postgres` into `.env.production` |
| `database "hadha" does not exist` | Wrong database name in `DATABASE_URL` | Name must be `hadha` |
| `Pre-deploy database backup failed` | Bucket unreachable (e.g. Supabase project paused), wrong keys, or file ownership | Read the `db-backup(predeploy)` line in `/opt/hadha/deploy.log`; resume the project / fix `/opt/hadha/.env.backup`; as a last resort `SKIP_PREDEPLOY_BACKUP=1` |
| `Permission denied` writing `/opt/hadha/backups/db` | Directory not owned by the `deploy` user | `chown -R deploy:deploy /opt/hadha/backups/db` |

## Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `DATABASE_URL` | `.env.production` | `postgresql+asyncpg://hadha:…@hadha-postgres:5432/hadha` |
| `ALEMBIC_DATABASE_URL` | `.env.production` | `postgresql+psycopg://…` same host/database (optional, falls back to `DATABASE_URL`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `.env.postgres` | Container bootstrap credentials |
| `BACKUP_S3_*`, `BACKUP_ENCRYPTION_KEY` | `.env.backup` | Off-site backup target and encryption passphrase |

## Manual Diagnostics

```bash
docker ps --filter name=hadha-postgres
docker exec hadha-postgres pg_isready
docker exec -it hadha-postgres psql -U hadha -d hadha          # interactive shell
docker logs --tail 100 hadha-postgres
tail -50 /opt/hadha/backup-db.log                              # hourly backup log
ls -lh /opt/hadha/backups/db | tail                            # local dumps
```
