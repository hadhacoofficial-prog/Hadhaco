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
  STEP_NAME=""
}

step_fail() {
  local reason="${1:-}"
  local elapsed=$(( $(date +%s) - STEP_START ))
  log "└─ ✗ FAILED: ${STEP_NAME} — ${elapsed}s — ${reason}"
}

# M-2 FIX: When die() is called inside an active step, log the step failure
# so the log shows a clean start→fail pair instead of a dangling start.
die() {
  [[ -n "${STEP_NAME}" ]] && step_fail "$*"
  log "[FATAL] $*"
  exit 1
}

# ── Deployment state machine ──────────────────────────────────────────────────
# These flags control whether rollback is warranted.
# Rollback must ONLY execute after containers have been modified (COMPOSE_UPDATED).
# Pull failures, manifest failures, and migration failures do NOT modify running
# containers — aborting in those states leaves the running system untouched.
#
# State progression:
#   PREFLIGHT → PULLING → MIGRATING → COMPOSING → COMPLETED
#
DEPLOYMENT_STATE="PREFLIGHT"
PULLED_IMAGES=false
MIGRATIONS_COMPLETED=false
COMPOSE_UPDATED=false
CONTAINERS_RESTARTED=false

# ── Failure classification ────────────────────────────────────────────────────
# Returns a short class string. Used in log output to guide operator recovery.
# Classes and suggested recovery:
#   AUTHENTICATION       — Check GHCR_TOKEN scope (needs read:packages)
#   MANIFEST_MISSING     — GHCR propagation delay; retry will resolve
#   NETWORK_EOF          — TCP drop mid-stream; transient, retry
#   TIMEOUT              — Registry slow; transient, retry
#   TLS_ERROR            — Certificate/TLS issue; check VPS time sync
#   REGISTRY_500         — GHCR backend error; transient, retry
#   REGISTRY_5XX         — GHCR overloaded; transient, retry
#   DOCKER_DAEMON        — Docker engine issue; check `systemctl status docker`
#   UNKNOWN              — Inspect raw log output
classify_failure() {
  local output="$1"
  if   echo "${output}" | grep -qi "unauthorized\|403\|authentication required"; then
    echo "AUTHENTICATION"
  elif echo "${output}" | grep -qi "manifest unknown\|not found\|404"; then
    echo "MANIFEST_MISSING"
  elif echo "${output}" | grep -qi " EOF\|connection reset\|broken pipe\|i/o timeout"; then
    echo "NETWORK_EOF"
  elif echo "${output}" | grep -qi "timeout\|timed out\|deadline exceeded\|context deadline"; then
    echo "TIMEOUT"
  elif echo "${output}" | grep -qi "TLS\|x509\|certificate\|ssl"; then
    echo "TLS_ERROR"
  elif echo "${output}" | grep -qi " 500 \|Internal Server Error"; then
    echo "REGISTRY_500"
  elif echo "${output}" | grep -qi " 502 \| 503 \| 504 \|Bad Gateway\|Service Unavailable\|Gateway Timeout"; then
    echo "REGISTRY_5XX"
  elif echo "${output}" | grep -qi "daemon\|dockerd\|no such"; then
    echo "DOCKER_DAEMON"
  else
    echo "UNKNOWN"
  fi
}

# ── Retry parameters ──────────────────────────────────────────────────────────
# 10 attempts maximum. Backoff: 5→10→20→30→60→60→60→60→60 (9 delays).
_MAX_RETRIES=10
_BACKOFFS=(5 10 20 30 60 60 60 60 60)

