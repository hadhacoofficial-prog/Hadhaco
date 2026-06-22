#!/usr/bin/env bash
# =============================================================================
# backup.sh — Pre-deployment backup of Docker state, volumes, and database
#
# Usage:
#   ./backup.sh <environment>
#
# Creates a timestamped backup in $DEPLOY_DIR/backups/ containing:
#   - PostgreSQL database dump (pg_dump, custom format, compressed)
#   - Redis volume data (tar.gz)
#   - docker-compose.*.yml snapshot
#   - current image tags metadata
#   - .env checksums (no secret values)
#
# Retains the last 30 backups.
# IMPORTANT: This script exits non-zero on any critical failure.
# deploy.sh treats a non-zero exit here as a deployment abort.
# =============================================================================

set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment>}"

case "$ENVIRONMENT" in
  production)
    DEPLOY_DIR="/opt/hadha"
    BACKEND_CONTAINER="hadha-backend"
    ;;
  staging)
    DEPLOY_DIR="/opt/hadha-staging"
    BACKEND_CONTAINER="hadha-staging-backend"
    ;;
  *)
    echo "[ERROR] Unknown environment: ${ENVIRONMENT}"
    exit 1
    ;;
esac

BACKUP_DIR="${DEPLOY_DIR}/backups"
TIMESTAMP=$(date +'%Y%m%dT%H%M%S')
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"
LOG_FILE="${DEPLOY_DIR}/backup.log"
ENV_FILE="${DEPLOY_DIR}/.env.${ENVIRONMENT}"

log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }

mkdir -p "${BACKUP_PATH}"
log "Starting backup → ${BACKUP_PATH}"

# ── 1. PostgreSQL database dump ───────────────────────────────────────────────
# This is the most critical backup. A failure here aborts the deployment.
log "Step 1: PostgreSQL backup"

if [[ ! -f "${ENV_FILE}" ]]; then
  log "[FATAL] Env file not found: ${ENV_FILE} — cannot read DATABASE_URL"
  exit 1
fi

# Extract and convert DATABASE_URL: strip asyncpg driver prefix for pg_dump
RAW_DB_URL=$(grep "^DATABASE_URL=" "${ENV_FILE}" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "")
if [[ -z "${RAW_DB_URL}" ]]; then
  log "[FATAL] DATABASE_URL not found in ${ENV_FILE}"
  exit 1
fi

# Convert postgresql+asyncpg://... → postgresql://...
PG_URL="${RAW_DB_URL/postgresql+asyncpg:\/\//postgresql:\/\/}"

log "Running pg_dump via postgres:16-alpine (timeout: 300s)..."
timeout 300 docker run --rm \
  -v "${BACKUP_PATH}:/backup" \
  postgres:16-alpine \
  sh -c "pg_dump '${PG_URL}?sslmode=require' \
    --no-password \
    --format=custom \
    --compress=9 \
    -f /backup/database_${TIMESTAMP}.dump" \
  && log "PostgreSQL backup complete: database_${TIMESTAMP}.dump" \
  || {
    log "[FATAL] PostgreSQL backup failed — aborting deployment"
    exit 1
  }

# ── 2. Capture current running image tags ────────────────────────────────────
log "Step 2: Image metadata"
CURRENT_BACKEND=$(docker inspect "${BACKEND_CONTAINER}"   --format='{{.Config.Image}}' 2>/dev/null || echo "")
CURRENT_FRONTEND=$(docker inspect "${BACKEND_CONTAINER/backend/frontend}" --format='{{.Config.Image}}' 2>/dev/null || echo "")

cat > "${BACKUP_DIR}/metadata_${TIMESTAMP}.json" <<EOF
{
  "timestamp":      "${TIMESTAMP}",
  "environment":    "${ENVIRONMENT}",
  "backend_image":  "${CURRENT_BACKEND}",
  "frontend_image": "${CURRENT_FRONTEND}",
  "git_sha":        "${GIT_COMMIT_SHA:-unknown}",
  "git_author":     "${GIT_COMMIT_AUTHOR:-unknown}"
}
EOF
log "Image metadata saved: metadata_${TIMESTAMP}.json"

# ── 3. Backup Redis volume ────────────────────────────────────────────────────
log "Step 3: Redis volume backup"
REDIS_VOLUME=$(docker volume ls -q 2>/dev/null | grep -E "hadha.*redis" | head -1 || echo "")
if [[ -n "${REDIS_VOLUME}" ]]; then
  log "Backing up Redis volume: ${REDIS_VOLUME}"
  docker run --rm \
    -v "${REDIS_VOLUME}:/data:ro" \
    -v "${BACKUP_PATH}:/backup" \
    alpine:3.20 \
    tar czf "/backup/redis_data.tar.gz" -C /data . \
    && log "Redis volume backed up" \
    || log "[WARN] Redis volume backup failed — continuing (Redis data is cache-only)"
else
  log "[WARN] No Redis volume found — skipping"
fi

# ── 4. Save compose file snapshot ────────────────────────────────────────────
log "Step 4: Compose snapshot"
COMPOSE_SRC=$(ls "${DEPLOY_DIR}"/docker-compose.*.yml 2>/dev/null | head -1 || echo "")
if [[ -f "${COMPOSE_SRC}" ]]; then
  cp "${COMPOSE_SRC}" "${BACKUP_PATH}/docker-compose.yml"
  log "Compose snapshot saved"
else
  log "[WARN] No compose file found in ${DEPLOY_DIR}"
fi

# ── 5. Backup nginx config ────────────────────────────────────────────────────
if [[ -d "${DEPLOY_DIR}/nginx" ]]; then
  cp -r "${DEPLOY_DIR}/nginx" "${BACKUP_PATH}/nginx"
  log "Nginx config backed up"
fi

# ── 6. Record .env file checksums (NOT contents — no secrets in backup) ───────
for env_file in "${DEPLOY_DIR}"/.env.*; do
  [[ -f "${env_file}" ]] || continue
  sha256sum "${env_file}" >> "${BACKUP_PATH}/env_checksums.txt"
done
log "Env checksums recorded"

# ── 7. Rotate old backups (keep last 30) ─────────────────────────────────────
log "Step 7: Backup rotation"
BACKUP_COUNT=$(find "${BACKUP_DIR}" -maxdepth 1 -name "[0-9]*" -type d 2>/dev/null | wc -l)
if (( BACKUP_COUNT > 30 )); then
  TO_DELETE=$(ls -dt "${BACKUP_DIR}"/[0-9]*/ 2>/dev/null | tail -n +31)
  for dir in ${TO_DELETE}; do
    rm -rf "${dir}"
    log "Removed old backup: $(basename "${dir}")"
  done
  # Also clean up old metadata files beyond 30
  # shellcheck disable=SC2012
  ls -t "${BACKUP_DIR}"/metadata_*.json 2>/dev/null | tail -n +31 | xargs -r rm -f
fi

log "Backup complete: ${BACKUP_PATH}"
log "Total backups retained: $(find "${BACKUP_DIR}" -maxdepth 1 -name "[0-9]*" -type d 2>/dev/null | wc -l)"
