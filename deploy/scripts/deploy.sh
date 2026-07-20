#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Hadha.co Production Deployment Script
#
# Usage:
#   ./deploy.sh <image_tag>
#   ./deploy.sh sha-abc1234
#
# Required environment variables (exported by caller / CI):
#   GHCR_TOKEN          — GitHub PAT with read:packages scope
#   GHCR_USERNAME       — GitHub org: hadhacoofficial-prog
#   REDIS_PASSWORD      — Redis authentication password
#   REDIS_UI_USERNAME   — Redis Commander HTTP Basic Auth username
#   REDIS_UI_PASSWORD   — Redis Commander HTTP Basic Auth password
#   DOZZLE_USERNAME     — Dozzle monitoring dashboard username
#   DOZZLE_PASSWORD     — Dozzle monitoring dashboard password (plain; hashed here)
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
IMAGE_TAG="${1:?Usage: $0 <image_tag>}"
DEPLOY_START=$(date +%s)

# ── Production config ─────────────────────────────────────────────────────────
ENVIRONMENT="production"
APP_DIR="/opt/hadha"
COMPOSE_FILE="${APP_DIR}/docker-compose.production.yml"
ENV_FILE="${APP_DIR}/.env.production"
BACKEND_CONTAINER="hadha-backend"
STOREFRONT_CONTAINER="hadha-storefront"
ADMIN_CONTAINER="hadha-admin"
APP_URL="https://hadha.co"
NETWORK_NAME="hadha-internal"
MIGRATION_CONTAINER="hadha-migration"

GHCR_ORG="hadhacoofficial-prog"
BACKEND_IMAGE="ghcr.io/${GHCR_ORG}/hadha-backend:${IMAGE_TAG}"
STOREFRONT_IMAGE="ghcr.io/${GHCR_ORG}/hadha-storefront:${IMAGE_TAG}"
ADMIN_IMAGE="ghcr.io/${GHCR_ORG}/hadha-admin:${IMAGE_TAG}"
BACKUP_DIR="${APP_DIR}/backups"
SCRIPTS_DIR="${APP_DIR}/scripts"
LOG_FILE="${APP_DIR}/deploy.log"
PREVIOUS_IMAGES_FILE="${APP_DIR}/.previous_images"
IMAGE_RETENTION="${IMAGE_RETENTION:-168h}"  # 7 days; override via env

# Infrastructure images that must be present before compose up.
INFRA_IMAGES=(
  "redis:7-alpine"
  "rediscommander/redis-commander:latest"
  "oliver006/redis_exporter:v1.61.0"
  "amir20/dozzle:v8"
  "nginx:stable-alpine"
  "prom/prometheus:v2.53.0"
  "grafana/grafana:11.1.0"
  "grafana/loki:3.1.0"
  "grafana/promtail:3.1.0"
  "prom/node-exporter:v1.8.1"
  "gcr.io/cadvisor/cadvisor:v0.49.1"
  "louislam/uptime-kuma:2.0.2"
  "glitchtip/glitchtip:6.2.2"
  "postgres:16-alpine"
)

# ── Compose wrapper ───────────────────────────────────────────────────────────
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

die() {
  [[ -n "${STEP_NAME}" ]] && step_fail "$*"
  log "[FATAL] $*"
  exit 1
}

# ── Deployment state machine ──────────────────────────────────────────────────
DEPLOYMENT_STATE="PREFLIGHT"
PULLED_IMAGES=false
MIGRATIONS_COMPLETED=false
COMPOSE_UPDATED=false
CONTAINERS_RESTARTED=false

# ── Failure classification ────────────────────────────────────────────────────
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
_MAX_RETRIES=10
_BACKOFFS=(5 10 20 30 60 60 60 60 60)

