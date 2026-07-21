#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Hadha.co Production Deployment Script
#
# Usage: ./deploy.sh <image_tag>
#
# Required environment variables (exported by CI):
#   GHCR_TOKEN, GHCR_USERNAME, REDIS_PASSWORD, REDIS_UI_USERNAME,
#   REDIS_UI_PASSWORD, DOZZLE_USERNAME, DOZZLE_PASSWORD, GRAFANA_USERNAME,
#   GRAFANA_PASSWORD, GLITCHTIP_DB_PASSWORD, GLITCHTIP_SECRET_KEY,
#   MONITORING_USERNAME, MONITORING_PASSWORD, RESEND_API_KEY,
#   RESEND_FROM_EMAIL, RESEND_TO_EMAIL, GIT_COMMIT_SHA, GIT_COMMIT_AUTHOR
# =============================================================================

set -uo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────
IMAGE_TAG="${1:?Usage: $0 <image_tag>}"
DEPLOY_START=$(date +%s)

# ── Production config ─────────────────────────────────────────────────────────
ENVIRONMENT="production"
APP_DIR="/opt/hadha"
INFRA_COMPOSE="${APP_DIR}/docker-compose.infrastructure.yml"
APP_COMPOSE="${APP_DIR}/docker-compose.application.yml"
ENV_FILE="${APP_DIR}/.env.production"
BACKEND_CONTAINER="hadha-backend"
STOREFRONT_CONTAINER="hadha-storefront"
ADMIN_CONTAINER="hadha-admin"
APP_URL="https://hadha.co"
NETWORK_NAME="hadha"
MIGRATION_CONTAINER="hadha-migration"

# ── IPv4/IPv6 detection ──────────────────────────────────────────────────────
IPV4_FUNCTIONAL=false
IPV6_FUNCTIONAL=false

detect_ip_support() {
  # Check IPv4 — if we can ping a known-working IPv4 address, IPv4 works
  if ping -4 -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
    IPV4_FUNCTIONAL=true
    log "  IPv4: functional"
  elif ip -4 addr show scope global 2>/dev/null | grep -q 'inet '; then
    IPV4_FUNCTIONAL=true
    log "  IPv4: configured (ping test unavailable)"
  else
    log "  IPv4: NOT functional"
  fi

  # Check IPv6 — must have both config AND working connectivity
  if ip -6 route show default 2>/dev/null | grep -q 'default'; then
    if ping6 -c 1 -W 3 2001:4860:4860::8888 >/dev/null 2>&1 || \
       ping6 -c 1 -W 3 2606:4700:4700::1111 >/dev/null 2>&1; then
      IPV6_FUNCTIONAL=true
      log "  IPv6: functional"
    else
      log "  IPv6: configured but no internet connectivity (will fail for DB)"
    fi
  else
    log "  IPv6: not configured"
  fi
}

