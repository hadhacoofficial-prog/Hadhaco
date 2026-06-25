#!/usr/bin/env bash
# =============================================================================
# healthcheck.sh — Verify all production services are healthy after deployment
#
# Usage:
#   ./healthcheck.sh
#
# Exit code:
#   0 — all required checks passed
#   1 — one or more checks failed
# =============================================================================

set -uo pipefail

APP_URL="https://hadha.co"
API_URL="https://api.hadha.co"
BACKEND_HOST="api.hadha.co"
BACKEND_CONTAINER="hadha-backend"
STOREFRONT_CONTAINER="hadha-storefront"
ADMIN_CONTAINER="hadha-admin"
REDIS_CONTAINER="hadha-redis"
NGINX_CONTAINER="hadha-nginx"
RC_CONTAINER="hadha-redis-commander"
DOZZLE_CONTAINER="hadha-dozzle"

TIMEOUT=120
FAILED=()
CHECK_START=$(date +%s)

log()  { echo "[$(date +'%H:%M:%S')] $*"; }
pass() { log "  ✓ $*"; }
fail() { log "  ✗ $*"; FAILED+=("$*"); }
warn() { log "  ⚠ $*"; }

# ── wait_for: poll with exponential backoff ───────────────────────────────────
wait_for() {
  local name="$1"
  local check_fn="$2"
  local max_wait="${3:-${TIMEOUT}}"
  local elapsed=0
  local interval=2
  local max_interval=30

  log "  Checking: ${name}"
  while (( elapsed < max_wait )); do
    if "${check_fn}" 2>/dev/null; then
      pass "${name} (${elapsed}s)"
      return 0
    fi
    sleep "${interval}"
    elapsed=$(( elapsed + interval ))
    interval=$(( interval * 2 ))
    (( interval > max_interval )) && interval=${max_interval}
    log "  … ${elapsed}s / ${max_wait}s — retrying ${name} in ${interval}s"
  done

  fail "${name} — timed out after ${max_wait}s"
  return 1
}

# =============================================================================
# Check functions
# =============================================================================

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

check_storefront() {
  docker exec "${STOREFRONT_CONTAINER}" \
    curl -sf --max-time 5 "http://localhost:3000" -o /dev/null 2>/dev/null
}

check_admin() {
  docker exec "${ADMIN_CONTAINER}" \
    curl -sf --max-time 5 "http://localhost:3000" -o /dev/null 2>/dev/null
}

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

check_nginx() {
  docker exec "${NGINX_CONTAINER}" nginx -t 2>/dev/null || return 1
  docker exec "${NGINX_CONTAINER}" \
    wget -q -O /dev/null --no-check-certificate "http://127.0.0.1:80/" 2>/dev/null
}

check_redis_commander() {
  docker exec "${RC_CONTAINER}" \
    node -e "
var http=require('http');
http.get('http://localhost:8081/',function(r){
  process.exit(r.statusCode<500?0:1);
}).on('error',function(e){
  process.stderr.write(e.message+'\n');
  process.exit(1);
});
" 2>/dev/null
}

check_dozzle() {
  docker exec "${DOZZLE_CONTAINER}" /dozzle healthcheck 2>/dev/null
}

# =============================================================================
# Run all checks
# =============================================================================
log ""
log "════ Health Checks: production [$(date +'%H:%M:%S')] ════"
log ""

wait_for "Redis"                              "check_redis"             || true
wait_for "Backend liveness  (/health/live)"   "check_backend_live"      || true
wait_for "Backend readiness (/health/ready)"  "check_backend_ready"     || true
wait_for "Storefront"                         "check_storefront"        || true
wait_for "Admin"                              "check_admin"             || true
wait_for "Nginx"                              "check_nginx"             || true

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
# External HTTP probe
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

API_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  --max-time 10 "${API_URL}/health/live" 2>/dev/null || echo "000")
if [[ "${API_STATUS}" =~ ^[23] ]]; then
  pass "Backend API /health/live → ${API_STATUS} (${API_URL})"
else
  fail "Backend API /health/live → ${API_STATUS} (${API_URL})"
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
