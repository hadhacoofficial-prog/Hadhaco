#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Hadha.co Production / Staging Deployment Script
#
# Usage:
#   ./deploy.sh <environment> <image_tag>
#   ./deploy.sh production sha-abc1234
#   ./deploy.sh staging    develop-abc1234
#
# Required environment variables (exported by caller / CI):
#   GHCR_TOKEN          — GitHub PAT with read:packages scope
#   GHCR_USERNAME       — GitHub org: hadhacoofficial-prog
#   REDIS_PASSWORD      — Redis authentication password
#   RESEND_API_KEY      — Resend email API key
#   RESEND_FROM_EMAIL   — Notification sender address
#   RESEND_TO_EMAIL     — Notification recipient address
#   GIT_COMMIT_SHA      — Full commit SHA
#   GIT_COMMIT_AUTHOR   — Commit author name
# =============================================================================

set -uo pipefail
# NOTE: we do NOT set -e globally so that failures in steps can be handled
# explicitly with rollback logic instead of causing an immediate uncontrolled exit.

# ── Arguments ─────────────────────────────────────────────────────────────────
ENVIRONMENT="${1:?Usage: $0 <environment> <image_tag>}"
IMAGE_TAG="${2:?Usage: $0 <environment> <image_tag>}"
DEPLOY_START=$(date +%s)

# ── Environment-specific config ───────────────────────────────────────────────
case "$ENVIRONMENT" in
  production)
    APP_DIR="/opt/hadha"
    COMPOSE_FILE="${APP_DIR}/docker-compose.production.yml"
    ENV_FILE="${APP_DIR}/.env.production"
    BACKEND_CONTAINER="hadha-backend"
    FRONTEND_CONTAINER="hadha-frontend"
    APP_URL="https://hadha.co"
    ;;
  staging)
    APP_DIR="/opt/hadha-staging"
    COMPOSE_FILE="${APP_DIR}/docker-compose.staging.yml"
    ENV_FILE="${APP_DIR}/.env.staging"
    BACKEND_CONTAINER="hadha-staging-backend"
    FRONTEND_CONTAINER="hadha-staging-frontend"
    APP_URL="https://staging.hadha.co"
    ;;
  *)
    echo "[ERROR] Unknown environment: ${ENVIRONMENT}. Use 'production' or 'staging'."
    exit 1
    ;;
esac

GHCR_ORG="hadhacoofficial-prog"
BACKEND_IMAGE="ghcr.io/${GHCR_ORG}/hadha-backend:${IMAGE_TAG}"
FRONTEND_IMAGE="ghcr.io/${GHCR_ORG}/hadha-frontend:${IMAGE_TAG}"
BACKUP_DIR="${APP_DIR}/backups"
SCRIPTS_DIR="${APP_DIR}/scripts"
LOG_FILE="${APP_DIR}/deploy.log"

# ── Logging ───────────────────────────────────────────────────────────────────
log()         { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }
log_section() { log ""; log "═══════ $* ═══════"; }
die()         { log "[FATAL] $*"; exit 1; }

# ── CRITICAL: rollback helper must be defined BEFORE any code that calls it ───
rollback_and_exit() {
  local reason="${1:-Unknown failure}"
  log "[ERROR] Deployment failed: ${reason}"
  log "[INFO]  Initiating automatic rollback..."

  if [[ -n "${PREVIOUS_BACKEND_IMAGE:-}" ]] && [[ -n "${PREVIOUS_FRONTEND_IMAGE:-}" ]]; then
    "${SCRIPTS_DIR}/rollback.sh" "${ENVIRONMENT}" \
      "${PREVIOUS_BACKEND_IMAGE}" \
      "${PREVIOUS_FRONTEND_IMAGE}" \
      || log "[FATAL] Rollback failed — manual intervention required"
  else
    log "[WARN] No previous images recorded — cannot auto-rollback"
  fi

  DEPLOY_END=$(date +%s)
  DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
  LAST_LOGS=$(tail -100 "${LOG_FILE}" 2>/dev/null || echo "No logs available")

  "${SCRIPTS_DIR}/notify.sh" failure \
    "${ENVIRONMENT}" \
    "${IMAGE_TAG}" \
    "${GIT_COMMIT_SHA:-unknown}" \
    "${GIT_COMMIT_AUTHOR:-unknown}" \
    "${DEPLOY_DURATION}" \
    "${reason}" \
    "${LAST_LOGS}" \
    2>/dev/null || log "[WARN] Failure notification could not be sent"

  exit 1
}

# ── Pre-flight validation ─────────────────────────────────────────────────────
log_section "Pre-flight checks"

