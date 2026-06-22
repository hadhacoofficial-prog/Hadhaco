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
# NOT set -e: failures are handled explicitly with rollback rather than
# causing an immediate uncontrolled exit.

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
    NETWORK_NAME="hadha-internal"
    MIGRATION_CONTAINER="hadha-migration"
    ;;
  staging)
    APP_DIR="/opt/hadha-staging"
    COMPOSE_FILE="${APP_DIR}/docker-compose.staging.yml"
    ENV_FILE="${APP_DIR}/.env.staging"
    BACKEND_CONTAINER="hadha-staging-backend"
    FRONTEND_CONTAINER="hadha-staging-frontend"
    APP_URL="https://staging.hadha.co"
    NETWORK_NAME="hadha-staging-internal"
    MIGRATION_CONTAINER="hadha-staging-migration"
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
PREVIOUS_IMAGES_FILE="${APP_DIR}/.previous_images"
IMAGE_RETENTION="${IMAGE_RETENTION:-168h}"  # 7 days; override via env

# Infrastructure images that must be present before compose up.
# These are pulled explicitly so no service ever fails with "No such image".
INFRA_IMAGES=(
  "redis:7-alpine"
  "rediscommander/redis-commander:latest"
  "amir20/dozzle:v8"
  "nginx:stable-alpine"
)

# ── Compose wrapper ───────────────────────────────────────────────────────────
# Every docker compose invocation goes through dc() to guarantee --env-file
# and -f are always present. Never call docker compose directly in this script.
dc() {
  docker compose \
    --env-file "${ENV_FILE}" \
    -f "${COMPOSE_FILE}" \
    "$@"
}

# ── Logging ───────────────────────────────────────────────────────────────────
log()         { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }
log_section() { log ""; log "══════════════════════════════════════════"; log "  $*"; log "══════════════════════════════════════════"; }
die()         { log "[FATAL] $*"; exit 1; }

STEP_NAME=""
STEP_START=0

step_start() {
  STEP_NAME="$1"
  STEP_START=$(date +%s)
  log ""
  log "┌─ START: ${STEP_NAME} [$(date +'%H:%M:%S')]"
}

step_end() {
  local elapsed=$(( $(date +%s) - STEP_START ))
  log "└─ ✓ DONE: ${STEP_NAME} — ${elapsed}s [$(date +'%H:%M:%S')]"
}

step_fail() {
  local reason="${1:-}"
  local elapsed=$(( $(date +%s) - STEP_START ))
  log "└─ ✗ FAILED: ${STEP_NAME} — ${elapsed}s — ${reason}"
}

# ── Rollback + exit helper ────────────────────────────────────────────────────
# Must be defined before any step that can fail.
FAILED_STEP=""
rollback_and_exit() {
  local reason="${1:-Unknown failure}"
  FAILED_STEP="${STEP_NAME}: ${reason}"
  step_fail "${reason}"
  log "[ERROR] Deployment failed at step: ${STEP_NAME}"
  log "[INFO]  Reason: ${reason}"
  log "[INFO]  Initiating automatic rollback..."

  local rollback_status="not attempted"

  if [[ -n "${PREVIOUS_BACKEND_IMAGE:-}" ]] && [[ -n "${PREVIOUS_FRONTEND_IMAGE:-}" ]]; then
    if "${SCRIPTS_DIR}/rollback.sh" \
        "${ENVIRONMENT}" \
        "${PREVIOUS_BACKEND_IMAGE}" \
        "${PREVIOUS_FRONTEND_IMAGE}" 2>&1 | tee -a "${LOG_FILE}"; then
      rollback_status="succeeded"
      log "[INFO] Rollback succeeded"
    else
      rollback_status="FAILED — manual intervention required"
      log "[FATAL] Rollback failed — manual intervention required"
    fi
  else
    rollback_status="skipped (no previous images recorded)"
    log "[WARN] No previous images available — cannot auto-rollback (first deployment?)"
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
    "${FAILED_STEP}" \
    "${rollback_status}" \
    "${LAST_LOGS}" \
    2>/dev/null || log "[WARN] Failure notification could not be sent"

  exit 1
}

