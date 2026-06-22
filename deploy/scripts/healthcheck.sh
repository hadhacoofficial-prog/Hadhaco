#!/usr/bin/env bash
# =============================================================================
# healthcheck.sh — Verify all services are healthy after deployment
#
# Usage:
#   ./healthcheck.sh <environment>
#
# Exit code:
#   0 — all required checks passed
#   1 — one or more checks failed
#
# Check strategy:
#   - Polls each service with exponential backoff (2s → 4s → 8s … max 30s)
#   - Total timeout per service: 120s
#   - All checks run before reporting failures (no early exit)
#   - Backend uses correct Host header to bypass TrustedHostMiddleware
# =============================================================================

# NOT set -e — failures accumulate in FAILED[] and are reported at the end.
set -uo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment>}"

# ── Config ────────────────────────────────────────────────────────────────────
case "$ENVIRONMENT" in
  production)
    APP_URL="https://hadha.co"
    BACKEND_HOST="hadha.co"
    BACKEND_CONTAINER="hadha-backend"
    FRONTEND_CONTAINER="hadha-frontend"
    REDIS_CONTAINER="hadha-redis"
    NGINX_CONTAINER="hadha-nginx"
    RC_CONTAINER="hadha-redis-commander"
    DOZZLE_CONTAINER="hadha-dozzle"
    ;;
  staging)
    APP_URL="https://staging.hadha.co"
    BACKEND_HOST="staging.hadha.co"
    BACKEND_CONTAINER="hadha-staging-backend"
    FRONTEND_CONTAINER="hadha-staging-frontend"
    REDIS_CONTAINER="hadha-staging-redis"
    NGINX_CONTAINER="hadha-staging-nginx"
    RC_CONTAINER="hadha-staging-redis-commander"
    DOZZLE_CONTAINER="hadha-staging-dozzle"
    ;;
  *)
    echo "[ERROR] Unknown environment: ${ENVIRONMENT}"
    exit 1
    ;;
esac

TIMEOUT=120    # seconds per service before giving up
FAILED=()
CHECK_START=$(date +%s)

# ── Logging ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date +'%H:%M:%S')] $*"; }
pass() { log "  ✓ $*"; }
fail() { log "  ✗ $*"; FAILED+=("$*"); }
warn() { log "  ⚠ $*"; }

# ── wait_for: poll with exponential backoff ───────────────────────────────────
# Args: <display_name> <check_function> [timeout_seconds]
# Returns 0 on success, 1 on timeout. Adds to FAILED[] on timeout.
wait_for() {
  local name="$1"
  local check_fn="$2"
  local max_wait="${3:-${TIMEOUT}}"
  local elapsed=0
  local interval=2
  local max_interval=30

  log "  Checking: ${name}"
  while (( elapsed < max_wait )); do
    # H-1 FIX: was eval "${check_fn}" — eval is unnecessary for simple function
    # names and masks future bugs. Direct call is correct and explicit.
    if "${check_fn}" 2>/dev/null; then
      pass "${name} (${elapsed}s)"
      return 0
    fi
    sleep "${interval}"
    elapsed=$(( elapsed + interval ))
    # Exponential backoff capped at max_interval
    interval=$(( interval * 2 ))
    (( interval > max_interval )) && interval=${max_interval}
    log "  … ${elapsed}s / ${max_wait}s — retrying ${name} in ${interval}s"
  done

  fail "${name} — timed out after ${max_wait}s"
  return 1
}

# =============================================================================
# Check functions
# Each must return 0 on success, non-zero on failure.
# docker exec is used for internal checks to bypass TLS and port exposure.
# =============================================================================

# Backend liveness: quick check that the process is alive.
# Sends correct Host header to satisfy TrustedHostMiddleware.
check_backend_live() {
  docker exec "${BACKEND_CONTAINER}" \
    python -c "
import httpx, sys
try:
    r = httpx.get('http://localhost:8000/health/live', headers={'Host': '${BACKEND_HOST}'}, timeout=5)
    sys.exit(0 if r.status_code < 400 else 1)
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null
}

# Backend readiness: confirms DB + Redis connections are up.
check_backend_ready() {
  docker exec "${BACKEND_CONTAINER}" \
    python -c "
import httpx, sys
try:
    r = httpx.get('http://localhost:8000/health/ready', headers={'Host': '${BACKEND_HOST}'}, timeout=8)
    sys.exit(0 if r.status_code == 200 else 1)
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null
}

# Frontend: basic HTTP response on port 3000.
check_frontend() {
  docker exec "${FRONTEND_CONTAINER}" \
    curl -sf --max-time 5 "http://localhost:3000" -o /dev/null 2>/dev/null
}

# Redis: PING/PONG with password from environment.
check_redis() {
  local redis_pw="${REDIS_PASSWORD:-}"
  if [[ -n "${redis_pw}" ]]; then
    docker exec "${REDIS_CONTAINER}" \
      redis-cli -a "${redis_pw}" --no-auth-warning ping 2>/dev/null \
      | grep -q "^PONG$"
  else
    docker exec "${REDIS_CONTAINER}" \
      redis-cli ping 2>/dev/null \
      | grep -q "^PONG$"
  fi
}

