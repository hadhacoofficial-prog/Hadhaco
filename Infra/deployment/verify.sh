#!/usr/bin/env bash
# =============================================================================
# verify.sh — Post-deployment verification for Hadha.co
#
# Checks health of all containers and services.
# Exit code 0 = all checks passed, 1 = failures detected.
# =============================================================================

set -uo pipefail

APP_DIR="/opt/hadha"
LOG_FILE="${APP_DIR}/deploy.log"
REPORT_FILE="${APP_DIR}/backups/verify-$(date +'%Y%m%d-%H%M%S').md"
APP_URL="https://hadha.co"
API_URL="https://api.hadha.co"

PASS=0
FAIL=0
WARN=0
RESULTS=()

log() { echo "[$(date +'%H:%M:%S')] $*"; }

check_pass() {
  (( PASS++ ))
  RESULTS+=("| ✅ PASS | $1 | $2 |")
  log "  ✅ PASS: $1 — $2"
}

check_fail() {
  (( FAIL++ ))
  RESULTS+=("| ❌ FAIL | $1 | $2 |")
  log "  ❌ FAIL: $1 — $2"
}

check_warn() {
  (( WARN++ ))
  RESULTS+=("| ⚠️ WARN | $1 | $2 |")
  log "  ⚠️ WARN: $1 — $2"
}

# ── Container health checks ───────────────────────────────────────────────────
log "Checking container health..."

CONTAINERS=(
  "hadha-backend"
  "hadha-storefront"
  "hadha-admin"
  "hadha-redis"
  "hadha-nginx"
  "hadha-prometheus"
  "hadha-grafana"
  "hadha-loki"
  "hadha-promtail"
  "hadha-node-exporter"
  "hadha-cadvisor"
  "hadha-uptime-kuma"
  "hadha-glitchtip"
  "hadha-glitchtip-worker"
  "hadha-glitchtip-db"
  "hadha-redis-commander"
  "hadha-dozzle"
  "hadha-redis-exporter"
)

for container in "${CONTAINERS[@]}"; do
  STATUS=$(docker inspect --format='{{.State.Status}}' "${container}" 2>/dev/null || echo "not_found")
  HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no_healthcheck{{end}}' "${container}" 2>/dev/null || echo "not_found")

  if [[ "${STATUS}" == "running" ]]; then
    if [[ "${HEALTH}" == "healthy" ]] || [[ "${HEALTH}" == "no_healthcheck" ]]; then
      check_pass "${container}" "Running (${HEALTH})"
    elif [[ "${HEALTH}" == "starting" ]]; then
      check_warn "${container}" "Running but health check starting"
    else
      check_fail "${container}" "Running but ${HEALTH}"
    fi
  elif [[ "${STATUS}" == "not_found" ]]; then
    check_fail "${container}" "Container not found"
  else
    check_fail "${container}" "Status: ${STATUS}"
  fi
done

# ── CrashLoop / OOMKilled detection ──────────────────────────────────────────
log ""
log "Checking for CrashLoop / OOMKilled..."

for container in "${CONTAINERS[@]}"; do
  RESTARTS=$(docker inspect --format='{{.RestartCount}}' "${container}" 2>/dev/null || echo "0")
  if [[ "${RESTARTS}" -gt 5 ]]; then
    check_fail "${container}" "Restart count: ${RESTARTS} (possible CrashLoop)"
  elif [[ "${RESTARTS}" -gt 2 ]]; then
    check_warn "${container}" "Restart count: ${RESTARTS}"
  fi

  OOMKILLED=$(docker inspect --format='{{.State.OOMKilled}}' "${container}" 2>/dev/null || echo "false")
  if [[ "${OOMKILLED}" == "true" ]]; then
    check_fail "${container}" "OOMKilled detected"
  fi
done

# ── Redis connectivity ────────────────────────────────────────────────────────
log ""
log "Checking Redis..."

REDIS_PONG=$(docker exec hadha-redis redis-cli -a "${REDIS_PASSWORD:-}" --no-auth-warning ping 2>/dev/null || echo "FAIL")
if [[ "${REDIS_PONG}" == "PONG" ]]; then
  check_pass "Redis" "PONG"
else
  check_fail "Redis" "Ping failed"
fi

# ── Nginx config test ────────────────────────────────────────────────────────
log ""
log "Checking Nginx..."

NGINX_TEST=$(docker exec hadha-nginx nginx -t 2>&1 || echo "FAIL")
if echo "${NGINX_TEST}" | grep -q "successful"; then
  check_pass "Nginx config" "Syntax OK"
else
  check_fail "Nginx config" "Syntax error"
fi

# ── HTTP probes ────────────────────────────────────────────────────────────────
log ""
log "Running HTTP probes..."