# ── pull_image_with_retry ─────────────────────────────────────────────────────
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
verify_image_digest() {
  local image="$1"
  log "  Verifying digest: ${image}"

  local inspect_output
  if ! inspect_output=$(docker image inspect "${image}" 2>&1); then
    log "  ✗ docker image inspect failed — image may not have been pulled"
    log "  Error: ${inspect_output}"
    return 1
  fi

  local digest
  digest=$(echo "${inspect_output}" | jq -r '.[0].RepoDigests[0] // empty' 2>/dev/null || echo "")
  if [[ -z "${digest}" ]]; then
    log "  ✗ No RepoDigest found in image metadata"
    return 1
  fi
  log "  Digest: ${digest}"

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
    rollback_status="skipped (no containers were modified — running system is unchanged)"
    log "[INFO] ${rollback_status}"
    log "[INFO] The running deployment is healthy and was not disturbed."
  else
    log "[INFO] Containers were modified (COMPOSE_UPDATED=true) — initiating automatic rollback..."

    if [[ -n "${PREVIOUS_BACKEND_IMAGE:-}" ]] && \
       [[ -n "${PREVIOUS_STOREFRONT_IMAGE:-}" ]] && \
       [[ -n "${PREVIOUS_ADMIN_IMAGE:-}" ]]; then
      if "${SCRIPTS_DIR}/rollback.sh" \
          "${PREVIOUS_BACKEND_IMAGE}" \
          "${PREVIOUS_STOREFRONT_IMAGE}" \
          "${PREVIOUS_ADMIN_IMAGE}" 2>&1 | tee -a "${LOG_FILE}"; then
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

# Docker Compose requires env_file paths to exist even if empty.
# Create placeholder files for storefront/admin if they haven't been provisioned yet.
for _svc_env in "${APP_DIR}/.env.storefront.production" "${APP_DIR}/.env.admin.production"; do
  [[ -f "${_svc_env}" ]] || { touch "${_svc_env}"; log "Created placeholder: ${_svc_env}"; }
done
unset _svc_env
command -v docker >/dev/null 2>&1 || die "docker is not installed"
command -v curl   >/dev/null 2>&1 || die "curl is not installed"
command -v jq     >/dev/null 2>&1 || die "jq is not installed (install: apt-get install jq)"

[[ -n "${GHCR_TOKEN:-}"         ]] || die "GHCR_TOKEN is required (GitHub PAT with read:packages scope)"
[[ -n "${REDIS_PASSWORD:-}"     ]] || die "REDIS_PASSWORD is required"
[[ -n "${REDIS_UI_USERNAME:-}"  ]] || die "REDIS_UI_USERNAME is required (Redis Commander auth)"
[[ -n "${REDIS_UI_PASSWORD:-}"  ]] || die "REDIS_UI_PASSWORD is required (Redis Commander auth)"
[[ -n "${DOZZLE_USERNAME:-}"    ]] || die "DOZZLE_USERNAME is required (Dozzle auth)"
[[ -n "${DOZZLE_PASSWORD:-}"    ]] || die "DOZZLE_PASSWORD is required (Dozzle auth)"
[[ -n "${GRAFANA_USERNAME:-}"   ]] || die "GRAFANA_USERNAME is required (Grafana auth)"
[[ -n "${GRAFANA_PASSWORD:-}"   ]] || die "GRAFANA_PASSWORD is required (Grafana auth)"
[[ -n "${GLITCHTIP_DB_PASSWORD:-}" ]] || die "GLITCHTIP_DB_PASSWORD is required (GlitchTip PostgreSQL)"
[[ -n "${GLITCHTIP_SECRET_KEY:-}"  ]] || die "GLITCHTIP_SECRET_KEY is required (GlitchTip session signing)"

log "Image tag    : ${IMAGE_TAG}"
log "Backend      : ${BACKEND_IMAGE}"
log "Storefront   : ${STOREFRONT_IMAGE}"
log "Admin        : ${ADMIN_IMAGE}"
log "App dir      : ${APP_DIR}"
log "Compose file : ${COMPOSE_FILE}"
log "Env file     : ${ENV_FILE}"

# =============================================================================
# STEP 0: Validate compose config
# =============================================================================
step_start "Validate compose configuration"

export BACKEND_IMAGE STOREFRONT_IMAGE ADMIN_IMAGE REDIS_PASSWORD \
       REDIS_UI_USERNAME REDIS_UI_PASSWORD \
       DOZZLE_USERNAME DOZZLE_PASSWORD \
       GRAFANA_USERNAME GRAFANA_PASSWORD \
       GLITCHTIP_DB_PASSWORD GLITCHTIP_SECRET_KEY \
       GLITCHTIP_DSN GLITCHTIP_FRONTEND_DSN

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
    "Compose config validation failed — check BACKEND_IMAGE, STOREFRONT_IMAGE, ADMIN_IMAGE, REDIS_PASSWORD, and compose syntax" \
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
PREVIOUS_STOREFRONT_IMAGE=$(docker inspect "${STOREFRONT_CONTAINER}" \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")
PREVIOUS_ADMIN_IMAGE=$(docker inspect "${ADMIN_CONTAINER}" \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")

if [[ -z "${PREVIOUS_BACKEND_IMAGE}" ]] && [[ -f "${PREVIOUS_IMAGES_FILE}" ]]; then
  PREVIOUS_BACKEND_IMAGE=$(jq -r '.backend_image // empty' "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
  PREVIOUS_STOREFRONT_IMAGE=$(jq -r '.storefront_image // empty' "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
  PREVIOUS_ADMIN_IMAGE=$(jq -r '.admin_image // empty' "${PREVIOUS_IMAGES_FILE}" 2>/dev/null || echo "")
  [[ -n "${PREVIOUS_BACKEND_IMAGE}" ]] && log "Previous images loaded from disk (containers not running)"
fi

export PREVIOUS_BACKEND_IMAGE PREVIOUS_STOREFRONT_IMAGE PREVIOUS_ADMIN_IMAGE
log "Previous backend    : ${PREVIOUS_BACKEND_IMAGE:-none (first deployment)}"
log "Previous storefront : ${PREVIOUS_STOREFRONT_IMAGE:-none (first deployment)}"
log "Previous admin      : ${PREVIOUS_ADMIN_IMAGE:-none (first deployment)}"
step_end

# =============================================================================
# STEP 2: Backup current state
# =============================================================================
step_start "Backup"
if ! "${SCRIPTS_DIR}/backup.sh" 2>&1 | tee -a "${LOG_FILE}"; then
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
# STEP 4: Verify ALL app image manifests before pulling anything
# =============================================================================
step_start "Verify app image manifests (pre-pull, atomic)"
log "Backend    : ${BACKEND_IMAGE}"
log "Storefront : ${STOREFRONT_IMAGE}"
log "Admin      : ${ADMIN_IMAGE}"
log "Verifying ALL manifests before starting any pull..."

BACKEND_MANIFEST_OK=false
STOREFRONT_MANIFEST_OK=false
ADMIN_MANIFEST_OK=false

check_image_manifest "${BACKEND_IMAGE}"    && BACKEND_MANIFEST_OK=true    || log "[ERROR] Backend manifest not available"
check_image_manifest "${STOREFRONT_IMAGE}" && STOREFRONT_MANIFEST_OK=true || log "[ERROR] Storefront manifest not available"
check_image_manifest "${ADMIN_IMAGE}"      && ADMIN_MANIFEST_OK=true      || log "[ERROR] Admin manifest not available"

if [[ "${BACKEND_MANIFEST_OK}" != "true" ]] || \
   [[ "${STOREFRONT_MANIFEST_OK}" != "true" ]] || \
   [[ "${ADMIN_MANIFEST_OK}" != "true" ]]; then
  log "[ERROR] One or more app image manifests are unavailable."
  log "[ERROR] Backend    manifest : ${BACKEND_MANIFEST_OK}"
  log "[ERROR] Storefront manifest : ${STOREFRONT_MANIFEST_OK}"
  log "[ERROR] Admin      manifest : ${ADMIN_MANIFEST_OK}"
  log "[INFO]  This is typically a GHCR propagation delay. Re-run the workflow."
  log "[INFO]  No containers were modified — rollback is not required."
  rollback_and_exit "App image manifest(s) unavailable after retries — GHCR propagation failure"
fi

log "✓ All app manifests confirmed — safe to begin pulling"
step_end

# =============================================================================
# STEP 5: Pull ALL images with retry
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

if ! pull_image_with_retry "${STOREFRONT_IMAGE}"; then
  rollback_and_exit "Failed to pull storefront image after ${_MAX_RETRIES} attempts: ${STOREFRONT_IMAGE}"
fi

if ! pull_image_with_retry "${ADMIN_IMAGE}"; then
  rollback_and_exit "Failed to pull admin image after ${_MAX_RETRIES} attempts: ${ADMIN_IMAGE}"
fi

PULLED_IMAGES=true
step_end

# =============================================================================
# STEP 6: Verify image digests
# =============================================================================
step_start "Verify image digests"

ALL_REQUIRED_IMAGES=(
  "${BACKEND_IMAGE}"
  "${STOREFRONT_IMAGE}"
  "${ADMIN_IMAGE}"
  "${INFRA_IMAGES[@]}"
)
DIGEST_FAILURES=()

for img in "${ALL_REQUIRED_IMAGES[@]}"; do
  if docker image inspect "${img}" >/dev/null 2>&1; then
    log "  ✓ present: ${img}"
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
  docker network create \
    --driver bridge \
    --ipv6 \
    "${NETWORK_NAME}" 2>&1 | tee -a "${LOG_FILE}" \
    || log "[WARN] Explicit network creation failed — compose will create it on startup"
fi
step_end

# =============================================================================
# STEP 7.5: Generate Dozzle authentication file
# =============================================================================
step_start "Generate Dozzle authentication file"

DOZZLE_DIR="${APP_DIR}/dozzle"
mkdir -p "${DOZZLE_DIR}"

# Safety: remove stale directory at file path (can happen from failed deploys)
if [[ -d "${DOZZLE_DIR}/users.yml" ]]; then
  rm -rf "${DOZZLE_DIR}/users.yml"
  log "Removed stale directory at ${DOZZLE_DIR}/users.yml"
fi

if ! command -v htpasswd >/dev/null 2>&1; then
  die "htpasswd not found — run: apt-get install -y apache2-utils"
fi

DOZZLE_HASH=$(htpasswd -nbB "${DOZZLE_USERNAME}" "${DOZZLE_PASSWORD}" 2>/dev/null | cut -d: -f2) \
  || die "Failed to generate bcrypt hash for Dozzle password"

cat > "${DOZZLE_DIR}/users.yml" <<DOZZLE_USERS_EOF
users:
  ${DOZZLE_USERNAME}:
    name: ${DOZZLE_USERNAME}
    email: admin@hadha.co
    password: "${DOZZLE_HASH}"
DOZZLE_USERS_EOF

chmod 600 "${DOZZLE_DIR}/users.yml"
log "Dozzle auth file written to ${DOZZLE_DIR}/users.yml (password bcrypt-hashed)"
step_end

# =============================================================================
# STEP 8: Database migrations
# =============================================================================
step_start "Database migrations (Supabase)"
DEPLOYMENT_STATE="MIGRATING"
log "Image   : ${BACKEND_IMAGE}"
log "Command : alembic -c alembic/alembic.ini upgrade head"

if grep -q '^ALEMBIC_DATABASE_URL=' "${ENV_FILE}" 2>/dev/null; then
  log "Pool routing : ALEMBIC_DATABASE_URL → Transaction Pooler (port 6543) ✓"
else
  log "[WARN] ALEMBIC_DATABASE_URL not set — falling back to DATABASE_URL (Session Pooler)"
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
  rollback_and_exit "Database migration failed — alembic upgrade head returned non-zero. Check logs above."
fi
MIGRATIONS_COMPLETED=true
step_end

# =============================================================================
# STEP 8.5: Ensure file-mount paths are files, not directories
# =============================================================================
step_start "Verify file-mount paths"

# If a host path that should be a file is a directory (from failed deploys),
# Docker will fail with "not a directory" on bind-mount.  Remove stale dirs.
FILE_MOUNT_PATHS=(
  "${APP_DIR}/dozzle/users.yml"
  "${APP_DIR}/nginx/nginx.conf"
  "${APP_DIR}/monitoring/prometheus/prometheus.yml"
  "${APP_DIR}/monitoring/loki/loki-config.yml"
  "${APP_DIR}/monitoring/promtail/promtail-config.yml"
)

CLEANED=0
for fpath in "${FILE_MOUNT_PATHS[@]}"; do
  if [[ -d "${fpath}" ]]; then
    if rm -rf "${fpath}" 2>/dev/null; then
      log "  [FIX] ${fpath} was a directory — removed"
      CLEANED=$((CLEANED + 1))
    else
      log "  [WARN] ${fpath} is a directory but cannot remove (permission) — container may fail"
    fi
  fi
done

if [[ ${CLEANED} -gt 0 ]]; then
  log "Cleaned ${CLEANED} stale directory mount(s)"
else
  log "All file-mount paths are correct"
fi

# Fallback: restore any missing or non-file monitoring configs from CI source
# (which is still at /tmp/hadha-deploy — CI cleans it after this step)
RESTORED=0
for fpath in "${FILE_MOUNT_PATHS[@]}"; do
  if [[ ! -f "${fpath}" ]]; then
    # Derive CI source path: /opt/hadha/... → /tmp/hadha-deploy/...
    src_path="/tmp/hadha-deploy/${fpath#${APP_DIR}/}"
    if [[ -f "${src_path}" ]]; then
      rm -rf "${fpath}" 2>/dev/null
      mkdir -p "$(dirname "${fpath}")"
      cp -f "${src_path}" "${fpath}" 2>/dev/null
      log "  [RESTORE] ${fpath} ← ${src_path}"
      RESTORED=$((RESTORED + 1))
    else
      log "  [WARN] ${fpath} is not a regular file and no CI source at ${src_path}"
      log "  [DIAG] File info: $(file "${fpath}" 2>/dev/null || echo 'MISSING')"
    fi
  fi
done
if [[ ${RESTORED} -gt 0 ]]; then
  log "Restored ${RESTORED} file(s) from CI source"
fi
step_end

# =============================================================================
# STEP 9: Start containers
# =============================================================================
step_start "Start containers"
DEPLOYMENT_STATE="COMPOSING"
COMPOSE_UPDATED=true

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
if ! "${SCRIPTS_DIR}/healthcheck.sh" 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "Health checks failed after deployment"
fi
step_end

# =============================================================================
# STEP 11: Record deployed images to disk
# =============================================================================
step_start "Record deployed images"
cat > "${PREVIOUS_IMAGES_FILE}" <<EOF
{
  "backend_image":    "${BACKEND_IMAGE}",
  "storefront_image": "${STOREFRONT_IMAGE}",
  "admin_image":      "${ADMIN_IMAGE}",
  "deployed_at":      "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "image_tag":        "${IMAGE_TAG}",
  "git_sha":          "${GIT_COMMIT_SHA:-unknown}",
  "git_author":       "${GIT_COMMIT_AUTHOR:-unknown}"
}
EOF
log "Deployed image state written to ${PREVIOUS_IMAGES_FILE}"
DEPLOYMENT_STATE="COMPLETED"
step_end

# =============================================================================
# STEP 12: Cleanup old application images
# =============================================================================
step_start "Cleanup old application images"
GHCR_PREFIX="ghcr.io/${GHCR_ORG}/"
log "Pruning unused ${GHCR_PREFIX}* images (keeping current and previous)"

KEEP_IMAGES=(
  "${BACKEND_IMAGE}"
  "${STOREFRONT_IMAGE}"
  "${ADMIN_IMAGE}"
  "${PREVIOUS_BACKEND_IMAGE:-}"
  "${PREVIOUS_STOREFRONT_IMAGE:-}"
  "${PREVIOUS_ADMIN_IMAGE:-}"
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