# ── Database pre-flight ───────────────────────────────────────────────────────
preflight_database() {
  local db_url="${DATABASE_URL:-}"
  [[ -z "${db_url}" ]] && { log "  DATABASE_URL not set — skipping pre-flight"; return 0; }

  # Extract host and port from DATABASE_URL
  local db_host db_port
  db_host=$(echo "${db_url}" | sed -n 's|.*@\([^:/]*\).*|\1|p')
  db_port=$(echo "${db_url}" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
  [[ -z "${db_port}" ]] && db_port=5432

  log "  Database host: ${db_host}:${db_port}"

  # Try TCP connectivity — prefer IPv4 if available, fallback through methods
  local tcp_ok=false

  if [[ "${IPV4_FUNCTIONAL}" == "true" ]]; then
    # Force IPv4 TCP check using nc
    if nc -4 -zw5 "${db_host}" "${db_port}" 2>/dev/null; then
      tcp_ok=true
      log "  TCP: reachable via IPv4"
    fi
  fi

  if [[ "${tcp_ok}" != "true" ]] && nc -zw5 "${db_host}" "${db_port}" 2>/dev/null; then
    tcp_ok=true
    log "  TCP: reachable"
  fi

  if [[ "${tcp_ok}" != "true" ]]; then
    # Bash fallback
    if (echo >/dev/tcp/"${db_host}"/"${db_port}") 2>/dev/null; then
      tcp_ok=true
      log "  TCP: reachable via bash /dev/tcp"
    fi
  fi

  if [[ "${tcp_ok}" != "true" ]]; then
    local msg="Cannot reach database at ${db_host}:${db_port}"
    log "  ✗ ${msg}"
    log "  This is usually caused by IPv6 AAAA record resolution on a VPS without working IPv6."
    log "  Fix: Set DATABASE_URL to use the IPv4 address directly, or run:"
    log "    echo 'precedence ::ffff:0:0/96 100' >> /etc/gai.conf"
    return 1
  fi

  return 0
}

GHCR_ORG="hadhacoofficial-prog"
BACKEND_IMAGE="ghcr.io/${GHCR_ORG}/hadha-backend:${IMAGE_TAG}"
STOREFRONT_IMAGE="ghcr.io/${GHCR_ORG}/hadha-storefront:${IMAGE_TAG}"
ADMIN_IMAGE="ghcr.io/${GHCR_ORG}/hadha-admin:${IMAGE_TAG}"
BACKUP_DIR="${APP_DIR}/backups"
SCRIPTS_DIR="${APP_DIR}/scripts"
LOG_FILE="${APP_DIR}/deploy.log"
PREVIOUS_IMAGES_FILE="${APP_DIR}/.previous_images"
IMAGE_RETENTION="${IMAGE_RETENTION:-168h}"

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

# ── Compose wrappers ──────────────────────────────────────────────────────────
dc_infra() {
  docker compose \
    --env-file "${ENV_FILE}" \
    -f "${INFRA_COMPOSE}" \
    "$@"
}

dc_app() {
  docker compose \
    --env-file "${ENV_FILE}" \
    -f "${APP_COMPOSE}" \
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

warn() {
  log "[WARN] $*"
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

pull_image_with_retry() {
  local image="$1"
  local attempt=0

  while (( attempt < _MAX_RETRIES )); do
    (( attempt++ ))
    log "  Pull attempt ${attempt}/${_MAX_RETRIES}: ${image}"

    local output exit_code
    output=$(docker pull "${image}" 2>&1) || exit_code=$?
    exit_code=${exit_code:-0}

    if [[ ${exit_code} -eq 0 ]]; then
      log "  ✓ Pulled successfully: ${image}"
      echo "${output}" >> "${LOG_FILE}"
      return 0
    fi

    log "  Registry response: $(echo "${output}" | tail -5 | tr '\n' '|')"

    local failure_class
    failure_class=$(classify_failure "${output}")
    log "  Failure class  : ${failure_class}"

    if (( attempt >= _MAX_RETRIES )); then
      log "  ✗ All ${_MAX_RETRIES} pull attempts failed for: ${image}"
      log "  Final failure class: ${failure_class}"
      return 1
    fi

    local delay="${_BACKOFFS[$((attempt - 1))]}"
    log "  Waiting ${delay}s before attempt $((attempt + 1))/${_MAX_RETRIES}..."
    sleep "${delay}"
  done
  return 1
}

check_image_manifest() {
  local image="$1"
  local attempt=0

  log "  Checking manifest: ${image}"

  while (( attempt < _MAX_RETRIES )); do
    (( attempt++ ))
    log "  Manifest check attempt ${attempt}/${_MAX_RETRIES}"

    local output exit_code
    output=$(docker manifest inspect "${image}" 2>&1) || exit_code=$?
    exit_code=${exit_code:-0}

    if [[ ${exit_code} -eq 0 ]]; then
      log "  ✓ Manifest confirmed: ${image}"
      return 0
    fi

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

verify_image_digest() {
  local image="$1"
  log "  Verifying digest: ${image}"

  local inspect_output
  if ! inspect_output=$(docker image inspect "${image}" 2>&1); then
    log "  ✗ docker image inspect failed"
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

  local rollback_status="not attempted"

  if [[ "${COMPOSE_UPDATED}" != "true" ]]; then
    rollback_status="skipped (no containers were modified)"
    log "[INFO] ${rollback_status}"
  else
    log "[INFO] Containers were modified — initiating automatic rollback..."

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
        log "[FATAL] Rollback failed"
      fi
    else
      rollback_status="skipped (no previous images recorded)"
      log "[WARN] No previous images available"
    fi
  fi

  DEPLOY_END=$(date +%s)
  DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
  LAST_LOGS=$(tail -100 "${LOG_FILE}" 2>/dev/null || echo "No logs available")

  # Send failure notification
  if [[ -n "${RESEND_API_KEY:-}" ]]; then
    curl -s -X POST "https://api.resend.com/emails" \
      -H "Authorization: Bearer ${RESEND_API_KEY}" \
      -H "Content-Type: application/json" \
      -d "{
        \"from\": \"${RESEND_FROM_EMAIL:-deploy@hadha.co}\",
        \"to\": [\"${RESEND_TO_EMAIL:-admin@hadha.co}\"],
        \"subject\": \"🔴 [PRODUCTION] Deployment failed — ${IMAGE_TAG}\",
        \"html\": \"<h2>Deployment Failed</h2><p><b>Tag:</b> ${IMAGE_TAG}</p><p><b>Step:</b> ${FAILED_STEP}</p><p><b>Rollback:</b> ${rollback_status}</p><p><b>Duration:</b> ${DEPLOY_DURATION}s</p><p><b>SHA:</b> ${GIT_COMMIT_SHA:-unknown}</p>\"
      }" 2>/dev/null || log "[WARN] Failure notification could not be sent"
  fi

  exit 1
}

# =============================================================================
# PRE-FLIGHT
# =============================================================================
log_section "Pre-flight checks"

[[ -d "${APP_DIR}" ]]      || die "Deploy directory ${APP_DIR} does not exist. Run bootstrap.sh first."
[[ -f "${INFRA_COMPOSE}" ]] || die "Infrastructure compose not found: ${INFRA_COMPOSE}"
[[ -f "${APP_COMPOSE}" ]]   || die "Application compose not found: ${APP_COMPOSE}"
[[ -f "${ENV_FILE}" ]]      || die "Env file not found: ${ENV_FILE}"

for _svc_env in "${APP_DIR}/.env.storefront.production" "${APP_DIR}/.env.admin.production"; do
  [[ -f "${_svc_env}" ]] || { touch "${_svc_env}"; log "Created placeholder: ${_svc_env}"; }
done
unset _svc_env

command -v docker >/dev/null 2>&1 || die "docker is not installed"
command -v curl   >/dev/null 2>&1 || die "curl is not installed"
command -v jq     >/dev/null 2>&1 || die "jq is not installed"

[[ -n "${GHCR_TOKEN:-}"         ]] || die "GHCR_TOKEN is required"
[[ -n "${REDIS_PASSWORD:-}"     ]] || die "REDIS_PASSWORD is required"
[[ -n "${REDIS_UI_USERNAME:-}"  ]] || die "REDIS_UI_USERNAME is required"
[[ -n "${REDIS_UI_PASSWORD:-}"  ]] || die "REDIS_UI_PASSWORD is required"
[[ -n "${DOZZLE_USERNAME:-}"    ]] || die "DOZZLE_USERNAME is required"
[[ -n "${DOZZLE_PASSWORD:-}"    ]] || die "DOZZLE_PASSWORD is required"
[[ -n "${GRAFANA_USERNAME:-}"   ]] || die "GRAFANA_USERNAME is required"
[[ -n "${GRAFANA_PASSWORD:-}"   ]] || die "GRAFANA_PASSWORD is required"
[[ -n "${GLITCHTIP_DB_PASSWORD:-}" ]] || die "GLITCHTIP_DB_PASSWORD is required"
[[ -n "${GLITCHTIP_SECRET_KEY:-}"  ]] || die "GLITCHTIP_SECRET_KEY is required"
if [[ -z "${RESEND_API_KEY:-}" ]]; then
  warn "RESEND_API_KEY not set — Grafana email alerts will not work"
fi

# Load GLITCHTIP_DSN from env file if not already set
if [[ -z "${GLITCHTIP_DSN:-}" ]]; then
  GLITCHTIP_DSN=$(grep -E '^GLITCHTIP_DSN=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-)
  export GLITCHTIP_DSN
fi
if [[ -z "${GLITCHTIP_FRONTEND_DSN:-}" ]]; then
  GLITCHTIP_FRONTEND_DSN=$(grep -E '^GLITCHTIP_FRONTEND_DSN=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-)
  export GLITCHTIP_FRONTEND_DSN
fi

log "Image tag    : ${IMAGE_TAG}"
log "Backend      : ${BACKEND_IMAGE}"
log "Storefront   : ${STOREFRONT_IMAGE}"
log "Admin        : ${ADMIN_IMAGE}"

# ── Detect IPv4/IPv6 support ──────────────────────────────────────────────────
log ""
log "Network detection:"
detect_ip_support

# =============================================================================
# STEP 0: Validate compose configuration
# =============================================================================
step_start "Validate compose configuration"

export BACKEND_IMAGE STOREFRONT_IMAGE ADMIN_IMAGE REDIS_PASSWORD \
       REDIS_UI_USERNAME REDIS_UI_PASSWORD \
       DOZZLE_USERNAME DOZZLE_PASSWORD \
       GRAFANA_USERNAME GRAFANA_PASSWORD \
       GLITCHTIP_DB_PASSWORD GLITCHTIP_SECRET_KEY \
       GLITCHTIP_DSN GLITCHTIP_FRONTEND_DSN \
       RESEND_API_KEY RESEND_FROM_EMAIL RESEND_TO_EMAIL

COMPOSE_VALIDATE_OUTPUT=$(dc_app config 2>&1) || {
  step_fail "docker compose config returned non-zero"
  log "[ERROR] Compose validation output:"
  log "${COMPOSE_VALIDATE_OUTPUT}"
  exit 1
}
log "Application compose configuration is valid"

COMPOSE_VALIDATE_OUTPUT=$(dc_infra config 2>&1) || {
  step_fail "Infrastructure compose config returned non-zero"
  log "[ERROR] Infrastructure compose validation output:"
  log "${COMPOSE_VALIDATE_OUTPUT}"
  exit 1
}
log "Infrastructure compose configuration is valid"
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
  [[ -n "${PREVIOUS_BACKEND_IMAGE}" ]] && log "Previous images loaded from disk"
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
  die "Backup failed — aborting to preserve rollback capability"
fi
step_end

# =============================================================================
# STEP 3: GHCR authentication
# =============================================================================
step_start "GHCR authentication"
if ! echo "${GHCR_TOKEN}" | docker login ghcr.io \
    -u "${GHCR_USERNAME:-${GHCR_ORG}}" --password-stdin 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "GHCR login failed"
fi
step_end

# =============================================================================
# STEP 4: Verify ALL app image manifests
# =============================================================================
step_start "Verify app image manifests (pre-pull, atomic)"

BACKEND_MANIFEST_OK=false
STOREFRONT_MANIFEST_OK=false
ADMIN_MANIFEST_OK=false

check_image_manifest "${BACKEND_IMAGE}"    && BACKEND_MANIFEST_OK=true    || log "[ERROR] Backend manifest not available"
check_image_manifest "${STOREFRONT_IMAGE}" && STOREFRONT_MANIFEST_OK=true || log "[ERROR] Storefront manifest not available"
check_image_manifest "${ADMIN_IMAGE}"      && ADMIN_MANIFEST_OK=true      || log "[ERROR] Admin manifest not available"

if [[ "${BACKEND_MANIFEST_OK}" != "true" ]] || \
   [[ "${STOREFRONT_MANIFEST_OK}" != "true" ]] || \
   [[ "${ADMIN_MANIFEST_OK}" != "true" ]]; then
  rollback_and_exit "App image manifest(s) unavailable after retries"
fi

log "✓ All app manifests confirmed"
step_end

# =============================================================================
# STEP 5: Pull ALL images with retry
# =============================================================================
step_start "Pull all images"
DEPLOYMENT_STATE="PULLING"

log "── Infrastructure images ──"
for img in "${INFRA_IMAGES[@]}"; do
  if ! pull_image_with_retry "${img}"; then
    rollback_and_exit "Failed to pull infrastructure image: ${img}"
  fi
done

log "── Application images ──"
if ! pull_image_with_retry "${BACKEND_IMAGE}"; then
  rollback_and_exit "Failed to pull backend image: ${BACKEND_IMAGE}"
fi
if ! pull_image_with_retry "${STOREFRONT_IMAGE}"; then
  rollback_and_exit "Failed to pull storefront image: ${STOREFRONT_IMAGE}"
fi
if ! pull_image_with_retry "${ADMIN_IMAGE}"; then
  rollback_and_exit "Failed to pull admin image: ${ADMIN_IMAGE}"
fi

PULLED_IMAGES=true
step_end

# =============================================================================
# STEP 6: Verify image digests
# =============================================================================
step_start "Verify image digests"

DIGEST_FAILURES=()
for img in "${BACKEND_IMAGE}" "${STOREFRONT_IMAGE}" "${ADMIN_IMAGE}"; do
  if docker image inspect "${img}" >/dev/null 2>&1; then
    log "  ✓ present: ${img}"
    if ! verify_image_digest "${img}"; then
      DIGEST_FAILURES+=("${img}")
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
  docker network create --driver bridge "${NETWORK_NAME}" 2>&1 | tee -a "${LOG_FILE}" \
    || log "[WARN] Network creation failed — compose will handle it"
fi
step_end

# =============================================================================
# STEP 7.5: Generate Dozzle authentication file
# =============================================================================
step_start "Generate Dozzle authentication file"

DOZZLE_DIR="${APP_DIR}/dozzle"
mkdir -p "${DOZZLE_DIR}"

if [[ -f "${DOZZLE_DIR}/users.yml" ]]; then
  rm -f "${DOZZLE_DIR}/users.yml"
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
log "Dozzle auth file written"
step_end

# =============================================================================
# STEP 7.6: Generate nginx basic-auth file
# =============================================================================
step_start "Generate nginx basic-auth file"

NGINX_DIR="${APP_DIR}/nginx"
HTPASSWD_FILE="${NGINX_DIR}/.htpasswd"

if [[ -f "${HTPASSWD_FILE}" ]]; then
  rm -f "${HTPASSWD_FILE}"
fi

mkdir -p "${NGINX_DIR}"

if [[ -z "${MONITORING_USERNAME:-}" ]] || [[ -z "${MONITORING_PASSWORD:-}" ]]; then
  die "MONITORING_USERNAME and MONITORING_PASSWORD are required"
fi

htpasswd -cb "${HTPASSWD_FILE}" "${MONITORING_USERNAME}" "${MONITORING_PASSWORD}" 2>/dev/null \
  || die "Failed to generate htpasswd file"

chmod 644 "${HTPASSWD_FILE}"
log "Basic-auth file written"
step_end

# =============================================================================
# STEP 7.7: Database pre-flight connectivity
# =============================================================================
step_start "Database pre-flight check"

# Source DATABASE_URL from env file for the pre-flight check
DATABASE_URL=$(grep -E '^DATABASE_URL=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-)
if ! preflight_database; then
  rollback_and_exit "Database pre-flight failed — cannot reach Supabase PostgreSQL"
fi

log "  ✓ Database reachable"
step_end

# =============================================================================
# STEP 8: Database migrations
# =============================================================================
step_start "Database migrations (Supabase)"
DEPLOYMENT_STATE="MIGRATING"

# Remove any stale migration container from previous runs
if docker inspect "${MIGRATION_CONTAINER}" >/dev/null 2>&1; then
  log "Removing stale migration container"
  docker rm -f "${MIGRATION_CONTAINER}" >/dev/null 2>&1 || true
  sleep 1
fi

# Sanitize env file — remove Windows \r, empty lines, and ensure no trailing whitespace
SANITIZED_ENV="/tmp/hadha-migration.env"
sed 's/\r$//' "${ENV_FILE}" | sed '/^$/d' | sed 's/[[:space:]]*$//' > "${SANITIZED_ENV}" 2>/dev/null || cp "${ENV_FILE}" "${SANITIZED_ENV}"

# Diagnostic: verify the image can start and run a simple command
log "  Diagnostic: testing image startup..."
DIAG_OUTPUT=$(docker run --rm --env-file "${SANITIZED_ENV}" --network "${NETWORK_NAME}" \
    "${BACKEND_IMAGE}" python -c "import sys; print(f'Python {sys.version} OK'); print('Module import test...'); import alembic; print(f'Alembic {alembic.__version__} OK')" 2>&1) || DIAG_EXIT=$?
DIAG_EXIT=${DIAG_EXIT:-0}
log "  Diagnostic exit code: ${DIAG_EXIT}"
if [[ ${DIAG_EXIT} -ne 0 ]]; then
  log "  Diagnostic output: ${DIAG_OUTPUT}"
  log "  ⚠ Image cannot start properly — check env file and image build"
  # Continue anyway — the migration might reveal the actual error
else
  log "  Diagnostic output: ${DIAG_OUTPUT}"
fi

# Always disable IPv6 for the migration container — the DB pre-flight confirmed
# IPv4 works, and Supabase's AAAA records are unreachable from this VPS even when
# the host-level IPv6 check passes (the kernel advertises it but can't route it).
MIGRATION_SYSCTL_ARGS=(--sysctl "net.ipv6.conf.all.disable_ipv6=1")
log "  IPv6 disabled for migration container (using IPv4 to reach Supabase)"

# Retry migration up to 3 times with backoff
MIGRATION_MAX_ATTEMPTS=3
MIGRATION_ATTEMPT=0
MIGRATION_OK=false
MIGRATION_EXIT=0

while (( MIGRATION_ATTEMPT < MIGRATION_MAX_ATTEMPTS )); do
  MIGRATION_ATTEMPT=$(( MIGRATION_ATTEMPT + 1 ))
  log "  Migration attempt ${MIGRATION_ATTEMPT}/${MIGRATION_MAX_ATTEMPTS}"

  CONTAINER_NAME="${MIGRATION_CONTAINER}-${MIGRATION_ATTEMPT}"
  MIGRATION_LOG="${APP_DIR}/migration-attempt-${MIGRATION_ATTEMPT}.log"

  # Build docker run command as an array to avoid quoting issues
  DOCKER_ARGS=(docker run --rm --name "${CONTAINER_NAME}" --env-file "${SANITIZED_ENV}" --network "${NETWORK_NAME}")
  if [[ ${#MIGRATION_SYSCTL_ARGS[@]} -gt 0 ]]; then
    DOCKER_ARGS+=("${MIGRATION_SYSCTL_ARGS[@]}")
  fi
  DOCKER_ARGS+=("${BACKEND_IMAGE}" alembic -c alembic/alembic.ini upgrade head)

  # Run migration — capture exit code without set -e (script uses set -uo pipefail only)
  MIGRATION_EXIT=0
  "${DOCKER_ARGS[@]}" > "${MIGRATION_LOG}" 2>&1 || MIGRATION_EXIT=$?

  # Append to deploy log
  if [[ -f "${MIGRATION_LOG}" ]] && [[ -s "${MIGRATION_LOG}" ]]; then
    log "  Migration output:"
    cat "${MIGRATION_LOG}" | tee -a "${LOG_FILE}"
  fi

  if [[ ${MIGRATION_EXIT} -eq 0 ]]; then
    MIGRATION_OK=true
    log "  ✓ Migration succeeded"
    break
  fi

  log "  ✗ Migration attempt ${MIGRATION_ATTEMPT} failed (exit code: ${MIGRATION_EXIT})"

  if [[ -z "${MIGRATION_LOG}" ]] || [[ ! -s "${MIGRATION_LOG}" ]]; then
    log "  ⚠ No output captured from migration container"
    log "  Possible causes:"
    log "    - Container failed to start (image or env issue)"
    log "    - Docker daemon rejected the request"
    log "    - Non-root user (hadha) cannot execute entrypoint"
  fi

  if (( MIGRATION_ATTEMPT < MIGRATION_MAX_ATTEMPTS )); then
    log "  Waiting 15s before retry..."
    sleep 15
  fi
done

# Cleanup
rm -f "${SANITIZED_ENV}"

if [[ "${MIGRATION_OK}" != "true" ]]; then
  rollback_and_exit "Database migration failed after ${MIGRATION_MAX_ATTEMPTS} attempts (exit code: ${MIGRATION_EXIT})"
fi
MIGRATIONS_COMPLETED=true
step_end

# =============================================================================
# STEP 8.5: Sync monitoring configs from deploy artifacts
# =============================================================================
step_start "Sync monitoring configs"

# Monitoring configs are deployed via SCP to /tmp/hadha-deploy by CI.
# Sync them to /opt/hadha/ if available.
SYNC_SRC="/tmp/hadha-deploy"
if [[ -d "${SYNC_SRC}" ]]; then
  log "Syncing configs from CI deploy artifacts..."

  # Nginx
  if [[ -f "${SYNC_SRC}/Infra/infrastructure/nginx/nginx.conf" ]]; then
    cp -f "${SYNC_SRC}/Infra/infrastructure/nginx/nginx.conf" "${APP_DIR}/nginx/nginx.conf"
    mkdir -p "${APP_DIR}/nginx/conf.d"
    for f in "${SYNC_SRC}/Infra/infrastructure/nginx/conf.d/"*.conf; do
      [[ -f "$f" ]] && cp -f "$f" "${APP_DIR}/nginx/conf.d/$(basename "$f")"
    done
    log "  Nginx configs synced"
  fi

  # Monitoring
  for subdir in prometheus loki promtail grafana; do
    if [[ -d "${SYNC_SRC}/Infra/infrastructure/monitoring/${subdir}" ]]; then
      mkdir -p "${APP_DIR}/monitoring/${subdir}"
      cp -rf "${SYNC_SRC}/Infra/infrastructure/monitoring/${subdir}/"* "${APP_DIR}/monitoring/${subdir}/" 2>/dev/null || true
      log "  Monitoring configs synced: ${subdir}"
    fi
  done

  # Grafana dashboards
  if [[ -d "${SYNC_SRC}/Infra/infrastructure/monitoring/grafana/dashboards" ]]; then
    mkdir -p "${APP_DIR}/monitoring/grafana/dashboards"
    cp -f "${SYNC_SRC}/Infra/infrastructure/monitoring/grafana/dashboards/"*.json "${APP_DIR}/monitoring/grafana/dashboards/" 2>/dev/null || true
    log "  Grafana dashboards synced"
  fi
else
  log "No CI deploy artifacts found at ${SYNC_SRC} — using existing configs"
fi
step_end

# =============================================================================
# STEP 8.6: Idempotent infrastructure startup
# =============================================================================
step_start "Idempotent infrastructure startup"

# Remove any orphaned containers from previous project names that conflict
for orphan in $(docker ps -a --filter "name=hadha-" --format '{{.Names}}' 2>/dev/null | grep -v '^hadha-' || true); do
  # This shouldn't match anything since we filter by hadha- prefix
  :
done

# Ensure infrastructure stack is running — use -d for background.
# Docker Compose is idempotent: only recreate containers with changed configs.
log "Ensuring infrastructure stack is running (idempotent)..."
dc_infra up -d --remove-orphans --pull never 2>&1 | tee -a "${LOG_FILE}" || true

# Log container statuses for debugging
for c in hadha-loki hadha-promtail hadha-prometheus hadha-grafana hadha-nginx hadha-redis; do
  local_status=$(docker inspect --format='{{.State.Status}}' "${c}" 2>/dev/null || echo "not_found")
  log "  ${c}: ${local_status}"
done
step_end

# =============================================================================
# STEP 9: Start application containers
# =============================================================================
step_start "Start application containers"
DEPLOYMENT_STATE="COMPOSING"
COMPOSE_UPDATED=true

if ! dc_app up -d --remove-orphans --pull never 2>&1 | tee -a "${LOG_FILE}"; then
  rollback_and_exit "docker compose up (application) failed"
fi
CONTAINERS_RESTARTED=true
log "Application containers started"

# Reload nginx to re-resolve upstream hostnames
log "Reloading nginx..."
if docker exec hadha-nginx nginx -s reload 2>/dev/null; then
  log "  ✓ nginx reloaded"
else
  log "  [WARN] nginx reload failed"
fi

log "Waiting for health checks..."
step_end

# =============================================================================
# STEP 10: Health checks
# =============================================================================
step_start "Health checks"
if ! "${SCRIPTS_DIR}/verify.sh" 2>&1 | tee -a "${LOG_FILE}"; then
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

KEEP_IMAGES=(
  "${BACKEND_IMAGE}" "${STOREFRONT_IMAGE}" "${ADMIN_IMAGE}"
  "${PREVIOUS_BACKEND_IMAGE:-}" "${PREVIOUS_STOREFRONT_IMAGE:-}" "${PREVIOUS_ADMIN_IMAGE:-}"
)

docker images --format "{{.Repository}}:{{.Tag}}\t{{.ID}}" \
  | grep "^${GHCR_PREFIX}" \
  | while IFS=$'\t' read -r full_name img_id; do
      local_keep=false
      for keep in "${KEEP_IMAGES[@]}"; do
        [[ -z "${keep}" ]] && continue
        [[ "${full_name}" == "${keep}" ]] && { local_keep=true; break; }
      done
      if [[ "${local_keep}" != "true" ]]; then
        log "  removing: ${full_name} (${img_id})"
        docker rmi "${img_id}" 2>/dev/null || true
      fi
    done
step_end

# =============================================================================
# COMPLETE
# =============================================================================
DEPLOY_END=$(date +%s)
DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
log_section "Deployment complete — ${DEPLOY_DURATION}s"

# Send success notification
if [[ -n "${RESEND_API_KEY:-}" ]]; then
  curl -s -X POST "https://api.resend.com/emails" \
    -H "Authorization: Bearer ${RESEND_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
      \"from\": \"${RESEND_FROM_EMAIL:-deploy@hadha.co}\",
      \"to\": [\"${RESEND_TO_EMAIL:-admin@hadha.co}\"],
      \"subject\": \"🟢 [PRODUCTION] Deployment successful — ${IMAGE_TAG}\",
      \"html\": \"<h2>Deployment Successful</h2><p><b>Tag:</b> ${IMAGE_TAG}</p><p><b>Duration:</b> ${DEPLOY_DURATION}s</p><p><b>SHA:</b> ${GIT_COMMIT_SHA:-unknown}</p><p><b>Author:</b> ${GIT_COMMIT_AUTHOR:-unknown}</p>\"
    }" 2>/dev/null || log "[WARN] Success notification failed"
fi

exit 0
