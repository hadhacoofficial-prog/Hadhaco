#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Hadha.co Production / Staging Deployment Script
#
# Usage:
#   ./deploy.sh <environment> <image_tag>
#   ./deploy.sh production sha-abc1234
#   ./deploy.sh staging    develop-abc1234
#
# Environment variables (set by caller / CI secrets):
#   GHCR_TOKEN          — GitHub Container Registry read token
#   GHCR_USERNAME       — GitHub username / org
#   RESEND_API_KEY      — Resend email API key
#   RESEND_FROM_EMAIL   — Notification sender address
#   RESEND_TO_EMAIL     — Notification recipient address
#   REDIS_PASSWORD      — Redis auth password
#   GIT_COMMIT_SHA      — Full commit SHA (set by CI)
#   GIT_COMMIT_AUTHOR   — Commit author (set by CI)
# =============================================================================

set -euo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────
ENVIRONMENT="${1:?Usage: $0 <environment> <image_tag>}"
IMAGE_TAG="${2:?Usage: $0 <environment> <image_tag>}"
DEPLOY_START=$(date +%s)

# ── Environment-specific config ───────────────────────────────────────────────
case "$ENVIRONMENT" in
  production)
    DEPLOY_DIR="/opt/hadha"
    COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.production.yml"
    GHCR_OWNER="${GHCR_USERNAME}"
    BACKEND_IMAGE="ghcr.io/${GHCR_OWNER}/hadha-backend:${IMAGE_TAG}"
    FRONTEND_IMAGE="ghcr.io/${GHCR_OWNER}/hadha-frontend:${IMAGE_TAG}"
    APP_URL="https://hadha.co"
    ;;
  staging)
    DEPLOY_DIR="/opt/hadha-staging"
    COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.staging.yml"
    GHCR_OWNER="${GHCR_USERNAME}"
    BACKEND_IMAGE="ghcr.io/${GHCR_OWNER}/hadha-backend:${IMAGE_TAG}"
    FRONTEND_IMAGE="ghcr.io/${GHCR_OWNER}/hadha-frontend:${IMAGE_TAG}"
    APP_URL="https://staging.hadha.co"
    ;;
  *)
    echo "[ERROR] Unknown environment: ${ENVIRONMENT}. Use 'production' or 'staging'."
    exit 1
    ;;
esac

BACKUP_DIR="${DEPLOY_DIR}/backups"
SCRIPTS_DIR="${DEPLOY_DIR}/scripts"
LOG_FILE="${DEPLOY_DIR}/deploy.log"

# ── Logging ───────────────────────────────────────────────────────────────────
log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }
log_section() { log ""; log "═══ $* ═══"; }
die() { log "[FATAL] $*"; exit 1; }

# ── Validation ────────────────────────────────────────────────────────────────
log_section "Pre-flight checks"

