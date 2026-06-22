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
# Timeout: 2 minutes total (120s)
# =============================================================================

set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment>}"

case "$ENVIRONMENT" in
  production)
    APP_URL="https://hadha.co"
    BACKEND_INTERNAL="http://localhost:8000"
    COMPOSE_PROJECT="hadha-production"
    ;;
  staging)
    APP_URL="https://staging.hadha.co"
    BACKEND_INTERNAL="http://localhost:8001"  # adjust if staging uses a different port
    COMPOSE_PROJECT="hadha-staging"
    ;;
  *) echo "[ERROR] Unknown environment: ${ENVIRONMENT}"; exit 1 ;;
esac

TIMEOUT=120
INTERVAL=5
ELAPSED=0
FAILED=()

log()  { echo "[$(date +'%H:%M:%S')] $*"; }
pass() { log "  ✓ $*"; }
fail() { log "  ✗ $*"; FAILED+=("$*"); }

wait_for() {
  local name="$1" check_fn="$2"
  local elapsed=0 interval=5

  log "Waiting for: ${name}"
  while (( elapsed < TIMEOUT )); do
    if ${check_fn}; then
      pass "${name}"
      return 0
    fi
    sleep "${interval}"
    (( elapsed += interval ))
    log "  … ${elapsed}s elapsed (timeout: ${TIMEOUT}s)"
  done
  fail "${name} — timed out after ${TIMEOUT}s"
  return 1
}

# ── Check functions ───────────────────────────────────────────────────────────

check_backend_liveness() {
  docker exec hadha-backend \
    python -c "import httpx; httpx.get('http://localhost:8000/health/live').raise_for_status()" \
    2>/dev/null
}

check_backend_readiness() {
  local result
  result=$(docker exec hadha-backend \
    python -c "import httpx; r=httpx.get('http://localhost:8000/health/ready'); print(r.status_code)" \
    2>/dev/null) || return 1
  [[ "${result}" == "200" ]]
}

check_frontend_liveness() {
  docker exec hadha-frontend \
    curl -sf "http://localhost:3000" -o /dev/null \
    2>/dev/null
}

check_redis_liveness() {
  docker exec hadha-redis \
    redis-cli -a "${REDIS_PASSWORD:-}" ping 2>/dev/null | grep -q PONG
}

check_nginx_liveness() {
  docker exec hadha-nginx nginx -t 2>/dev/null
}

# ── Run all checks ─────────────────────────────────────────────────────────────
log "════ Health Checks: ${ENVIRONMENT} ════"

wait_for "Redis"              check_redis_liveness
wait_for "Backend (liveness)" check_backend_liveness
wait_for "Backend (readiness — DB + Redis)" check_backend_readiness
wait_for "Frontend"           check_frontend_liveness
wait_for "Nginx config"       check_nginx_liveness

# ── External HTTP check (after nginx is up) ───────────────────────────────────
log "External HTTP probe → ${APP_URL}"
for i in 1 2 3; do
  HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
    --max-time 15 --connect-timeout 5 "${APP_URL}" 2>/dev/null || echo "000")
  if [[ "${HTTP_STATUS}" =~ ^[23] ]]; then
    pass "External HTTP → ${HTTP_STATUS}"
    break
  fi
  [[ $i -eq 3 ]] && fail "External HTTP → ${HTTP_STATUS} (${APP_URL})" || \
    { log "  Retrying in 10s…"; sleep 10; }
done

# ── Backend API probe ─────────────────────────────────────────────────────────
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
