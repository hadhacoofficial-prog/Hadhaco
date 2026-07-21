#!/usr/bin/env bash
# =============================================================================
# restore.sh — Restore from backup for Hadha.co
#
# Usage:
#   ./restore.sh [backup_id]
#   ./restore.sh backup-20260101-120000
#   ./restore.sh (uses latest backup)
# =============================================================================

set -uo pipefail

APP_DIR="/opt/hadha"
BACKUP_DIR="${APP_DIR}/backups"
APP_COMPOSE="${APP_DIR}/docker-compose.application.yml"
ENV_FILE="${APP_DIR}/.env.production"
LOG_FILE="${APP_DIR}/deploy.log"
NETWORK_NAME="hadha"

log() { echo "[$(date +'%H:%M:%S')] $*"; }
log_section() { log ""; log "════════ RESTORE ════════"; log "  $*"; log "══════════════════════════"; }

# ── Resolve backup ────────────────────────────────────────────────────────────
if [[ -n "${1:-}" ]]; then
  BACKUP_ID="$1"
  BACKUP_PATH="${BACKUP_DIR}/${BACKUP_ID}"
else
  BACKUP_PATH=$(ls -1d "${BACKUP_DIR}"/backup-* 2>/dev/null | tail -1)
  if [[ -z "${BACKUP_PATH}" ]]; then
    echo "No backups found in ${BACKUP_DIR}"
    exit 1
  fi
  BACKUP_ID=$(basename "${BACKUP_PATH}")
fi

if [[ ! -d "${BACKUP_PATH}" ]]; then
  echo "Backup not found: ${BACKUP_PATH}"
  exit 1
fi

log_section "Restoring from backup: ${BACKUP_ID}"
log "Backup path: ${BACKUP_PATH}"

# ── Confirm ───────────────────────────────────────────────────────────────────
echo ""
echo "This will restore the following from backup:"
echo "  - Compose files"
echo "  - Nginx configuration"
echo "  - Redis data volume"
echo "  - Monitoring configurations"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""
[[ $REPLY =~ ^[Yy]$ ]] || { log "Aborted"; exit 0; }

# ── Restore compose files ─────────────────────────────────────────────────────
log "Restoring compose files..."
for f in docker-compose.infrastructure.yml docker-compose.application.yml; do
  if [[ -f "${BACKUP_PATH}/${f}" ]]; then
    cp -f "${BACKUP_PATH}/${f}" "${APP_DIR}/${f}"
    log "  Restored: ${f}"
  fi
done

# ── Restore nginx config ──────────────────────────────────────────────────────
log "Restoring nginx configuration..."
if [[ -f "${BACKUP_PATH}/nginx-config.tar.gz" ]]; then
  tar xzf "${BACKUP_PATH}/nginx-config.tar.gz" -C "${APP_DIR}" 2>/dev/null \
    && log "  Nginx config restored" \
    || log "[WARN] Nginx restore failed"
fi

# ── Restore Redis data ────────────────────────────────────────────────────────
log "Restoring Redis volume..."
if [[ -f "${BACKUP_PATH}/redis-data.tar.gz" ]]; then
  log "  Stopping Redis..."
  docker stop hadha-redis 2>/dev/null || true

  log "  Restoring data..."
  docker run --rm \
    -v hadha_redis_data:/data \
    -v "${BACKUP_PATH}:/backup:ro" \
    alpine sh -c "rm -rf /data/* && tar xzf /backup/redis-data.tar.gz -C /data" 2>/dev/null \
    && log "  Redis data restored" \
    || log "[WARN] Redis restore failed"

  log "  Starting Redis..."
  docker start hadha-redis 2>/dev/null || true
fi

# ── Restore monitoring configs ────────────────────────────────────────────────
log "Restoring monitoring configurations..."
if [[ -f "${BACKUP_PATH}/monitoring-config.tar.gz" ]]; then
  tar xzf "${BACKUP_PATH}/monitoring-config.tar.gz" -C "${APP_DIR}" 2>/dev/null \
    && log "  Monitoring configs restored" \
    || log "[WARN] Monitoring config restore failed"
fi

# ── Restart services ──────────────────────────────────────────────────────────
log "Restarting services..."

# Ensure network
docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1 || \
  docker network create --driver bridge "${NETWORK_NAME}" 2>/dev/null || true

export REDIS_PASSWORD GLITCHTIP_DSN GLITCHTIP_FRONTEND_DSN

# Restart infrastructure
log "  Restarting infrastructure stack..."
docker compose --env-file "${ENV_FILE}" -f "${APP_DIR}/docker-compose.infrastructure.yml" \
  up -d --remove-orphans 2>&1 | tee -a "${LOG_FILE}" || true

# Restart application
log "  Restarting application stack..."
docker compose --env-file "${ENV_FILE}" -f "${APP_COMPOSE}" \
  up -d --remove-orphans 2>&1 | tee -a "${LOG_FILE}" || true

# ── Health check ──────────────────────────────────────────────────────────────
log "Running post-restore health checks..."
sleep 10

HEALTHY=true
for container in hadha-backend hadha-storefront hadha-admin hadha-redis; do
  STATUS=$(docker inspect --format='{{.State.Status}}' "${container}" 2>/dev/null || echo "not_found")
  if [[ "${STATUS}" != "running" ]]; then
    log "[WARN] ${container} is ${STATUS}"
    HEALTHY=false
  fi
done

if [[ "${HEALTHY}" == "true" ]]; then
  log_section "Restore complete — all services running"
else
  log_section "Restore complete — some services may need attention"
fi
