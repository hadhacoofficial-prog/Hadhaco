#!/usr/bin/env bash
# =============================================================================
# rollback.sh — Restore the previous production deployment
#
# Called automatically by deploy.sh on failure, or manually for emergencies.
#
# Usage (from deploy.sh — images passed as args):
#   ./rollback.sh <prev_backend_image> <prev_storefront_image> <prev_admin_image>
#
# Usage (manual emergency — reads images from disk):
#   ./rollback.sh
# =============================================================================

set -uo pipefail

PREV_BACKEND="${1:-}"
PREV_STOREFRONT="${2:-}"
PREV_ADMIN="${3:-}"

APP_DIR="/opt/hadha"
COMPOSE_FILE="${APP_DIR}/docker-compose.production.yml"
ENV_FILE="${APP_DIR}/.env.production"
BACKUP_DIR="${APP_DIR}/backups"
LOG_FILE="${APP_DIR}/rollback.log"
SCRIPTS_DIR="${APP_DIR}/scripts"
PREVIOUS_IMAGES_FILE="${APP_DIR}/.previous_images"
ROLLBACK_START=$(date +%s)

log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }
die() { log "[FATAL] $*"; exit 1; }

dc() {
  docker compose \
    --env-file "${ENV_FILE}" \
    -f "${COMPOSE_FILE}" \
    "$@"
}

log ""
log "════ ROLLBACK INITIATED ════"
log "Started at  : $(date +'%Y-%m-%dT%H:%M:%S%z')"

# ── Resolve previous images ───────────────────────────────────────────────────
if [[ -z "${PREV_BACKEND}" ]] || [[ -z "${PREV_STOREFRONT}" ]] || [[ -z "${PREV_ADMIN}" ]]; then
  log "No image arguments provided — reading previous images from disk"

  if [[ -f "${PREVIOUS_IMAGES_FILE}" ]]; then
    PREV_BACKEND=$(jq -r '.backend_image // empty'    "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
    PREV_STOREFRONT=$(jq -r '.storefront_image // empty' "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
    PREV_ADMIN=$(jq -r '.admin_image // empty'        "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
    [[ -n "${PREV_BACKEND}" ]] && log "Previous images loaded from ${PREVIOUS_IMAGES_FILE}"
  fi

  if [[ -z "${PREV_BACKEND}" ]]; then
    log "Disk file not available — trying backup metadata"
    LATEST_META=$(ls -t "${BACKUP_DIR}"/metadata_*.json 2>/dev/null | head -1 || echo "")
    if [[ -n "${LATEST_META}" ]]; then
      log "Using metadata: ${LATEST_META}"
      PREV_BACKEND=$(jq -r '.backend_image // empty'    "${LATEST_META}" 2>/dev/null || echo "")
      PREV_STOREFRONT=$(jq -r '.storefront_image // empty' "${LATEST_META}" 2>/dev/null || echo "")
      PREV_ADMIN=$(jq -r '.admin_image // empty'        "${LATEST_META}" 2>/dev/null || echo "")
    fi
  fi
fi

[[ -n "${PREV_BACKEND}"    ]] || die "Cannot determine previous backend image for rollback. No disk file or backup metadata found."
[[ -n "${PREV_STOREFRONT}" ]] || die "Cannot determine previous storefront image for rollback. No disk file or backup metadata found."
[[ -n "${PREV_ADMIN}"      ]] || die "Cannot determine previous admin image for rollback. No disk file or backup metadata found."

log "Rolling back to:"
log "  Backend    → ${PREV_BACKEND}"
log "  Storefront → ${PREV_STOREFRONT}"
log "  Admin      → ${PREV_ADMIN}"

[[ -f "${ENV_FILE}" ]] || die "Env file not found: ${ENV_FILE}"

# ── Pull previous images ──────────────────────────────────────────────────────
log "Pulling previous images (will use local cache if pull fails)..."
docker pull "${PREV_BACKEND}"    2>&1 || log "[WARN] Pull failed for ${PREV_BACKEND} — using local cache"
docker pull "${PREV_STOREFRONT}" 2>&1 || log "[WARN] Pull failed for ${PREV_STOREFRONT} — using local cache"
docker pull "${PREV_ADMIN}"      2>&1 || log "[WARN] Pull failed for ${PREV_ADMIN} — using local cache"

docker image inspect "${PREV_BACKEND}"    >/dev/null 2>&1 \
  || die "Previous backend image not available locally: ${PREV_BACKEND}"
docker image inspect "${PREV_STOREFRONT}" >/dev/null 2>&1 \
  || die "Previous storefront image not available locally: ${PREV_STOREFRONT}"
docker image inspect "${PREV_ADMIN}"      >/dev/null 2>&1 \
  || die "Previous admin image not available locally: ${PREV_ADMIN}"

export BACKEND_IMAGE="${PREV_BACKEND}"
export STOREFRONT_IMAGE="${PREV_STOREFRONT}"
export ADMIN_IMAGE="${PREV_ADMIN}"

if [[ -z "${REDIS_PASSWORD:-}" ]] && [[ -f "${ENV_FILE}" ]]; then
  REDIS_PASSWORD=$(grep -E '^REDIS_PASSWORD=' "${ENV_FILE}" | head -1 | cut -d= -f2-)
  log "REDIS_PASSWORD loaded from ${ENV_FILE}"
fi
export REDIS_PASSWORD="${REDIS_PASSWORD:-}"

# ── Ensure file-mount paths are files, not directories ─────────────────────────
FILE_MOUNT_PATHS=(
  "${APP_DIR}/dozzle/users.yml"
  "${APP_DIR}/nginx/nginx.conf"
  "${APP_DIR}/monitoring/prometheus/prometheus.yml"
  "${APP_DIR}/monitoring/loki/loki-config.yml"
  "${APP_DIR}/monitoring/promtail/promtail-config.yml"
)
for fpath in "${FILE_MOUNT_PATHS[@]}"; do
  if [[ -d "${fpath}" ]]; then
    log "[FIX] ${fpath} is a directory — removing (stale mount path)"
    sudo rm -rf "${fpath}"
  fi
done

# ── Restart with previous images ──────────────────────────────────────────────
log "Restarting containers with previous images..."
if ! dc up -d --remove-orphans --pull never 2>&1 | tee -a "${LOG_FILE}"; then
  die "Failed to restart containers during rollback — manual intervention required"
fi

# ── Health check after rollback ───────────────────────────────────────────────
log "Running health checks on rolled-back deployment..."
if "${SCRIPTS_DIR}/healthcheck.sh" 2>&1 | tee -a "${LOG_FILE}"; then
  ROLLBACK_END=$(date +%s)
  log "Rollback succeeded in $(( ROLLBACK_END - ROLLBACK_START ))s — deployment is healthy"
  exit 0
else
  die "Rollback health check failed — manual intervention required. Previous images: ${PREV_BACKEND} / ${PREV_STOREFRONT} / ${PREV_ADMIN}"
fi
