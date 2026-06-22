#!/usr/bin/env bash
# =============================================================================
# healthcheck.sh — Verify all services are healthy after deployment
#
# Usage:
#   ./healthcheck.sh <environment>
#
# Exit code:
#   0 — all checks passed
#   1 — one or more checks failed
#
# Timeout: 2 minutes total (120s) per check
# =============================================================================

# NOT set -e — failures are accumulated into FAILED[] and reported at the end.
# Using set -e would cause the script to exit on the first failed check instead
# of running all checks and giving a complete health picture.
set -uo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment>}"

case "$ENVIRONMENT" in
  production)
    APP_URL="https://hadha.co"
    BACKEND_CONTAINER="hadha-backend"
    FRONTEND_CONTAINER="hadha-frontend"
    REDIS_CONTAINER="hadha-redis"
    NGINX_CONTAINER="hadha-nginx"
    ;;
  staging)
    APP_URL="https://staging.hadha.co"
    BACKEND_CONTAINER="hadha-staging-backend"
    FRONTEND_CONTAINER="hadha-staging-frontend"
    REDIS_CONTAINER="hadha-staging-redis"
    NGINX_CONTAINER="hadha-staging-nginx"
    ;;
  *)
    echo "[ERROR] Unknown environment: ${ENVIRONMENT}"
    exit 1
    ;;
esac

TIMEOUT=120
FAILED=()

log()  { echo "[$(date +'%H:%M:%S')] $*"; }
pass() { log "  ✓ $*"; }
fail() { log "  ✗ $*"; FAILED+=("$*"); }

wait_for() {
  local name="$1" check_fn="$2"
  local elapsed=0 interval=5

  log "Waiting for: ${name}"
  while (( elapsed < TIMEOUT )); do
    if "${check_fn}"; then
      pass "${name}"
      return 0
    fi
    sleep "${interval}"
    elapsed=$(( elapsed + interval ))
    log "  … ${elapsed}s elapsed (timeout: ${TIMEOUT}s)"
  done
  fail "${name} — timed out after ${TIMEOUT}s"
  return 1
}

# ── Check functions ───────────────────────────────────────────────────────────

check_backend_liveness() {
  docker exec "${BACKEND_CONTAINER}" \
    python -c "import httpx; httpx.get('http://localhost:8000/health/live').raise_for_status()" \
    2>/dev/null
}

check_backend_readiness() {
  local result
  result=$(docker exec "${BACKEND_CONTAINER}" \
    python -c "import httpx; r=httpx.get('http://localhost:8000/health/ready'); print(r.status_code)" \
    2>/dev/null) || return 1
  [[ "${result}" == "200" ]]
}

check_frontend_liveness() {
  docker exec "${FRONTEND_CONTAINER}" \
    curl -sf "http://localhost:3000" -o /dev/null \
    2>/dev/null
}

check_redis_liveness() {
  local redis_pw="${REDIS_PASSWORD:-}"
  if [[ -n "${redis_pw}" ]]; then
    docker exec "${REDIS_CONTAINER}" \
      redis-cli -a "${redis_pw}" ping 2>/dev/null | grep -q PONG
  else
    docker exec "${REDIS_CONTAINER}" \
      redis-cli ping 2>/dev/null | grep -q PONG
  fi
}

check_nginx_http() {
  # wget is available in nginx:alpine; hitting /health proxied to backend
  docker exec "${NGINX_CONTAINER}" \
    wget -qO /dev/null --server-response "http://localhost/health" 2>&1 \
    | grep -qE "HTTP/[0-9.]+ [23]"
}

# ── Run all checks ─────────────────────────────────────────────────────────────
log "════ Health Checks: ${ENVIRONMENT} ════"

# Use || true so each wait_for failure is tracked in FAILED[] but doesn't abort
wait_for "Redis"                             check_redis_liveness    || true
wait_for "Backend (liveness)"               check_backend_liveness  || true
wait_for "Backend (readiness — DB + Redis)" check_backend_readiness || true
wait_for "Frontend"                         check_frontend_liveness || true
wait_for "Nginx HTTP"                       check_nginx_http        || true

# ── External HTTP check (through public internet / DNS) ──────────────────────
log "External HTTP probe → ${APP_URL}"
EXTERNAL_OK=false
for i in 1 2 3; do
  HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
    --max-time 15 --connect-timeout 5 "${APP_URL}" 2>/dev/null || echo "000")
  if [[ "${HTTP_STATUS}" =~ ^[23] ]]; then
    pass "External HTTP → ${HTTP_STATUS}"
    EXTERNAL_OK=true
    break
  fi
  if [[ $i -lt 3 ]]; then
    log "  HTTP ${HTTP_STATUS} — retrying in 10s…"
    sleep 10
  fi
done
[[ "${EXTERNAL_OK}" == "true" ]] || fail "External HTTP → ${HTTP_STATUS} (${APP_URL})"

# ── Backend API probe through nginx ──────────────────────────────────────────
API_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  --max-time 10 "${APP_URL}/health" 2>/dev/null || echo "000")
if [[ "${API_STATUS}" == "200" ]]; then
  pass "Backend API /health → 200"
else
  fail "Backend API /health → ${API_STATUS}"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log ""
if [[ ${#FAILED[@]} -eq 0 ]]; then
  log "All health checks passed ✓"
  exit 0
else
  log "FAILED checks (${#FAILED[@]}):"
  for f in "${FAILED[@]}"; do log "  - ${f}"; done
  exit 1
fi