declare -A HTTP_CHECKS=(
  ["Storefront"]="https://hadha.co"
  ["API"]="https://api.hadha.co/health/live"
  ["Admin"]="https://admin.hadha.co"
  ["Grafana"]="https://grafana.hadha.co/api/health"
  ["Prometheus"]="https://prometheus.hadha.co/-/healthy"
  ["Uptime Kuma"]="https://uptime.hadha.co"
  ["GlitchTip"]="https://errors.hadha.co/_health/"
  ["Redis Commander"]="https://redis.hadha.co"
  ["Dozzle"]="https://dozzle.hadha.co"
)

for name in "${!HTTP_CHECKS[@]}"; do
  url="${HTTP_CHECKS[$name]}"
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${url}" 2>/dev/null || echo "000")

  if [[ "${HTTP_CODE}" -ge 200 ]] && [[ "${HTTP_CODE}" -lt 400 ]]; then
    check_pass "${name}" "HTTP ${HTTP_CODE}"
  elif [[ "${HTTP_CODE}" == "000" ]]; then
    check_fail "${name}" "Connection failed (timeout or DNS)"
  elif [[ "${HTTP_CODE}" -ge 400 ]] && [[ "${HTTP_CODE}" -lt 500 ]]; then
    check_warn "${name}" "HTTP ${HTTP_CODE} (auth required?)"
  else
    check_fail "${name}" "HTTP ${HTTP_CODE}"
  fi
done

# ── Prometheus targets ────────────────────────────────────────────────────────
log ""
log "Checking Prometheus targets..."

PROM_TARGETS=$(curl -sf "http://localhost:9090/api/v1/targets" 2>/dev/null || echo '{"data":{"activeTargets":[]}}')
# If localhost doesn't work, try via docker
if echo "${PROM_TARGETS}" | grep -q '"activeTargets":\[\]'; then
  PROM_TARGETS=$(docker exec hadha-prometheus wget -qO- "http://localhost:9090/api/v1/targets" 2>/dev/null || echo '{"data":{"activeTargets":[]}}')
fi

UP_TARGETS=$(echo "${PROM_TARGETS}" | jq '[.data.activeTargets[] | select(.health == "up")] | length' 2>/dev/null || echo "0")
TOTAL_TARGETS=$(echo "${PROM_TARGETS}" | jq '[.data.activeTargets[]] | length' 2>/dev/null || echo "0")

if [[ "${TOTAL_TARGETS}" -gt 0 ]] && [[ "${UP_TARGETS}" -eq "${TOTAL_TARGETS}" ]]; then
  check_pass "Prometheus targets" "${UP_TARGETS}/${TOTAL_TARGETS} up"
elif [[ "${UP_TARGETS}" -gt 0 ]]; then
  check_warn "Prometheus targets" "${UP_TARGETS}/${TOTAL_TARGETS} up"
else
  check_fail "Prometheus targets" "0/${TOTAL_TARGETS} up"
fi

# ── Loki readiness ────────────────────────────────────────────────────────────
log ""
log "Checking Loki..."

LOKI_READY=$(curl -sf "http://localhost:3100/ready" 2>/dev/null || echo "FAIL")
if [[ "${LOKI_READY}" == "ready" ]]; then
  check_pass "Loki" "Ready"
else
  # Try via docker exec
  LOKI_READY=$(docker exec hadha-loki wget -qO- "http://localhost:3100/ready" 2>/dev/null || echo "FAIL")
  if [[ "${LOKI_READY}" == "ready" ]]; then
    check_pass "Loki" "Ready (via docker exec)"
  else
    check_fail "Loki" "Not ready"
  fi
fi

# ── Generate report ────────────────────────────────────────────────────────────
log ""
log "Generating verification report..."

mkdir -p "$(dirname "${REPORT_FILE}")"

cat > "${REPORT_FILE}" <<EOF
# Deployment Verification Report

**Date:** $(date -u +'%Y-%m-%dT%H:%M:%SZ')
**Tag:** ${IMAGE_TAG:-unknown}

## Summary

| Status | Count |
|--------|-------|
| ✅ Pass | ${PASS} |
| ❌ Fail | ${FAIL} |
| ⚠️ Warn | ${WARN} |

## Results

| Status | Service | Details |
|--------|---------|---------|
$(printf '%s\n' "${RESULTS[@]}")

## Verdict

$([ ${FAIL} -eq 0 ] && echo "✅ **DEPLOYMENT VERIFIED** — All critical checks passed." || echo "❌ **DEPLOYMENT FAILED** — ${FAIL} critical check(s) failed.")
EOF

log "Report written to: ${REPORT_FILE}"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Verification Summary"
echo "══════════════════════════════════════════"
echo "  ✅ Pass: ${PASS}"
echo "  ❌ Fail: ${FAIL}"
echo "  ⚠️ Warn: ${WARN}"
echo "══════════════════════════════════════════"

if [[ ${FAIL} -gt 0 ]]; then
  echo "  ❌ VERIFICATION FAILED"
  exit 1
else
  echo "  ✅ VERIFICATION PASSED"
  exit 0
fi