# =============================================================================
# PRE-FLIGHT
# =============================================================================
log_section "Pre-flight checks"

[[ -d "${APP_DIR}" ]]      || die "Deploy directory ${APP_DIR} does not exist. Run bootstrap.sh first."
[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
[[ -f "${ENV_FILE}" ]]     || die "Env file not found: ${ENV_FILE}"
command -v docker >/dev/null 2>&1 || die "docker is not installed"
command -v curl   >/dev/null 2>&1 || die "curl is not installed"
command -v jq     >/dev/null 2>&1 || die "jq is not installed (install: apt-get install jq)"

[[ -n "${GHCR_TOKEN:-}"     ]] || die "GHCR_TOKEN is required (GitHub PAT with read:packages scope)"
[[ -n "${REDIS_PASSWORD:-}" ]] || die "REDIS_PASSWORD is required"

log "Environment  : ${ENVIRONMENT}"
log "Image tag    : ${IMAGE_TAG}"
log "Backend      : ${BACKEND_IMAGE}"
log "Frontend     : ${FRONTEND_IMAGE}"
log "App dir      : ${APP_DIR}"
log "Compose file : ${COMPOSE_FILE}"
log "Env file     : ${ENV_FILE}"

# =============================================================================
# STEP 0: Validate compose config
# Must run before anything else — catches missing variables and syntax errors.
# =============================================================================
step_start "Validate compose configuration"

# Export variables that compose interpolates so validation can succeed
export BACKEND_IMAGE FRONTEND_IMAGE REDIS_PASSWORD

COMPOSE_VALIDATE_OUTPUT=$(dc config 2>&1) || {
  step_fail "docker compose config returned non-zero"
  log "[ERROR] Compose validation output:"
  log "${COMPOSE_VALIDATE_OUTPUT}"

  DEPLOY_END=$(date +%s)
  DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
  "${SCRIPTS_DIR}/notify.sh" failure \
    "${ENVIRONMENT}" "${IMAGE_TAG}" \
    "${GIT_COMMIT_SHA:-unknown}" "${GIT_COMMIT_AUTHOR:-unknown}" \
    "${DEPLOY_DURATION}" \
    "Compose config validation failed — check BACKEND_IMAGE, FRONTEND_IMAGE, REDIS_PASSWORD, and compose syntax" \
    "not attempted" \
    "${COMPOSE_VALIDATE_OUTPUT}" \
    2>/dev/null || true
  exit 1
}
log "Compose configuration is valid"
step_end

# =============================================================================
# STEP 1: Record current state (before touching anything)
# =============================================================================
step_start "Record current state"

PREVIOUS_BACKEND_IMAGE=$(docker inspect "${BACKEND_CONTAINER}" \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")
PREVIOUS_FRONTEND_IMAGE=$(docker inspect "${FRONTEND_CONTAINER}" \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")

# Fallback: read from disk if containers aren't running (e.g., after reboot)
if [[ -z "${PREVIOUS_BACKEND_IMAGE}" ]] && [[ -f "${PREVIOUS_IMAGES_FILE}" ]]; then
  PREVIOUS_BACKEND_IMAGE=$(jq -r '.backend_image // empty' "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
  PREVIOUS_FRONTEND_IMAGE=$(jq -r '.frontend_image // empty' "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
  [[ -n "${PREVIOUS_BACKEND_IMAGE}" ]] && log "Previous images loaded from disk (containers not running)"
fi

export PREVIOUS_BACKEND_IMAGE PREVIOUS_FRONTEND_IMAGE
log "Previous backend  : ${PREVIOUS_BACKEND_IMAGE:-none (first deployment)}"
log "Previous frontend : ${PREVIOUS_FRONTEND_IMAGE:-none (first deployment)}"
step_end

# =============================================================================
# STEP 2: Backup current state
# Backup must succeed before we change anything. A failed backup aborts
# the deployment to preserve rollback capability.
# =============================================================================
step_start "Backup"
if ! "${SCRIPTS_DIR}/backup.sh" "${ENVIRONMENT}" 2>&1 | tee -a "${LOG_FILE}"; then
  die "Backup failed — aborting deployment to preserve rollback capability. Fix backup and retry."
fi
step_end

# =============================================================================
# STEP 3: GHCR authentication
# =============================================================================
step_start "GHCR authentication"
if ! echo "${GHCR_TOKEN}" | docker login ghcr.io \
    -u "${GHCR_USERNAME:-${GHCR_ORG}}" --password-stdin 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "GHCR login failed. Verify GHCR_TOKEN has read:packages scope."
fi
step_end

# =============================================================================
# STEP 4: Pull ALL images
# Infrastructure images are pulled explicitly so no service ever fails with
# "No such image" on a fresh VPS or after docker system prune.
# =============================================================================
step_start "Pull all images"

log "── Infrastructure images ──"
for img in "${INFRA_IMAGES[@]}"; do
  log "Pulling: ${img}"
  if ! docker pull "${img}" 2>&1 | tee -a "${LOG_FILE}"; then
    rollback_and_exit "Failed to pull infrastructure image: ${img}"
  fi
done

log "── Application images ──"
log "Pulling backend: ${BACKEND_IMAGE}"
if ! docker pull "${BACKEND_IMAGE}" 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "Failed to pull backend image: ${BACKEND_IMAGE}"
fi

log "Pulling frontend: ${FRONTEND_IMAGE}"
if ! docker pull "${FRONTEND_IMAGE}" 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "Failed to pull frontend image: ${FRONTEND_IMAGE}"
fi

step_end

# =============================================================================
# STEP 5: Verify all required images exist locally
# Fail-fast before attempting compose up to give a clear error message.
# =============================================================================
step_start "Verify images exist locally"

ALL_REQUIRED_IMAGES=(
  "${BACKEND_IMAGE}"
  "${FRONTEND_IMAGE}"
  "${INFRA_IMAGES[@]}"
)
MISSING_IMAGES=()
for img in "${ALL_REQUIRED_IMAGES[@]}"; do
  if docker image inspect "${img}" >/dev/null 2>&1; then
    log "  ✓ ${img}"
  else
    log "  ✗ MISSING: ${img}"
    MISSING_IMAGES+=("${img}")
  fi
done

if [[ ${#MISSING_IMAGES[@]} -gt 0 ]]; then
  rollback_and_exit "Required images missing after pull: ${MISSING_IMAGES[*]}"
fi
step_end

# =============================================================================
# STEP 6: Ensure Docker network exists
# We create the network explicitly so it exists before the migration container
# (which runs outside of compose) needs it. compose up will reuse it because
# the network is declared as external in the compose file.
# Never delete production networks — only create if missing.
# =============================================================================
step_start "Ensure Docker network: ${NETWORK_NAME}"
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  log "Network ${NETWORK_NAME} already exists — reusing"
else
  log "Creating Docker network: ${NETWORK_NAME}"
  docker network create \
    --driver bridge \
    --subnet "172.28.0.0/16" \
    "${NETWORK_NAME}" 2>&1 | tee -a "${LOG_FILE}" \
    || log "[WARN] Explicit network creation failed — compose will create it on startup"
fi
step_end

# =============================================================================
# STEP 7: Database migrations
# Uses a deterministic container name so stale containers from failed runs
# are cleaned up before starting a new migration.
# =============================================================================
step_start "Database migrations (Supabase)"
log "Image   : ${BACKEND_IMAGE}"
log "Command : alembic -c alembic/alembic.ini upgrade head"

# Remove any stale migration container from a previous failed run
if docker inspect "${MIGRATION_CONTAINER}" >/dev/null 2>&1; then
  log "Removing stale migration container: ${MIGRATION_CONTAINER}"
  docker rm -f "${MIGRATION_CONTAINER}" >/dev/null 2>&1 || true
fi

if ! docker run \
    --rm \
    --name "${MIGRATION_CONTAINER}" \
    --env-file "${ENV_FILE}" \
    --network "${NETWORK_NAME}" \
    "${BACKEND_IMAGE}" \
    alembic -c alembic/alembic.ini upgrade head 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "Database migration failed — alembic upgrade head returned non-zero. Check logs above."
fi
step_end

# =============================================================================
# STEP 8: Start containers
# --pull never: images were explicitly pulled in step 4 and verified in step 5.
# --remove-orphans: cleans up containers from services removed from compose file.
# =============================================================================
step_start "Start containers"
if ! dc up -d --remove-orphans --pull never 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "docker compose up failed"
fi
log "Containers started — waiting for health checks..."
step_end

# =============================================================================
# STEP 9: Health checks
# =============================================================================
step_start "Health checks"
if ! "${SCRIPTS_DIR}/healthcheck.sh" "${ENVIRONMENT}" 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "Health checks failed after deployment"
fi
step_end

# =============================================================================
# STEP 10: Record deployed images to disk
# Written after successful health checks so rollback.sh always has
# a valid previous state to restore from, even across reboots.
# =============================================================================
step_start "Record deployed images"
cat > "${PREVIOUS_IMAGES_FILE}" <<EOF
{
  "backend_image":  "${BACKEND_IMAGE}",
  "frontend_image": "${FRONTEND_IMAGE}",
  "deployed_at":    "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "image_tag":      "${IMAGE_TAG}",
  "git_sha":        "${GIT_COMMIT_SHA:-unknown}",
  "git_author":     "${GIT_COMMIT_AUTHOR:-unknown}"
}
EOF
log "Deployed image state written to ${PREVIOUS_IMAGES_FILE}"
step_end

# =============================================================================
# STEP 11: Cleanup old application images
# Only removes images from our GHCR org that are no longer the current or
# previous deployment. Never touches infrastructure images (redis, nginx, etc.)
# Never runs docker system prune or docker image prune -a.
# =============================================================================
step_start "Cleanup old application images"
GHCR_PREFIX="ghcr.io/${GHCR_ORG}/"
log "Pruning unused ${GHCR_PREFIX}* images (keeping current and previous)"

KEEP_IMAGES=(
  "${BACKEND_IMAGE}"
  "${FRONTEND_IMAGE}"
  "${PREVIOUS_BACKEND_IMAGE:-}"
  "${PREVIOUS_FRONTEND_IMAGE:-}"
)

docker images --format "{{.Repository}}:{{.Tag}}\t{{.ID}}" \
  | grep "^${GHCR_PREFIX}" \
  | while IFS=$'\t' read -r full_name img_id; do
      local_keep=false
      for keep in "${KEEP_IMAGES[@]}"; do
        [[ -z "${keep}" ]] && continue
        [[ "${full_name}" == "${keep}" ]] && { local_keep=true; break; }
      done
      if [[ "${local_keep}" == "true" ]]; then
        log "  keeping : ${full_name}"
      else
        log "  removing: ${full_name} (${img_id})"
        docker rmi "${img_id}" 2>/dev/null || log "  [WARN] Could not remove ${img_id} (may be in use)"
      fi
    done
step_end

# =============================================================================
# COMPLETE
# =============================================================================
DEPLOY_END=$(date +%s)
DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
log_section "Deployment complete ✓ — ${DEPLOY_DURATION}s"

"${SCRIPTS_DIR}/notify.sh" success \
  "${ENVIRONMENT}" \
  "${IMAGE_TAG}" \
  "${GIT_COMMIT_SHA:-unknown}" \
  "${GIT_COMMIT_AUTHOR:-unknown}" \
  "${DEPLOY_DURATION}" \
  "" "" "" \
  2>/dev/null || log "[WARN] Success notification failed — deployment itself succeeded"

exit 0
