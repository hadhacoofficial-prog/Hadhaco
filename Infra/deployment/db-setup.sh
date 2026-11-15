#!/usr/bin/env bash
# =============================================================================
# db-setup.sh — provision / verify the application PostgreSQL container.
#
# Idempotent: safe to run any number of times (deploy.sh runs it on every
# release). Creates the data volume, generates credentials once, starts the
# container, waits for it to be healthy, makes sure the extensions the schema
# needs exist, and installs the hourly backup cron.
#
# Never prints the password. Never touches an existing database's data.
# =============================================================================
set -euo pipefail

APP_DIR="/opt/hadha"
COMPOSE_FILE="${APP_DIR}/docker-compose.database.yml"
PG_ENV="${APP_DIR}/.env.postgres"
CONTAINER="hadha-postgres"
VOLUME="hadha_postgres_data"
NETWORK="hadha"

log() { echo "[$(date +'%H:%M:%S')] db-setup: $*"; }
die() { log "ERROR: $*"; exit 1; }

[[ -f "${COMPOSE_FILE}" ]] || die "missing ${COMPOSE_FILE}"
docker network inspect "${NETWORK}" >/dev/null 2>&1 || die "docker network '${NETWORK}' not found (run bootstrap.sh)"

docker volume inspect "${VOLUME}" >/dev/null 2>&1 || {
  docker volume create "${VOLUME}" >/dev/null
  log "created volume ${VOLUME}"
}

if [[ ! -f "${PG_ENV}" ]]; then
  ( umask 077
    printf 'POSTGRES_USER=hadha\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=hadha\n' "$(openssl rand -hex 24)" > "${PG_ENV}" )
  log "generated ${PG_ENV} (mode 600)"
fi
chmod 600 "${PG_ENV}"
[[ "${EUID}" -ne 0 ]] || chown "$(stat -c %U:%G "${APP_DIR}")" "${PG_ENV}"

docker compose -f "${COMPOSE_FILE}" up -d >/dev/null

log "waiting for ${CONTAINER} to become healthy..."
for _ in $(seq 1 60); do
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER}" 2>/dev/null || echo missing)"
  [[ "${state}" == "healthy" ]] && break
  sleep 2
done
[[ "${state}" == "healthy" ]] || die "${CONTAINER} not healthy (state=${state})"

# Extensions the schema relies on (trigram search indexes, unaccent, ...).
# They live in `public` because the restored index definitions reference
# public.gin_trgm_ops. IF NOT EXISTS keeps this a no-op on a populated DB.
# shellcheck disable=SC2016  # $POSTGRES_* are expanded inside the container
docker exec -i "${CONTAINER}" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q' <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_trgm   WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS btree_gin WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS unaccent  WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pgcrypto  WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;
SQL

# Hourly backup (script keeps its own retention), run as the deploy user so the
# files it writes are owned by the same user deploy.sh runs as. /etc/cron.d is
# root-only: installed when this runs as root (first provisioning, by hand),
# left as is when deploy.sh runs it as the deploy user.
BACKUP_USER="$(stat -c %U "${APP_DIR}")"
if (( EUID == 0 )); then
  cat > /etc/cron.d/hadha-db-backup <<CRON
# Managed by db-setup.sh — do not edit.
17 * * * * ${BACKUP_USER} ${APP_DIR}/scripts/db-backup.sh >> ${APP_DIR}/backup-db.log 2>&1
CRON
  chmod 644 /etc/cron.d/hadha-db-backup
elif [[ ! -f /etc/cron.d/hadha-db-backup ]]; then
  log "WARN: backup cron not installed (needs root): run scripts/db-setup.sh as root once"
fi

log "ready: $(docker exec "${CONTAINER}" postgres --version)"
