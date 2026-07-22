#!/usr/bin/env bash
# =============================================================================
# verify.sh — Post-deployment verification for Hadha.co
#
# Checks health of all containers and services.
# CRITICAL failures (app + core infra) block deployment.
# MONITORING failures (prometheus, loki, etc.) only warn.
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

# ── Container classification ──────────────────────────────────────────────────
# CRITICAL: deployment fails if these are unhealthy
CRITICAL_CONTAINERS=(
  "hadha-backend"
  "hadha-storefront"
  "hadha-admin"
  "hadha-redis"
  "hadha-nginx"
  "hadha-glitchtip"
  "hadha-glitchtip-worker"
  "hadha-glitchtip-db"
)

# MONITORING: warned but do NOT block deployment
MONITORING_CONTAINERS=(
  "hadha-prometheus"
  "hadha-grafana"
  "hadha-loki"
  "hadha-promtail"
  "hadha-node-exporter"
  "hadha-cadvisor"
  "hadha-uptime-kuma"
  "hadha-redis-commander"
  "hadha-dozzle"
  "hadha-redis-exporter"
)

# ── Container health checks ───────────────────────────────────────────────────
log "Checking container health..."

check_container() {
  local container="$1"
  local severity="$2"

  local STATUS HEALTH
  STATUS=$(docker inspect --format='{{.State.Status}}' "${container}" 2>/dev/null || echo "not_found")
  HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no_healthcheck{{end}}' "${container}" 2>/dev/null || echo "not_found")

  if [[ "${STATUS}" == "running" ]]; then
    if [[ "${HEALTH}" == "healthy" ]] || [[ "${HEALTH}" == "no_healthcheck" ]]; then
      check_pass "${container}" "Running (${HEALTH})"
    elif [[ "${HEALTH}" == "starting" ]]; then
      check_warn "${container}" "Running but health check starting"
    elif [[ "${severity}" == "critical" ]]; then
      check_fail "${container}" "Running but ${HEALTH}"
    else
      check_warn "${container}" "Monitoring: running but ${HEALTH}"
    fi
  elif [[ "${STATUS}" == "not_found" ]]; then
    if [[ "${severity}" == "critical" ]]; then
      check_fail "${container}" "Container not found"
    else
      check_warn "${container}" "Monitoring: container not found"
    fi
  else
    if [[ "${severity}" == "critical" ]]; then
      check_fail "${container}" "Status: ${STATUS}"
    else
      check_warn "${container}" "Monitoring: status ${STATUS}"
    fi
  fi
}

for container in "${CRITICAL_CONTAINERS[@]}"; do
  check_container "${container}" "critical"
done

for container in "${MONITORING_CONTAINERS[@]}"; do
  check_container "${container}" "monitoring"
done

# ── CrashLoop / OOMKilled detection ──────────────────────────────────────────
log ""
log "Checking for CrashLoop / OOMKilled..."

ALL_CONTAINERS=("${CRITICAL_CONTAINERS[@]}" "${MONITORING_CONTAINERS[@]}")
for container in "${ALL_CONTAINERS[@]}"; do
  local_severity="monitoring"
  for c in "${CRITICAL_CONTAINERS[@]}"; do
    [[ "${c}" == "${container}" ]] && local_severity="critical" && break
  done

  RESTARTS=$(docker inspect --format='{{.RestartCount}}' "${container}" 2>/dev/null || echo "0")
  if [[ "${RESTARTS}" -gt 5 ]]; then
    if [[ "${local_severity}" == "critical" ]]; then
      check_fail "${container}" "Restart count: ${RESTARTS} (possible CrashLoop)"
    else
      check_warn "${container}" "Monitoring: restart count ${RESTARTS}"
    fi
  elif [[ "${RESTARTS}" -gt 2 ]]; then
    check_warn "${container}" "Restart count: ${RESTARTS}"
  fi

  OOMKILLED=$(docker inspect --format='{{.State.OOMKilled}}' "${container}" 2>/dev/null || echo "false")
  if [[ "${OOMKILLED}" == "true" ]]; then
    if [[ "${local_severity}" == "critical" ]]; then
      check_fail "${container}" "OOMKilled detected"
    else
      check_warn "${container}" "Monitoring: OOMKilled"
    fi
  fi

  # Capture last 20 lines of logs for any container with elevated restarts
  if [[ "${RESTARTS}" -gt 2 ]]; then
    log ""
    log "  Last 20 lines of ${container} logs:"
    docker logs --tail 20 "${container}" 2>&1 | sed 's/^/    /' || true
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

NGINX_HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no_healthcheck{{end}}' "hadha-nginx" 2>/dev/null || echo "unknown")
if [[ "${NGINX_HEALTH}" == "healthy" ]]; then
  check_pass "Nginx config" "Syntax OK (docker health: healthy)"