[[ -d "${DEPLOY_DIR}" ]] || die "Deploy directory ${DEPLOY_DIR} does not exist. Run bootstrap.sh first."
[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
command -v docker  >/dev/null 2>&1 || die "docker is not installed"
command -v curl    >/dev/null 2>&1 || die "curl is not installed"

log "Environment : ${ENVIRONMENT}"
log "Image tag   : ${IMAGE_TAG}"
log "Backend     : ${BACKEND_IMAGE}"
log "Frontend    : ${FRONTEND_IMAGE}"
log "Deploy dir  : ${DEPLOY_DIR}"

# ── Step 1: Backup current state ──────────────────────────────────────────────
log_section "Step 1: Backup"
"${SCRIPTS_DIR}/backup.sh" "${ENVIRONMENT}" || {
  log "[WARN] Backup failed — continuing anyway"
}

# ── Save current image tags for rollback ──────────────────────────────────────
PREVIOUS_BACKEND_IMAGE=$(docker inspect hadha-backend  --format='{{.Config.Image}}' 2>/dev/null || echo "")
PREVIOUS_FRONTEND_IMAGE=$(docker inspect hadha-frontend --format='{{.Config.Image}}' 2>/dev/null || echo "")
export PREVIOUS_BACKEND_IMAGE PREVIOUS_FRONTEND_IMAGE
log "Previous backend  : ${PREVIOUS_BACKEND_IMAGE:-none}"
log "Previous frontend : ${PREVIOUS_FRONTEND_IMAGE:-none}"

# ── Step 2: Pull new images ────────────────────────────────────────────────────
log_section "Step 2: Pull images"

echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin \
  || die "GHCR login failed"

docker pull "${BACKEND_IMAGE}"  || die "Failed to pull backend image"
docker pull "${FRONTEND_IMAGE}" || die "Failed to pull frontend image"

log "Images pulled successfully"

# ── Step 3: Run database migrations ───────────────────────────────────────────
log_section "Step 3: Database migrations"

docker run --rm \
  --env-file "${DEPLOY_DIR}/.env.production" \
  --network hadha-internal \
  --add-host host.docker.internal:host-gateway \
  "${BACKEND_IMAGE}" \
  python -m alembic upgrade head \
  && log "Migrations applied successfully" \
  || {
    log "[ERROR] Migrations failed — aborting deployment"
    notify_failure "Database migration failed" "${LOG_FILE}"
    exit 1
  }

# ── Step 4: Update running containers ─────────────────────────────────────────
log_section "Step 4: Restart containers"

export BACKEND_IMAGE FRONTEND_IMAGE REDIS_PASSWORD

docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans --pull never \
  && log "Containers restarted" \
  || {
    log "[ERROR] Container restart failed"
    rollback_and_exit "Container restart failed"
  }

# ── Step 5: Health checks ──────────────────────────────────────────────────────
log_section "Step 5: Health checks"

"${SCRIPTS_DIR}/healthcheck.sh" "${ENVIRONMENT}" || {
  log "[ERROR] Health checks failed — initiating rollback"
  rollback_and_exit "Health checks failed after deployment"
}

# ── Step 6: Cleanup old images ─────────────────────────────────────────────────
log_section "Step 6: Cleanup"
docker image prune -f --filter "until=24h" 2>/dev/null || true

# ── Step 7: Success notification ──────────────────────────────────────────────
DEPLOY_END=$(date +%s)
DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))

log_section "Deployment complete"
log "Duration: ${DEPLOY_DURATION}s"

"${SCRIPTS_DIR}/notify.sh" success \
  "${ENVIRONMENT}" \
  "${IMAGE_TAG}" \
  "${GIT_COMMIT_SHA:-unknown}" \
  "${GIT_COMMIT_AUTHOR:-unknown}" \
  "${DEPLOY_DURATION}" \
  "" \
  2>/dev/null || log "[WARN] Success notification failed — deployment itself succeeded"

exit 0

# ── Rollback helper ────────────────────────────────────────────────────────────
rollback_and_exit() {
  local reason="$1"
  log "[ERROR] ${reason}"
  "${SCRIPTS_DIR}/rollback.sh" "${ENVIRONMENT}" \
    "${PREVIOUS_BACKEND_IMAGE:-}" \
    "${PREVIOUS_FRONTEND_IMAGE:-}" \
    || log "[FATAL] Rollback also failed — manual intervention required"

  DEPLOY_END=$(date +%s)
  DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
  LAST_100_LINES=$(tail -100 "${LOG_FILE}" 2>/dev/null || echo "No logs available")

  "${SCRIPTS_DIR}/notify.sh" failure \
    "${ENVIRONMENT}" \
    "${IMAGE_TAG}" \
    "${GIT_COMMIT_SHA:-unknown}" \
    "${GIT_COMMIT_AUTHOR:-unknown}" \
    "${DEPLOY_DURATION}" \
    "${reason}" \
    "${LAST_100_LINES}" \
    2>/dev/null || true

  exit 1
}
