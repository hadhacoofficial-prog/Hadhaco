#!/usr/bin/env bash
# =============================================================================
# rollback.sh — Restore the previous deployment
#
# Usage:
#   ./rollback.sh <environment> [previous_backend_image] [previous_frontend_image]
#
# When called from deploy.sh, the previous images are passed as arguments.
# When called manually for emergency rollback, omit image arguments and the
# script will restore from the most recent backup metadata.
# =============================================================================

set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment> [prev_backend_image] [prev_frontend_image]}"
PREV_BACKEND="${2:-}"
PREV_FRONTEND="${3:-}"

# ── Config ────────────────────────────────────────────────────────────────────
case "$ENVIRONMENT" in
  production)
    DEPLOY_DIR="/opt/hadha"
    COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.production.yml"
    ;;
  staging)
    DEPLOY_DIR="/opt/hadha-staging"
    COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.staging.yml"
    ;;
  *)
    echo "[ERROR] Unknown environment: ${ENVIRONMENT}"
    exit 1
    ;;
esac

BACKUP_DIR="${DEPLOY_DIR}/backups"
LOG_FILE="${DEPLOY_DIR}/rollback.log"
SCRIPTS_DIR="${DEPLOY_DIR}/scripts"

log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }
die() { log "[FATAL] $*"; exit 1; }

log "════ ROLLBACK INITIATED ════"
log "Environment: ${ENVIRONMENT}"

# ── Resolve previous images from backup metadata if not passed ────────────────
if [[ -z "${PREV_BACKEND}" ]] || [[ -z "${PREV_FRONTEND}" ]]; then
  log "No image args — reading from most recent backup metadata"
  LATEST_META=$(ls -t "${BACKUP_DIR}"/metadata_*.json 2>/dev/null | head -1 || echo "")
  if [[ -z "${LATEST_META}" ]]; then
    die "No backup metadata found in ${BACKUP_DIR} and no image arguments provided"
  fi
  log "Using metadata: ${LATEST_META}"
  # Fix: || echo "" (not || "") — bash subshell must produce output, not evaluate a string
  PREV_BACKEND=$(python3  -c "import json; d=json.load(open('${LATEST_META}')); print(d['backend_image'])"  2>/dev/null || echo "")
  PREV_FRONTEND=$(python3 -c "import json; d=json.load(open('${LATEST_META}')); print(d['frontend_image'])" 2>/dev/null || echo "")
fi

[[ -n "${PREV_BACKEND}"  ]] || die "Cannot determine previous backend image for rollback"
[[ -n "${PREV_FRONTEND}" ]] || die "Cannot determine previous frontend image for rollback"

log "Rolling back to:"
log "  Backend  → ${PREV_BACKEND}"
log "  Frontend → ${PREV_FRONTEND}"

# ── Pull previous images (they should already be cached locally) ──────────────
log "Pulling previous images..."
docker pull "${PREV_BACKEND}"  || log "[WARN] Could not pull ${PREV_BACKEND} — using local cache"
docker pull "${PREV_FRONTEND}" || log "[WARN] Could not pull ${PREV_FRONTEND} — using local cache"

# ── Restart with previous images ─────────────────────────────────────────────
log "Restarting containers with previous images..."
export BACKEND_IMAGE="${PREV_BACKEND}"
export FRONTEND_IMAGE="${PREV_FRONTEND}"
export REDIS_PASSWORD="${REDIS_PASSWORD:-}"

docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans --pull never \
  || die "Failed to restart containers during rollback"

# ── Health check after rollback ───────────────────────────────────────────────
log "Running health checks on rolled-back deployment..."
sleep 15

if "${SCRIPTS_DIR}/healthcheck.sh" "${ENVIRONMENT}"; then
  log "Rollback successful — deployment is healthy"
  exit 0
else
  die "Rollback health check failed — manual intervention required"
fi