[[ -d "${APP_DIR}" ]]      || die "Deploy directory ${APP_DIR} does not exist. Run bootstrap.sh first."
[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
[[ -f "${ENV_FILE}" ]]     || die "Env file not found: ${ENV_FILE}"
command -v docker >/dev/null 2>&1 || die "docker is not installed"
command -v curl   >/dev/null 2>&1 || die "curl is not installed"
command -v jq     >/dev/null 2>&1 || die "jq is not installed (install via apt-get install jq)"

[[ -n "${GHCR_TOKEN:-}"    ]] || die "GHCR_TOKEN is required (GitHub PAT with read:packages scope)"
[[ -n "${REDIS_PASSWORD:-}" ]] || die "REDIS_PASSWORD is required"

log "Environment  : ${ENVIRONMENT}"
log "Image tag    : ${IMAGE_TAG}"
log "Backend      : ${BACKEND_IMAGE}"
log "Frontend     : ${FRONTEND_IMAGE}"
log "App dir      : ${APP_DIR}"
log "Compose file : ${COMPOSE_FILE}"

# ── Step 1: Record current state (before touching anything) ───────────────────
log_section "Step 1: Record current state"
PREVIOUS_BACKEND_IMAGE=$(docker inspect "${BACKEND_CONTAINER}"   \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")
PREVIOUS_FRONTEND_IMAGE=$(docker inspect "${FRONTEND_CONTAINER}" \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")
export PREVIOUS_BACKEND_IMAGE PREVIOUS_FRONTEND_IMAGE
log "Previous backend  : ${PREVIOUS_BACKEND_IMAGE:-none (first deployment)}"
log "Previous frontend : ${PREVIOUS_FRONTEND_IMAGE:-none (first deployment)}"

# ── Step 2: Backup ────────────────────────────────────────────────────────────
log_section "Step 2: Backup"
if ! "${SCRIPTS_DIR}/backup.sh" "${ENVIRONMENT}"; then
  die "Backup failed — aborting deployment to preserve rollback capability. Fix backup before retrying."
fi
log "Backup completed successfully"

# ── Step 3: Pull new images ───────────────────────────────────────────────────
log_section "Step 3: Pull images"
echo "${GHCR_TOKEN}" | docker login ghcr.io \
  -u "${GHCR_USERNAME:-${GHCR_ORG}}" --password-stdin \
  || die "GHCR login failed. Check GHCR_TOKEN has read:packages scope."

docker pull "${BACKEND_IMAGE}"  || die "Failed to pull backend image: ${BACKEND_IMAGE}"
docker pull "${FRONTEND_IMAGE}" || die "Failed to pull frontend image: ${FRONTEND_IMAGE}"
log "Images pulled successfully"

# ── Step 4: Ensure Docker network exists (required for migration container) ───
log_section "Step 4: Ensure network"
NETWORK_NAME="${ENVIRONMENT/staging/hadha-staging}-internal"
NETWORK_NAME="${NETWORK_NAME/production/hadha-internal}"
# Simpler: just map explicitly
case "${ENVIRONMENT}" in
  production) NETWORK_NAME="hadha-internal" ;;
  staging)    NETWORK_NAME="hadha-staging-internal" ;;
esac
if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  log "Creating Docker network: ${NETWORK_NAME}"
  docker network create "${NETWORK_NAME}" \
    || log "[WARN] Network creation failed — will be created by compose"
else
  log "Network ${NETWORK_NAME} already exists"
fi

# ── Step 5: Database migrations ───────────────────────────────────────────────
log_section "Step 5: Database migrations"
log "Running: alembic upgrade head"

if ! docker run --rm \
  --env-file "${ENV_FILE}" \
  --network "${NETWORK_NAME}" \
  --name "hadha-migration-$$" \
  "${BACKEND_IMAGE}" \
  python -m alembic upgrade head; then
    log "[ERROR] Database migrations failed — aborting deployment"
    DEPLOY_END=$(date +%s)
    DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
    LAST_LOGS=$(tail -100 "${LOG_FILE}" 2>/dev/null || echo "")
    "${SCRIPTS_DIR}/notify.sh" failure \
      "${ENVIRONMENT}" "${IMAGE_TAG}" \
      "${GIT_COMMIT_SHA:-unknown}" "${GIT_COMMIT_AUTHOR:-unknown}" \
      "${DEPLOY_DURATION}" "Database migration failed" "${LAST_LOGS}" \
      2>/dev/null || true
    exit 1
fi
log "Migrations applied successfully"

# ── Step 6: Restart containers with new images ────────────────────────────────
log_section "Step 6: Restart containers"
export BACKEND_IMAGE FRONTEND_IMAGE REDIS_PASSWORD

if ! docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans --pull never; then
  log "[ERROR] Container restart failed"
  rollback_and_exit "docker compose up failed"
fi
log "Containers started — waiting for health checks..."

# ── Step 7: Health checks ─────────────────────────────────────────────────────
log_section "Step 7: Health checks"
if ! "${SCRIPTS_DIR}/healthcheck.sh" "${ENVIRONMENT}"; then
  log "[ERROR] Health checks failed after deployment"
  rollback_and_exit "Health checks failed after deployment"
fi

# ── Step 8: Cleanup old images (keep images newer than 7 days) ────────────────
log_section "Step 8: Cleanup"
docker image prune -f --filter "until=168h" 2>/dev/null || true

# ── Step 9: Success notification ──────────────────────────────────────────────
DEPLOY_END=$(date +%s)
DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
log_section "Deployment complete ✓"
log "Duration: ${DEPLOY_DURATION}s"

"${SCRIPTS_DIR}/notify.sh" success \
  "${ENVIRONMENT}" \
  "${IMAGE_TAG}" \
  "${GIT_COMMIT_SHA:-unknown}" \
  "${GIT_COMMIT_AUTHOR:-unknown}" \
  "${DEPLOY_DURATION}" \
  "" \
  "" \
  2>/dev/null || log "[WARN] Success notification failed — deployment itself succeeded"

exit 0
