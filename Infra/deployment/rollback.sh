#!/usr/bin/env bash
# =============================================================================
# rollback.sh — Restore previous Hadha.co deployment
#
# Usage:
#   ./rollback.sh <backend_image> <storefront_image> <admin_image>
#   ./rollback.sh (reads from /opt/hadha/.previous_images)
# =============================================================================

set -uo pipefail

APP_DIR="/opt/hadha"
APP_COMPOSE="${APP_DIR}/docker-compose.application.yml"
ENV_FILE="${APP_DIR}/.env.production"
NETWORK_NAME="hadha"
LOG_FILE="${APP_DIR}/deploy.log"
PREVIOUS_IMAGES_FILE="${APP_DIR}/.previous_images"

log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }
log_section() { log ""; log "════════ ROLLBACK ════════"; log "  $*"; log "══════════════════════════"; }

# ── Resolve images ────────────────────────────────────────────────────────────
if [[ $# -ge 3 ]]; then
  BACKEND_IMAGE="$1"
  STOREFRONT_IMAGE="$2"
  ADMIN_IMAGE="$3"
elif [[ -f "${PREVIOUS_IMAGES_FILE}" ]]; then
  BACKEND_IMAGE=$(jq -r '.backend_image // empty' "${PREVIOUS_IMAGES_FILE}")
  STOREFRONT_IMAGE=$(jq -r '.storefront_image // empty' "${PREVIOUS_IMAGES_FILE}")
  ADMIN_IMAGE=$(jq -r '.admin_image // empty' "${PREVIOUS_IMAGES_FILE}")
else
  echo "Usage: $0 <backend_image> <storefront_image> <admin_image>"
  echo "Or ensure ${PREVIOUS_IMAGES_FILE} exists"
  exit 1
fi

[[ -z "${BACKEND_IMAGE}" ]]    && { echo "No previous backend image"; exit 1; }
[[ -z "${STOREFRONT_IMAGE}" ]] && { echo "No previous storefront image"; exit 1; }
[[ -z "${ADMIN_IMAGE}" ]]      && { echo "No previous admin image"; exit 1; }

log_section "Rolling back to previous images"
log "Backend    : ${BACKEND_IMAGE}"
log "Storefront : ${STOREFRONT_IMAGE}"
log "Admin      : ${ADMIN_IMAGE}"

export BACKEND_IMAGE STOREFRONT_IMAGE ADMIN_IMAGE REDIS_PASSWORD \
       GLITCHTIP_DSN GLITCHTIP_FRONTEND_DSN

# ── Pull previous images ──────────────────────────────────────────────────────
log "Pulling previous images..."
for img in "${BACKEND_IMAGE}" "${STOREFRONT_IMAGE}" "${ADMIN_IMAGE}"; do
  log "  Pulling: ${img}"
  docker pull "${img}" 2>&1 | tee -a "${LOG_FILE}" || {
    log "[ERROR] Failed to pull: ${img}"
    exit 1
  }
done

# ── Remove stale containers with file bind mounts ─────────────────────────────
log "Removing stale containers..."
for c in hadha-backend hadha-storefront hadha-admin; do
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qFx "${c}"; then
    docker rm -f "${c}" 2>/dev/null || true
    log "  Removed: ${c}"
  fi
done

# ── Restart application containers with previous images ────────────────────────
log "Restarting application containers..."
docker compose \
  --env-file "${ENV_FILE}" \
  -f "${APP_COMPOSE}" \
  up -d --remove-orphans --pull never 2>&1 | tee -a "${LOG_FILE}" || {
  log "[FATAL] docker compose up failed during rollback"
  exit 1
}

# ── Reload nginx ──────────────────────────────────────────────────────────────
log "Reloading nginx..."
docker exec hadha-nginx nginx -s reload 2>/dev/null || log "[WARN] nginx reload failed"

# ── Health checks ─────────────────────────────────────────────────────────────
log "Running post-rollback health checks..."

HEALTHY=false
MAX_WAIT=120
INTERVAL=5
ELAPSED=0

while (( ELAPSED < MAX_WAIT )); do
  ALL_OK=true

  for container in hadha-backend hadha-storefront hadha-admin; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "${container}" 2>/dev/null || echo "missing")
    if [[ "${STATUS}" != "healthy" ]]; then
      ALL_OK=false
      break
    fi
  done

  if [[ "${ALL_OK}" == "true" ]]; then
    log "✓ All application containers healthy after rollback"
    HEALTHY=true
    break
  fi

  sleep "${INTERVAL}"
  ELAPSED=$(( ELAPSED + INTERVAL ))
done

if [[ "${HEALTHY}" != "true" ]]; then
  log "[ERROR] Some containers not healthy after ${MAX_WAIT}s"
  log "[ERROR] Manual intervention required"
  exit 1
fi

log_section "Rollback complete"
exit 0