# ── pull_image_with_retry ─────────────────────────────────────────────────────
# Pull a Docker image with exponential backoff retry.
# Retries on: EOF, timeout, TLS errors, manifest unknown, HTTP 5xx.
# Classifies every failure in the log so operators can diagnose quickly.
# Returns 0 on success, 1 after all retries are exhausted.
pull_image_with_retry() {
  local image="$1"
  local attempt=0

  while (( attempt < _MAX_RETRIES )); do
    (( attempt++ ))
    log "  Pull attempt ${attempt}/${_MAX_RETRIES}: ${image}"

    local output exit_code
    set +e
    output=$(docker pull "${image}" 2>&1)
    exit_code=$?
    set -e

    if [[ ${exit_code} -eq 0 ]]; then
      log "  ✓ Pulled successfully: ${image}"
      echo "${output}" >> "${LOG_FILE}"
      return 0
    fi

    # Log the raw registry response (last 5 lines to avoid flooding the log)
    log "  Registry response: $(echo "${output}" | tail -5 | tr '\n' '|')"

    local failure_class
    failure_class=$(classify_failure "${output}")
    log "  Failure class  : ${failure_class}"
    log "  Retry reason   : ${failure_class} — $(
      case "${failure_class}" in
        AUTHENTICATION)  echo "token invalid or missing read:packages scope" ;;
        MANIFEST_MISSING) echo "GHCR propagation delay — image not yet on this CDN edge" ;;
        NETWORK_EOF)     echo "TCP connection dropped mid-stream (transient)" ;;
        TIMEOUT)         echo "registry slow to respond (transient)" ;;
        TLS_ERROR)       echo "TLS certificate or handshake failure — check VPS clock sync" ;;
        REGISTRY_500)    echo "GHCR internal error (transient)" ;;
        REGISTRY_5XX)    echo "GHCR overloaded or degraded (transient)" ;;
        DOCKER_DAEMON)   echo "Docker daemon issue — check: systemctl status docker" ;;
        *)               echo "unknown — inspect raw output above" ;;
      esac
    )"

    if (( attempt >= _MAX_RETRIES )); then
      log "  ✗ All ${_MAX_RETRIES} pull attempts failed for: ${image}"
      log "  Final failure class: ${failure_class}"
      log "  Recovery: see DEVOPS.md § 'Failure Classification'"
      return 1
    fi

    local delay="${_BACKOFFS[$((attempt - 1))]}"
    log "  Waiting ${delay}s before attempt $((attempt + 1))/${_MAX_RETRIES}..."
    sleep "${delay}"
  done
  return 1
}

# ── check_image_manifest ──────────────────────────────────────────────────────
# Verify a manifest is readable in GHCR without pulling the image.
# Uses docker manifest inspect which contacts the registry API directly.
# Returns 0 when the manifest is confirmed, 1 after all retries.
check_image_manifest() {
  local image="$1"
  local attempt=0

  log "  Checking manifest: ${image}"

  while (( attempt < _MAX_RETRIES )); do
    (( attempt++ ))
    log "  Manifest check attempt ${attempt}/${_MAX_RETRIES}"

    local output exit_code
    set +e
    output=$(docker manifest inspect "${image}" 2>&1)
    exit_code=$?
    set -e

    if [[ ${exit_code} -eq 0 ]]; then
      log "  ✓ Manifest confirmed: ${image}"
      return 0
    fi

    local failure_class
    failure_class=$(classify_failure "${output}")
    log "  Manifest not yet available — class: ${failure_class}"
    log "  Registry response: $(echo "${output}" | head -3 | tr '\n' '|')"

    if (( attempt >= _MAX_RETRIES )); then
      log "  ✗ Manifest unavailable after ${_MAX_RETRIES} attempts: ${image}"
      return 1
    fi

    local delay="${_BACKOFFS[$((attempt - 1))]}"
    log "  Waiting ${delay}s before attempt $((attempt + 1))/${_MAX_RETRIES}..."
    sleep "${delay}"
  done
  return 1
}

# ── verify_image_digest ───────────────────────────────────────────────────────
# After a successful pull, verify the local image has a registry digest and
# that the expected tag exists in image metadata.
# This catches silent pull truncations or tag resolution mismatches.
verify_image_digest() {
  local image="$1"
  log "  Verifying digest: ${image}"

  local inspect_output
  if ! inspect_output=$(docker image inspect "${image}" 2>&1); then
    log "  ✗ docker image inspect failed — image may not have been pulled"
    log "  Error: ${inspect_output}"
    return 1
  fi

  # Verify a registry digest exists (proves the image came from a registry,
  # not just a local build that was never pushed and never will match)
  local digest
  digest=$(echo "${inspect_output}" | jq -r '.[0].RepoDigests[0] // empty' 2>/dev/null || echo "")
  if [[ -z "${digest}" ]]; then
    log "  ✗ No RepoDigest found in image metadata"
    log "  This usually means the image was built locally and never pushed."
    return 1
  fi
  log "  Digest: ${digest}"

  # Verify the exact tag we requested appears in the image's RepoTags list.
  # A mismatch here means Docker resolved the tag to a different image than expected.
  local tags
  tags=$(echo "${inspect_output}" | jq -r '.[0].RepoTags // [] | .[]' 2>/dev/null || echo "")
  if ! echo "${tags}" | grep -qF "${image}"; then
    log "  ✗ Expected tag not found in image RepoTags"
    log "  Expected : ${image}"
    log "  Found    : ${tags:-none}"
    return 1
  fi

  log "  ✓ Digest verified: ${digest}"
  return 0
}

