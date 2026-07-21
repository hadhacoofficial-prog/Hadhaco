#!/usr/bin/env bash
# =============================================================================
# backup.sh — Pre-deployment backup for Hadha.co
#
# Backs up: image metadata, Redis volume, compose files, nginx config, env checksums
# Retention: keeps last 30 backups
# =============================================================================

set -uo pipefail

APP_DIR="/opt/hadha"
BACKUP_DIR="${APP_DIR}/backups"
TIMESTAMP=$(date +'%Y%m%d-%H%M%S')
BACKUP_NAME="backup-${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"
RETENTION=30

log() { echo "[$(date +'%H:%M:%S')] $*"; }

mkdir -p "${BACKUP_PATH}"

log "Starting backup: ${BACKUP_NAME}"

# ── Image metadata ────────────────────────────────────────────────────────────
log "Backing up container image metadata..."
docker inspect hadha-backend hadha-storefront hadha-admin 2>/dev/null \
  > "${BACKUP_PATH}/container-images.json" || log "[WARN] Could not inspect containers"

# ── Redis volume ──────────────────────────────────────────────────────────────
log "Backing up Redis volume..."
if docker inspect hadha-redis >/dev/null 2>&1; then
  docker run --rm \
    -v hadha_redis_data:/data:ro \
    -v "${BACKUP_PATH}:/backup" \
    alpine tar czf /backup/redis-data.tar.gz -C /data . 2>/dev/null \
    && log "  Redis backup complete" \
    || log "[WARN] Redis backup failed"
else
  log "[WARN] Redis container not running — skipping volume backup"
fi

# ── Compose files ─────────────────────────────────────────────────────────────
log "Backing up compose files..."
for f in docker-compose.infrastructure.yml docker-compose.application.yml; do
  [[ -f "${APP_DIR}/${f}" ]] && cp -f "${APP_DIR}/${f}" "${BACKUP_PATH}/${f}"
done

# ── Nginx config ──────────────────────────────────────────────────────────────
log "Backing up nginx config..."
if [[ -d "${APP_DIR}/nginx" ]]; then
  tar czf "${BACKUP_PATH}/nginx-config.tar.gz" -C "${APP_DIR}" nginx/ 2>/dev/null \
    || log "[WARN] Nginx backup failed"
fi

# ── Environment files ─────────────────────────────────────────────────────────
log "Backing up environment file checksums..."
for envfile in .env.production .env.storefront.production .env.admin.production; do
  if [[ -f "${APP_DIR}/${envfile}" ]]; then
    sha256sum "${APP_DIR}/${envfile}" > "${BACKUP_PATH}/${envfile}.sha256"
  fi
done

# ── Monitoring configs ────────────────────────────────────────────────────────
log "Backing up monitoring configs..."
if [[ -d "${APP_DIR}/monitoring" ]]; then
  tar czf "${BACKUP_PATH}/monitoring-config.tar.gz" -C "${APP_DIR}" monitoring/ 2>/dev/null \
    || log "[WARN] Monitoring config backup failed"
fi

# ── Previous images state ─────────────────────────────────────────────────────
log "Backing up deployment state..."
[[ -f "${APP_DIR}/.previous_images" ]] && cp -f "${APP_DIR}/.previous_images" "${BACKUP_PATH}/previous-images.json"
[[ -f "${APP_DIR}/.bootstrap-state.json" ]] && cp -f "${APP_DIR}/.bootstrap-state.json" "${BACKUP_PATH}/bootstrap-state.json"

# ── Backup rotation ───────────────────────────────────────────────────────────
log "Rotating backups (keeping last ${RETENTION})..."
BACKUP_COUNT=$(ls -1d "${BACKUP_DIR}"/backup-* 2>/dev/null | wc -l)
if [[ "${BACKUP_COUNT}" -gt "${RETENTION}" ]]; then
  REMOVE_COUNT=$(( BACKUP_COUNT - RETENTION ))
  ls -1d "${BACKUP_DIR}"/backup-* | head -n "${REMOVE_COUNT}" | while read -r old; do
    log "  Removing old backup: $(basename "${old}")"
    rm -rf "${old}"
  done
fi

log "Backup complete: ${BACKUP_PATH}"
log "Backup size: $(du -sh "${BACKUP_PATH}" 2>/dev/null | awk '{print $1}')"
