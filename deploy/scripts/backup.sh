#!/usr/bin/env bash
# =============================================================================
# backup.sh — Pre-deployment backup of Docker state and volumes
#
# Usage:
#   ./backup.sh <environment>
#
# Creates a timestamped backup in $DEPLOY_DIR/backups/ containing:
#   - Current image tag metadata (JSON)
#   - Redis volume data (tar.gz)
#   - docker-compose.*.yml snapshot
#   - nginx configuration
#   - .env checksums (no secret values)
#
# Database: Supabase (managed PostgreSQL).
#   No local pg_dump is performed here. The database lives in Supabase, not
#   on this VPS. Use the Supabase dashboard for point-in-time recovery.
#   See DEVOPS.md § "Disaster Recovery" for the full restore procedure.
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

log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }

mkdir -p "${BACKUP_PATH}"
log "Starting backup → ${BACKUP_PATH}"
log "Database provider: Supabase (managed)"
log "Skipping local PostgreSQL backup — database is hosted by Supabase, not this VPS."
log "Using managed PostgreSQL service. See DEVOPS.md for point-in-time recovery."

# ── 1. Capture current running image tags ────────────────────────────────────
log "Step 1: Image metadata"
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

# ── 2. Backup Redis volume ────────────────────────────────────────────────────
log "Step 2: Redis volume backup"
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

# ── 3. Save compose file snapshot ────────────────────────────────────────────
log "Step 3: Compose snapshot"
COMPOSE_SRC=$(ls "${DEPLOY_DIR}"/docker-compose.*.yml 2>/dev/null | head -1 || echo "")
if [[ -f "${COMPOSE_SRC}" ]]; then
  cp "${COMPOSE_SRC}" "${BACKUP_PATH}/docker-compose.yml"
  log "Compose snapshot saved"
else
  log "[WARN] No compose file found in ${DEPLOY_DIR}"
fi

# ── 4. Backup nginx config ────────────────────────────────────────────────────
if [[ -d "${DEPLOY_DIR}/nginx" ]]; then
  cp -r "${DEPLOY_DIR}/nginx" "${BACKUP_PATH}/nginx"
  log "Nginx config backed up"
fi

# ── 5. Record .env file checksums (NOT contents — no secrets in backup) ───────
for env_file in "${DEPLOY_DIR}"/.env.*; do
  [[ -f "${env_file}" ]] || continue
  sha256sum "${env_file}" >> "${BACKUP_PATH}/env_checksums.txt"
done
log "Env checksums recorded"

# ── 6. Rotate old backups (keep last 30) ─────────────────────────────────────
log "Step 6: Backup rotation"
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
