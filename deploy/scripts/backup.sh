#!/usr/bin/env bash
# =============================================================================
# backup.sh — Pre-deployment backup of Docker state and volumes
#
# Usage:
#   ./backup.sh <environment>
#
# Creates a timestamped backup in $DEPLOY_DIR/backups/ containing:
#   - docker-compose.*.yml snapshot
#   - named volume data (redis_data)
#   - current image tags metadata
#   - .env files (metadata only — no secrets in git)
#
# Retains the last 30 backups and removes older ones automatically.
# =============================================================================

set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment>}"

case "$ENVIRONMENT" in
  production) DEPLOY_DIR="/opt/hadha" ;;
  staging)    DEPLOY_DIR="/opt/hadha-staging" ;;
  *) echo "[ERROR] Unknown environment: ${ENVIRONMENT}"; exit 1 ;;
esac

BACKUP_DIR="${DEPLOY_DIR}/backups"
TIMESTAMP=$(date +'%Y%m%dT%H%M%S')
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"
LOG_FILE="${DEPLOY_DIR}/backup.log"

log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }

mkdir -p "${BACKUP_PATH}"

log "Starting backup → ${BACKUP_PATH}"

# ── 1. Save compose file snapshot ────────────────────────────────────────────
COMPOSE_SRC=$(ls "${DEPLOY_DIR}"/docker-compose.*.yml 2>/dev/null | head -1)
if [[ -f "${COMPOSE_SRC}" ]]; then
  cp "${COMPOSE_SRC}" "${BACKUP_PATH}/docker-compose.yml"
  log "Compose snapshot saved"
fi

# ── 2. Capture current running image tags ────────────────────────────────────
BACKEND_IMAGE=$(docker inspect  hadha-backend  --format='{{.Config.Image}}' 2>/dev/null || echo "")
FRONTEND_IMAGE=$(docker inspect hadha-frontend --format='{{.Config.Image}}' 2>/dev/null || echo "")

cat > "${BACKUP_DIR}/metadata_${TIMESTAMP}.json" <<EOF
{
  "timestamp":      "${TIMESTAMP}",
  "environment":    "${ENVIRONMENT}",
  "backend_image":  "${BACKEND_IMAGE}",
  "frontend_image": "${FRONTEND_IMAGE}",
  "git_sha":        "${GIT_COMMIT_SHA:-unknown}",
  "git_author":     "${GIT_COMMIT_AUTHOR:-unknown}"
}
EOF
log "Image metadata saved: metadata_${TIMESTAMP}.json"

# ── 3. Backup Redis volume ────────────────────────────────────────────────────
REDIS_VOLUME=$(docker volume ls -q | grep -E "hadha.*redis" | head -1 || echo "")
if [[ -n "${REDIS_VOLUME}" ]]; then
  log "Backing up Redis volume: ${REDIS_VOLUME}"
  docker run --rm \
    -v "${REDIS_VOLUME}:/data:ro" \
    -v "${BACKUP_PATH}:/backup" \
    alpine:3.20 \
    tar czf "/backup/redis_data.tar.gz" -C /data . \
    && log "Redis volume backed up" \
    || log "[WARN] Redis volume backup failed"
fi

# ── 4. Backup nginx config ────────────────────────────────────────────────────
if [[ -d "${DEPLOY_DIR}/nginx" ]]; then
  cp -r "${DEPLOY_DIR}/nginx" "${BACKUP_PATH}/nginx"
  log "Nginx config backed up"
fi

# ── 5. Record .env file checksums (NOT contents — no secrets in backup) ───────
for env_file in "${DEPLOY_DIR}"/.env.*; do
  [[ -f "${env_file}" ]] || continue
  echo "$(sha256sum "${env_file}")" >> "${BACKUP_PATH}/env_checksums.txt"
done
log "Env checksums recorded"

# ── 6. Rotate old backups (keep last 30) ─────────────────────────────────────
BACKUP_COUNT=$(ls -d "${BACKUP_DIR}"/[0-9]* 2>/dev/null | wc -l)
if (( BACKUP_COUNT > 30 )); then
  TO_DELETE=$(ls -dt "${BACKUP_DIR}"/[0-9]* 2>/dev/null | tail -n +31)
  for dir in ${TO_DELETE}; do
    rm -rf "${dir}"
    log "Removed old backup: $(basename "${dir}")"
  done
  # Also clean up old metadata files
  ls -t "${BACKUP_DIR}"/metadata_*.json 2>/dev/null | tail -n +31 | xargs rm -f
fi

log "Backup complete: ${BACKUP_PATH}"
log "Total backups retained: $(ls -d "${BACKUP_DIR}"/[0-9]* 2>/dev/null | wc -l)"
