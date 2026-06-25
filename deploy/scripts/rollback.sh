#!/usr/bin/env bash
# =============================================================================
# rollback.sh — Restore the previous production deployment
#
# Called automatically by deploy.sh on failure, or manually for emergencies.
#
# Usage (from deploy.sh — images passed as args):
#   ./rollback.sh <prev_backend_image> <prev_frontend_image>
#
# Usage (manual emergency — reads images from disk):
#   ./rollback.sh
# =============================================================================

set -uo pipefail

PREV_BACKEND="${1:-}"
PREV_FRONTEND="${2:-}"

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
if [[ -z "${PREV_BACKEND}" ]] || [[ -z "${PREV_FRONTEND}" ]]; then
  log "No image arguments provided — reading previous images from disk"

  if [[ -f "${PREVIOUS_IMAGES_FILE}" ]]; then
    PREV_BACKEND=$(jq -r '.backend_image // empty'  "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
    PREV_FRONTEND=$(jq -r '.frontend_image // empty' "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
    [[ -n "${PREV_BACKEND}" ]] && log "Previous images loaded from ${PREVIOUS_IMAGES_FILE}"
  fi

  if [[ -z "${PREV_BACKEND}" ]]; then
    log "Disk file not available — trying backup metadata"
    LATEST_META=$(ls -t "${BACKUP_DIR}"/metadata_*.json 2>/dev/null | head -1 || echo "")
    if [[ -n "${LATEST_META}" ]]; then
      log "Using metadata: ${LATEST_META}"
      PREV_BACKEND=$(jq -r '.backend_image // empty'  "${LATEST_META}" 2>/dev/null || echo "")
      PREV_FRONTEND=$(jq -r '.frontend_image // empty' "${LATEST_META}" 2>/dev/null || echo "")
    fi
  fi
fi

[[ -n "${PREV_BACKEND}"  ]] || die "Cannot determine previous backend image for rollback. No disk file or backup metadata found."
[[ -n "${PREV_FRONTEND}" ]] || die "Cannot determine previous frontend image for rollback. No disk file or backup metadata found."

log "Rolling back to:"
log "  Backend  → ${PREV_BACKEND}"
log "  Frontend → ${PREV_FRONTEND}"

[[ -f "${ENV_FILE}" ]] || die "Env file not found: ${ENV_FILE}"

# ── Pull previous images ──────────────────────────────────────────────────────
log "Pulling previous images (will use local cache if pull fails)..."
docker pull "${PREV_BACKEND}"  2>&1 || log "[WARN] Pull failed for ${PREV_BACKEND} — using local cache"
docker pull "${PREV_FRONTEND}" 2>&1 || log "[WARN] Pull failed for ${PREV_FRONTEND} — using local cache"

docker image inspect "${PREV_BACKEND}"  >/dev/null 2>&1 \
  || die "Previous backend image not available locally: ${PREV_BACKEND}"
docker image inspect "${PREV_FRONTEND}" >/dev/null 2>&1 \
  || die "Previous frontend image not available locally: ${PREV_FRONTEND}"

export BACKEND_IMAGE="${PREV_BACKEND}"
export FRONTEND_IMAGE="${PREV_FRONTEND}"

if [[ -z "${REDIS_PASSWORD:-}" ]] && [[ -f "${ENV_FILE}" ]]; then
  REDIS_PASSWORD=$(grep -E '^REDIS_PASSWORD=' "${ENV_FILE}" | head -1 | cut -d= -f2-)
  log "REDIS_PASSWORD loaded from ${ENV_FILE}"
fi
export REDIS_PASSWORD="${REDIS_PASSWORD:-}"

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
  die "Rollback health check failed — manual intervention required. Previous images: ${PREV_BACKEND} / ${PREV_FRONTEND}"
fi