# ── Rollback + exit helper ────────────────────────────────────────────────────
# IMPORTANT: Rollback is only initiated if COMPOSE_UPDATED=true.
# Failures during PREFLIGHT or PULLING leave the running system completely
# unchanged — triggering a rollback in those states would restart already-
# healthy containers and create a misleading "rollback" notification.
FAILED_STEP=""
rollback_and_exit() {
  local reason="${1:-Unknown failure}"
  FAILED_STEP="${STEP_NAME}: ${reason}"
  step_fail "${reason}"
  log "[ERROR] Deployment failed at step : ${STEP_NAME}"
  log "[INFO]  Reason                    : ${reason}"
  log "[INFO]  Deployment state          : ${DEPLOYMENT_STATE}"
  log "[INFO]  PULLED_IMAGES             : ${PULLED_IMAGES}"
  log "[INFO]  MIGRATIONS_COMPLETED      : ${MIGRATIONS_COMPLETED}"
  log "[INFO]  COMPOSE_UPDATED           : ${COMPOSE_UPDATED}"
  log "[INFO]  CONTAINERS_RESTARTED      : ${CONTAINERS_RESTARTED}"

  local rollback_status="not attempted"

  if [[ "${COMPOSE_UPDATED}" != "true" ]]; then
    # Nothing was changed — do not touch the running system.
    rollback_status="skipped (no containers were modified — running system is unchanged)"
    log "[INFO] ${rollback_status}"
    log "[INFO] The running deployment is healthy and was not disturbed."
  else
    log "[INFO] Containers were modified (COMPOSE_UPDATED=true) — initiating automatic rollback..."

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
# STEP 4: Verify BOTH app image manifests are available before pulling anything
#
# WHY THIS STEP EXISTS:
#   GHCR uses an eventually consistent CDN. docker push returns 200 when the
#   origin accepts the manifest, but edge nodes serving the VPS region may not
#   have replicated it yet. Without this check, we could:
#     • Pull backend successfully (edge A has it)
#     • Fail to pull frontend (edge B hasn't replicated yet)
#     • Hit rollback_and_exit — but nothing was changed, wasting a rollback
#   This step verifies BOTH manifests are readable before touching anything.
#   If either manifest is missing, we abort with DEPLOYMENT_STATE=PREFLIGHT
#   so rollback_and_exit correctly skips the rollback.
#
# ATOMICITY:
#   We check both images before starting either pull. A partial deployment
#   (backend available, frontend not) is rejected before any image is pulled.
# =============================================================================
step_start "Verify app image manifests (pre-pull, atomic)"
log "Backend  : ${BACKEND_IMAGE}"
log "Frontend : ${FRONTEND_IMAGE}"
log "Verifying BOTH manifests before starting any pull..."

BACKEND_MANIFEST_OK=false
FRONTEND_MANIFEST_OK=false

if check_image_manifest "${BACKEND_IMAGE}"; then
  BACKEND_MANIFEST_OK=true
else
  log "[ERROR] Backend manifest not available: ${BACKEND_IMAGE}"
fi

if check_image_manifest "${FRONTEND_IMAGE}"; then
  FRONTEND_MANIFEST_OK=true
else
  log "[ERROR] Frontend manifest not available: ${FRONTEND_IMAGE}"
fi

# Require BOTH — refuse partial deployments
if [[ "${BACKEND_MANIFEST_OK}" != "true" ]] || [[ "${FRONTEND_MANIFEST_OK}" != "true" ]]; then
  log "[ERROR] One or both app image manifests are unavailable."
  log "[ERROR] Backend  manifest : ${BACKEND_MANIFEST_OK}"
  log "[ERROR] Frontend manifest : ${FRONTEND_MANIFEST_OK}"
  log "[INFO]  This is typically a GHCR propagation delay. The images were pushed"
  log "[INFO]  moments ago and the CDN edge serving this VPS has not replicated them."
  log "[INFO]  The verify-images job in GitHub Actions should have caught this."
  log "[INFO]  No containers were modified — rollback is not required."
  # DEPLOYMENT_STATE is still PREFLIGHT → rollback_and_exit will skip rollback
  rollback_and_exit "App image manifest(s) unavailable after retries — GHCR propagation failure"
fi

log "✓ Both app manifests confirmed — safe to begin pulling"
step_end

# =============================================================================
# STEP 5: Pull ALL images with retry
#
# Infrastructure images are pulled first. App images are pulled only after
# both manifests were confirmed in Step 4.
# DEPLOYMENT_STATE advances to PULLING — rollback still skipped on failure.
# =============================================================================
step_start "Pull all images"
DEPLOYMENT_STATE="PULLING"

log "── Infrastructure images ──"
for img in "${INFRA_IMAGES[@]}"; do
  if ! pull_image_with_retry "${img}"; then
    rollback_and_exit "Failed to pull infrastructure image after ${_MAX_RETRIES} attempts: ${img}"
  fi
done

log "── Application images ──"
if ! pull_image_with_retry "${BACKEND_IMAGE}"; then
  rollback_and_exit "Failed to pull backend image after ${_MAX_RETRIES} attempts: ${BACKEND_IMAGE}"
fi

if ! pull_image_with_retry "${FRONTEND_IMAGE}"; then
  rollback_and_exit "Failed to pull frontend image after ${_MAX_RETRIES} attempts: ${FRONTEND_IMAGE}"
fi

PULLED_IMAGES=true
step_end

# =============================================================================
# STEP 6: Verify image digests
#
# Confirm every pulled image has a registry digest and the expected tag.
# This catches rare silent-truncation scenarios where docker pull returns 0
# but the local image is incomplete, and tag resolution mismatches.
# =============================================================================
step_start "Verify image digests"

ALL_REQUIRED_IMAGES=(
  "${BACKEND_IMAGE}"
  "${FRONTEND_IMAGE}"
  "${INFRA_IMAGES[@]}"
)
DIGEST_FAILURES=()

for img in "${ALL_REQUIRED_IMAGES[@]}"; do
  if docker image inspect "${img}" >/dev/null 2>&1; then
    log "  ✓ present: ${img}"
    # Verify digest for app images (infra images may be local builds)
    if [[ "${img}" == ghcr.io/* ]]; then
      if ! verify_image_digest "${img}"; then
        DIGEST_FAILURES+=("${img}")
      fi
    fi
  else
    log "  ✗ MISSING: ${img}"
    DIGEST_FAILURES+=("${img}")
  fi
done

if [[ ${#DIGEST_FAILURES[@]} -gt 0 ]]; then
  rollback_and_exit "Image verification failed for: ${DIGEST_FAILURES[*]}"
fi
log "All images present and digests verified"
step_end

# =============================================================================
# STEP 7: Ensure Docker network exists
# =============================================================================
step_start "Ensure Docker network: ${NETWORK_NAME}"
if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  log "Network ${NETWORK_NAME} already exists — reusing"
else
  log "Creating Docker network: ${NETWORK_NAME}"
  # M-3 FIX: Removed --subnet to avoid "subnet already in use" failure when
  # production and staging networks are created on the same host.
  docker network create \
    --driver bridge \
    --ipv6 \
    "${NETWORK_NAME}" 2>&1 | tee -a "${LOG_FILE}" \
    || log "[WARN] Explicit network creation failed — compose will create it on startup"
fi
step_end

# =============================================================================
# STEP 8: Database migrations
#
# DEPLOYMENT_STATE advances to MIGRATING.
# A migration failure does NOT trigger rollback — containers are unchanged.
# The old backend continues running against the unchanged DB schema.
# =============================================================================
step_start "Database migrations (Supabase)"
DEPLOYMENT_STATE="MIGRATING"
log "Image   : ${BACKEND_IMAGE}"
log "Command : alembic -c alembic/alembic.ini upgrade head"

if grep -q '^ALEMBIC_DATABASE_URL=' "${ENV_FILE}" 2>/dev/null; then
  log "Pool routing : ALEMBIC_DATABASE_URL → Transaction Pooler (port 6543) ✓"
else
  log "[WARN] ALEMBIC_DATABASE_URL not set — falling back to DATABASE_URL (Session Pooler)"
  log "[WARN] Add ALEMBIC_DATABASE_URL pointing to port 6543 to prevent EMAXCONNSESSION."
fi

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
  # Containers were NOT modified yet — rollback_and_exit will skip rollback.
  rollback_and_exit "Database migration failed — alembic upgrade head returned non-zero. Check logs above."
fi
MIGRATIONS_COMPLETED=true
step_end

# =============================================================================
# STEP 9: Start containers
#
# DEPLOYMENT_STATE advances to COMPOSING immediately before compose up.
# Any failure from this point onward triggers a real rollback.
# --pull never: images were explicitly pulled and verified in steps 5-6.
# =============================================================================
step_start "Start containers"
DEPLOYMENT_STATE="COMPOSING"
COMPOSE_UPDATED=true   # Mark BEFORE compose up — any failure now warrants rollback

if ! dc up -d --remove-orphans --pull never 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "docker compose up failed"
fi
CONTAINERS_RESTARTED=true
log "Containers started — waiting for health checks..."
step_end

# =============================================================================
# STEP 10: Health checks
# =============================================================================
step_start "Health checks"
if ! "${SCRIPTS_DIR}/healthcheck.sh" "${ENVIRONMENT}" 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "Health checks failed after deployment"
fi
step_end

# =============================================================================
# STEP 11: Record deployed images to disk
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
DEPLOYMENT_STATE="COMPLETED"
step_end

# =============================================================================
# STEP 12: Cleanup old application images
# Only removes images from our GHCR org. Never touches infra images.
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