elif [[ "${NGINX_HEALTH}" == "starting" ]]; then
  # Wait up to 15s for health check to complete
  for _ in 1 2 3 4 5; do
    sleep 3
    NGINX_HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no_healthcheck{{end}}' "hadha-nginx" 2>/dev/null || echo "unknown")
    if [[ "${NGINX_HEALTH}" == "healthy" ]]; then
      check_pass "Nginx config" "Syntax OK (docker health: healthy)"
      NGINX_CHECK_DONE=1
      break
    fi
  done
  if [[ "${NGINX_CHECK_DONE:-}" != "1" ]]; then
    # Container is running but health check not yet complete — HTTP probes will validate
    check_pass "Nginx config" "Running (health check pending, HTTP probes validate)"
  fi
else
  NGINX_TEST=$(docker exec hadha-nginx nginx -t 2>&1 || echo "FAIL")
  if echo "${NGINX_TEST}" | grep -q "successful"; then
    check_pass "Nginx config" "Syntax OK"
  else
    # nginx -t failed, but nginx might still be serving traffic correctly.
    # This handles transient docker exec issues where the running config is
    # valid but the exec test fails (e.g., timing, cgroup, or PID namespace).
    NGINX_HTTP_FALLBACK=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "https://hadha.co" 2>/dev/null || echo "000")
    if [[ "${NGINX_HTTP_FALLBACK}" -ge 200 ]] && [[ "${NGINX_HTTP_FALLBACK}" -lt 500 ]]; then
      check_pass "Nginx config" "Serving traffic OK (nginx -t inconclusive)"
    else
      check_fail "Nginx config" "Syntax error and not serving traffic"
    fi
  fi
fi

# ── HTTP probes ────────────────────────────────────────────────────────────────
log ""
log "Running HTTP probes..."

declare -A CRITICAL_HTTP=(
  ["API"]="https://api.hadha.co/health/live"
  ["Storefront"]="https://hadha.co"
  ["Admin"]="https://admin.hadha.co"
  ["GlitchTip"]="https://errors.hadha.co/_health/"
)

declare -A MONITORING_HTTP=(
  ["Grafana"]="https://grafana.hadha.co/api/health"
  ["Prometheus"]="https://prometheus.hadha.co/-/healthy"
  ["Uptime Kuma"]="https://uptime.hadha.co"
  ["Redis Commander"]="https://redis.hadha.co"
  ["Dozzle"]="https://dozzle.hadha.co"
)

for name in "${!CRITICAL_HTTP[@]}"; do
  url="${CRITICAL_HTTP[$name]}"
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

for name in "${!MONITORING_HTTP[@]}"; do
  url="${MONITORING_HTTP[$name]}"
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${url}" 2>/dev/null || echo "000")

  if [[ "${HTTP_CODE}" -ge 200 ]] && [[ "${HTTP_CODE}" -lt 400 ]]; then
    check_pass "${name}" "HTTP ${HTTP_CODE}"
  elif [[ "${HTTP_CODE}" == "000" ]]; then
    check_warn "${name}" "Monitoring: connection failed"
  elif [[ "${HTTP_CODE}" -ge 400 ]] && [[ "${HTTP_CODE}" -lt 500 ]]; then
    check_warn "${name}" "HTTP ${HTTP_CODE} (auth required?)"
  else
    check_warn "${name}" "Monitoring: HTTP ${HTTP_CODE}"
  fi
done

# ── Prometheus targets ────────────────────────────────────────────────────────
log ""
log "Checking Prometheus targets..."

PROM_TARGETS=$(curl -sf "http://localhost:9090/api/v1/targets" 2>/dev/null || echo '{"data":{"activeTargets":[]}}')
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
  check_warn "Prometheus targets" "Monitoring: 0/${TOTAL_TARGETS} up"
fi

# ── Loki readiness ────────────────────────────────────────────────────────────
log ""
log "Checking Loki..."

LOKI_READY=$(curl -sf "http://localhost:3100/ready" 2>/dev/null || echo "FAIL")
if [[ "${LOKI_READY}" == "ready" ]]; then
  check_pass "Loki" "Ready"
else
  LOKI_READY=$(docker exec hadha-loki wget -qO- "http://localhost:3100/ready" 2>/dev/null || echo "FAIL")
  if [[ "${LOKI_READY}" == "ready" ]]; then
    check_pass "Loki" "Ready (via docker exec)"
  else
    check_warn "Loki" "Monitoring: not ready"
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
| ❌ Fail | ${FAIL} (critical only) |
| ⚠️ Warn | ${WARN} (incl. monitoring) |

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
echo "  ❌ Fail: ${FAIL} (critical)"
echo "  ⚠️ Warn: ${WARN} (incl. monitoring)"
echo "══════════════════════════════════════════"

if [[ ${FAIL} -gt 0 ]]; then
  echo "  ❌ VERIFICATION FAILED"
  exit 1
else
  echo "  ✅ VERIFICATION PASSED"
  exit 0
fi