# Nginx: config valid AND actually responding to HTTP.
check_nginx() {
  # First validate config is syntactically correct.
  docker exec "${NGINX_CONTAINER}" nginx -t 2>/dev/null || return 1
  # C-2 FIX: --server-response is GNU wget only; nginx:stable-alpine uses
  # BusyBox wget which does not support it, making the grep always fail.
  # Use wget -q -O /dev/null --no-check-certificate so the request succeeds
  # even when port 80 redirects to HTTPS (cert is for hadha.co, not localhost).
  docker exec "${NGINX_CONTAINER}" \
    wget -q -O /dev/null --no-check-certificate "http://127.0.0.1:80/" 2>/dev/null
}

# Redis Commander: web UI responding on port 8081.
check_redis_commander() {
  # C-2 / M-4 FIX: redis-commander runs on Node.js (node:alpine). BusyBox wget
  # --server-response is unsupported. Use node (always present) for an HTTP
  # check that also validates the status code is not a 5xx server error.
  docker exec "${RC_CONTAINER}" \
    node -e "
var http=require('http');
http.get('http://localhost:8081/redis-commander/',function(r){
  process.exit(r.statusCode<500?0:1);
}).on('error',function(e){
  process.stderr.write(e.message+'\n');
  process.exit(1);
});
" 2>/dev/null
}

# Dozzle: web UI responding on port 8080.
check_dozzle() {
  # C-2 FIX: --server-response is BusyBox-unsupported. Dozzle v8 ships its
  # own /dozzle healthcheck binary (same binary as the main process). Use it
  # directly — it is the official healthcheck method from dozzle's Dockerfile.
  docker exec "${DOZZLE_CONTAINER}" /dozzle healthcheck 2>/dev/null
}

# =============================================================================
# Run all checks
# Required services (Redis, backend, frontend, nginx) are blocking.
# Monitoring services (Redis Commander, Dozzle) are non-blocking warnings.
# =============================================================================
log ""
log "════ Health Checks: ${ENVIRONMENT} [$(date +'%H:%M:%S')] ════"
log ""

# Redis must be healthy first (backend depends on it)
wait_for "Redis"                              "check_redis"             || true

# Backend: liveness first, then readiness (which checks DB+Redis)
wait_for "Backend liveness  (/health/live)"   "check_backend_live"      || true
wait_for "Backend readiness (/health/ready)"  "check_backend_ready"     || true

# Frontend
wait_for "Frontend"                           "check_frontend"          || true

# Nginx (config + HTTP response)
wait_for "Nginx"                              "check_nginx"             || true

# Monitoring tools — degraded state is acceptable, log warn instead of fail
log "  Checking: Redis Commander (non-blocking)"
if check_redis_commander 2>/dev/null; then
  pass "Redis Commander"
else
  warn "Redis Commander not responding (monitoring only — deployment continues)"
fi

log "  Checking: Dozzle (non-blocking)"
if check_dozzle 2>/dev/null; then
  pass "Dozzle"
else
  warn "Dozzle not responding (monitoring only — deployment continues)"
fi

# =============================================================================
# External HTTP probe (through public DNS / internet)
# =============================================================================
log ""
log "  External HTTP probe → ${APP_URL}"
EXTERNAL_OK=false
HTTP_STATUS="000"
for attempt in 1 2 3; do
  HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
    --max-time 15 --connect-timeout 5 "${APP_URL}" 2>/dev/null || echo "000")
  if [[ "${HTTP_STATUS}" =~ ^[23] ]]; then
    pass "External HTTP → ${HTTP_STATUS} (${APP_URL})"
    EXTERNAL_OK=true
    break
  fi
  if (( attempt < 3 )); then
    log "  HTTP ${HTTP_STATUS} — retrying in 10s (attempt ${attempt}/3)..."
    sleep 10
  fi
done
[[ "${EXTERNAL_OK}" == "true" ]] || fail "External HTTP → ${HTTP_STATUS} (${APP_URL})"

# Backend API through nginx
API_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  --max-time 10 "${APP_URL}/health/live" 2>/dev/null || echo "000")
if [[ "${API_STATUS}" =~ ^[23] ]]; then
  pass "Backend API /health/live through nginx → ${API_STATUS}"
else
  fail "Backend API /health/live through nginx → ${API_STATUS}"
fi

# =============================================================================
# Summary
# =============================================================================
TOTAL_ELAPSED=$(( $(date +%s) - CHECK_START ))
log ""
log "════ Health Check Summary ════"
if [[ ${#FAILED[@]} -eq 0 ]]; then
  log "All required checks passed ✓ (${TOTAL_ELAPSED}s)"
  exit 0
else
  log "FAILED (${#FAILED[@]}) required check(s) after ${TOTAL_ELAPSED}s:"
  for f in "${FAILED[@]}"; do
    log "  ✗ ${f}"
  done
  exit 1
fi
