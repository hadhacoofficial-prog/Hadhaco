#!/usr/bin/env bash
# =============================================================================
# smoke-tests.sh — Quick verification after deployment
#
# Runs fast HTTP checks against all services and generates a markdown report.
# =============================================================================

set -uo pipefail

REPORT_FILE="${1:-/opt/hadha/backups/smoke-$(date +'%Y%m%d-%H%M%S').md}"

PASS=0
FAIL=0
RESULTS=()

log() { echo "[$(date +'%H:%M:%S')] $*"; }

check() {
  local name="$1" url="$2" expected="${3:-200}"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${url}" 2>/dev/null || echo "000")
  if [[ "${code}" == "${expected}" ]] || [[ "${code}" -ge 200 && "${code}" -lt 400 ]]; then
    (( PASS++ ))
    RESULTS+=("| ✅ | ${name} | ${code} | ${url} |")
    log "  ✅ ${name}: HTTP ${code}"
  else
    (( FAIL++ ))
    RESULTS+=("| ❌ | ${name} | ${code} | ${url} |")
    log "  ❌ ${name}: HTTP ${code} (expected ${expected})"
  fi
}

log "Running smoke tests..."

# ── Application ───────────────────────────────────────────────────────────────
log ""
log "Application services:"
check "Storefront" "https://hadha.co"
check "API Health" "https://api.hadha.co/health/live"
check "Admin" "https://admin.hadha.co"

# ── Monitoring ────────────────────────────────────────────────────────────────
log ""
log "Monitoring services:"
check "Grafana" "https://grafana.hadha.co/api/health"
check "Prometheus" "https://prometheus.hadha.co/-/healthy"
check "Uptime Kuma" "https://uptime.hadha.co"
check "GlitchTip" "https://errors.hadha.co/_health/"

# ── Utilities ─────────────────────────────────────────────────────────────────
log ""
log "Utility services:"
check "Redis Commander" "https://redis.hadha.co"
check "Dozzle" "https://dozzle.hadha.co"

# ── Container checks ──────────────────────────────────────────────────────────
log ""
log "Container status:"
for c in hadha-backend hadha-storefront hadha-admin hadha-redis hadha-nginx \
         hadha-prometheus hadha-grafana hadha-loki hadha-promtail; do
  STATUS=$(docker inspect --format='{{.State.Status}}' "${c}" 2>/dev/null || echo "not_found")
  if [[ "${STATUS}" == "running" ]]; then
    (( PASS++ ))
    RESULTS+=("| ✅ | ${c} | running | container |")
  else
    (( FAIL++ ))
    RESULTS+=("| ❌ | ${c} | ${STATUS} | container |")
  fi
done

# ── Redis ─────────────────────────────────────────────────────────────────────
log ""
log "Redis connectivity:"
REDIS_PONG=$(docker exec hadha-redis redis-cli -a "${REDIS_PASSWORD:-}" --no-auth-warning ping 2>/dev/null || echo "FAIL")
if [[ "${REDIS_PONG}" == "PONG" ]]; then
  (( PASS++ ))
  RESULTS+=("| ✅ | Redis | PONG | redis |")
else
  (( FAIL++ ))
  RESULTS+=("| ❌ | Redis | FAIL | redis |")
fi

# ── SSL ───────────────────────────────────────────────────────────────────────
log ""
log "SSL certificate:"
SSL_EXPIRY=$(echo | openssl s_client -servername hadha.co -connect hadha.co:443 2>/dev/null | \
  openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "unknown")
if [[ "${SSL_EXPIRY}" != "unknown" ]]; then
  (( PASS++ ))
  RESULTS+=("| ✅ | SSL Certificate | Expires: ${SSL_EXPIRY} | ssl |")
else
  (( FAIL++ ))
  RESULTS+=("| ❌ | SSL Certificate | Could not verify | ssl |")
fi

# ── Generate report ────────────────────────────────────────────────────────────
mkdir -p "$(dirname "${REPORT_FILE}")"

cat > "${REPORT_FILE}" <<EOF
# Smoke Test Report

**Date:** $(date -u +'%Y-%m-%dT%H:%M:%SZ')

## Summary

- **Passed:** ${PASS}
- **Failed:** ${FAIL}
- **Total:** $(( PASS + FAIL ))

## Results

| Status | Service | Code | URL |
|--------|---------|------|-----|
$(printf '%s\n' "${RESULTS[@]}")

## Verdict

$([ ${FAIL} -eq 0 ] && echo "✅ All smoke tests passed." || echo "❌ ${FAIL} smoke test(s) failed.")
EOF

log ""
log "Report: ${REPORT_FILE}"
log "Result: ${PASS} passed, ${FAIL} failed"

[[ ${FAIL} -eq 0 ]] && exit 0 || exit 1
