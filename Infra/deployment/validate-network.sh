#!/usr/bin/env bash
# =============================================================================
# validate-network.sh — Pre-deployment network and dependency validation
#
# Verifies all network dependencies before deployment proceeds.
# Designed to run on the VPS before any containers are started.
#
# Exit code: 0 = all checks passed, 1 = critical failures detected.
# =============================================================================

set -uo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
DOMAIN="${DOMAIN:-hadha.co}"
APP_DIR="${APP_DIR:-/opt/hadha}"
ENV_FILE="${APP_DIR}/.env.production"
LOG_FILE="${APP_DIR}/deploy.log"

PASS=0
FAIL=0
WARN=0
CRITICAL=false

# ── Logging ───────────────────────────────────────────────────────────────────
log()    { echo "[$(date +'%H:%M:%S')] $*"; }
pass()   { (( PASS++ )); log "  ✅ $1"; }
fail()   { (( FAIL++ )); log "  ❌ $1"; CRITICAL=true; }
warn()   { (( WARN++ )); log "  ⚠️  $1"; }

section() { echo ""; echo "═══ $1 ═══"; }

# ── IPv4/IPv6 Detection ──────────────────────────────────────────────────────
detect_ip_support() {
  section "IPv4/IPv6 Support Detection"

  HAS_IPV4=false
  HAS_IPV6=false
  IPV4_ADDR=""
  IPV6_ADDR=" ""

  # Check IPv4
  if ip -4 addr show 2>/dev/null | grep -q 'inet '; then
    HAS_IPV4=true
    IPV4_ADDR=$(ip -4 addr show scope global 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)
    pass "IPv4 configured: ${IPV4_ADDR:-unknown}"
  else
    fail "No IPv4 address found on any interface"
  fi

  # Check IPv6
  if ip -6 addr show 2>/dev/null | grep -q 'inet6 '; then
    if ip -6 route show default 2>/dev/null | grep -q 'default'; then
      HAS_IPV6=true
      IPV6_ADDR=$(ip -6 addr show scope global 2>/dev/null | grep -oP 'inet6 \K[0-9a-f:]+' | head -1)
      pass "IPv6 configured with default route: ${IPV6_ADDR:-unknown}"

      # Test actual IPv6 connectivity
      if ping6 -c 1 -W 3 2001:4860:4860::8888 >/dev/null 2>&1 || \
         ping6 -c 1 -W 3 2606:4700:4700::1111 >/dev/null 2>&1; then
        pass "IPv6 internet connectivity confirmed"
      else
        warn "IPv6 configured but no internet connectivity — IPv6 will fail"
        HAS_IPV6=false
      fi
    else
      warn "IPv6 configured but no default route — IPv6 will fail"
    fi
  else
    log "  ℹ️  IPv6 not configured (this is fine if not needed)"
  fi

  # Determine preferred protocol
  if [[ "${HAS_IPV4}" == "true" ]] && [[ "${HAS_IPV6}" == "true" ]]; then
    IP_PROTOCOL="dual-stack"
    log "  Network: dual-stack (IPv4 + IPv6)"
  elif [[ "${HAS_IPV4}" == "true" ]]; then
    IP_PROTOCOL="ipv4-only"
    log "  Network: IPv4 only"
  else
    fail "No functional IP protocol available"
    IP_PROTOCOL="none"
  fi
}

# ── DNS Resolution ────────────────────────────────────────────────────────────
check_dns() {
  section "DNS Resolution"

  # Test DNS resolution for critical services
  local dns_targets=(
    "hadha.co"
    "api.hadha.co"
    "admin.hadha.co"
    "grafana.hadha.co"
    "errors.hadha.co"
  )

  for target in "${dns_targets[@]}"; do
    if getent hosts "${target}" >/dev/null 2>&1; then
      local ipv4_addr ipv6_addr
      ipv4_addr=$(getent ahostsv4 "${target}" 2>/dev/null | head -1 | awk '{print $1}')
      ipv6_addr=$(getent ahostsv6 "${target}" 2>/dev/null | head -1 | awk '{print $1}')

      local info=""
      [[ -n "${ipv4_addr}" ]] && info="A=${ipv4_addr}"
      [[ -n "${ipv6_addr}" ]] && info="${info} AAAA=${ipv6_addr}"
      pass "DNS ${target}: ${info:-resolved}"
    else
      fail "DNS resolution failed for ${target}"
    fi
  done

  # Test DNS for Supabase (from .env.production)
  if [[ -f "${ENV_FILE}" ]]; then
    local db_url
    db_url=$(grep -E '^DATABASE_URL=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-)
    if [[ -n "${db_url}" ]]; then
      # Extract hostname from DATABASE_URL: postgresql://user:pass@host:port/db
      local db_host
      db_host=$(echo "${db_url}" | sed -n 's|.*@\([^:/]*\).*|\1|p')
      if [[ -n "${db_host}" ]]; then
        if getent hosts "${db_host}" >/dev/null 2>&1; then
          local ipv4 ipv6
          ipv4=$(getent ahostsv4 "${db_host}" 2>/dev/null | head -1 | awk '{print $1}')
          ipv6=$(getent ahostsv6 "${db_host}" 2>/dev/null | head -1 | awk '{print $1}')
          pass "DNS database host ${db_host}: A=${ipv4:-none} AAAA=${ipv6:-none}"

          # If IPv6 resolves but we know it won't work, warn
          if [[ -n "${ipv6}" ]] && [[ "${HAS_IPV6}" != "true" ]]; then
            warn "Database host has AAAA record but IPv6 is not functional — will need IPv4 fallback"
          fi
        else
          fail "DNS resolution failed for database host: ${db_host}"
        fi
      fi
    fi
  fi
}

# ── Docker Network ────────────────────────────────────────────────────────────
check_docker() {
  section "Docker"

  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker not installed"
    return
  fi
  pass "Docker installed: $(docker --version 2>/dev/null | head -1)"

  if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon not running"
    return
  fi
  pass "Docker daemon running"

  if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose plugin not available"
    return
  fi
  pass "Docker Compose: $(docker compose version 2>/dev/null)"

  # Check hadha network
  if docker network inspect hadha >/dev/null 2>&1; then
    pass "Docker network 'hadha' exists"
  else
    warn "Docker network 'hadha' not found — will be created"
  fi

  # Check for container name conflicts
  local conflict_containers
  conflict_containers=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -E '^hadha-' | sort)
  if [[ -n "${conflict_containers}" ]]; then
    log "  Existing hadha containers:"
    echo "${conflict_containers}" | while read -r c; do
      local status
      status=$(docker inspect --format='{{.State.Status}}' "${c}" 2>/dev/null || echo "unknown")
      log "    ${c}: ${status}"
    done
  fi
}

# ── Database Connectivity ─────────────────────────────────────────────────────
check_database() {
  section "Database Connectivity (Supabase)"

  if [[ ! -f "${ENV_FILE}" ]]; then
    warn "No .env.production found — skipping database check"
    return
  fi

  # Source env file (safely)
  local db_url=""
  local alembic_url=""
  while IFS='=' read -r key value; do
    case "${key}" in
      DATABASE_URL=*) db_url="${value}" ;;
      ALEMBIC_DATABASE_URL=*) alembic_url="${value}" ;;
    esac
  done < <(grep -E '^(DATABASE_URL|ALEMBIC_DATABASE_URL)=' "${ENV_FILE}" 2>/dev/null)

  if [[ -z "${db_url}" ]]; then
    warn "DATABASE_URL not set in .env.production"
    return
  fi

  # Extract connection details
  local db_host db_port db_name db_user
  db_host=$(echo "${db_url}" | sed -n 's|.*@\([^:/]*\).*|\1|p')
  db_port=$(echo "${db_url}" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
  db_name=$(echo "${db_url}" | sed -n 's|.*/\([^?]*\).*|\1|p')
  db_user=$(echo "${db_url}" | sed -n 's|://\([^:]*\):.*|\1|p')

  [[ -z "${db_port}" ]] && db_port=5432

  log "  Host: ${db_host}"
  log "  Port: ${db_port}"
  log "  Database: ${db_name}"
  log "  User: ${db_user}"

  # Test TCP connectivity (this is the critical test)
  local tcp_ok=false

  # Try IPv4 first (most reliable)
  if command -v nc >/dev/null 2>&1; then
    if nc -4 -zw5 "${db_host}" "${db_port}" 2>/dev/null; then
      tcp_ok=true
      pass "TCP connectivity (IPv4) to ${db_host}:${db_port}"
    fi
  fi

  if [[ "${tcp_ok}" != "true" ]] && command -v bash >/dev/null 2>&1; then
    # Bash /dev/tcp fallback
    if (echo >/dev/tcp/"${db_host}"/"${db_port}") 2>/dev/null; then
      tcp_ok=true
      pass "TCP connectivity (bash) to ${db_host}:${db_port}"
    fi
  fi

  if [[ "${tcp_ok}" != "true" ]] && command -v timeout >/dev/null 2>&1; then
    # timeout + nc fallback
    if timeout 5 nc -zw5 "${db_host}" "${db_port}" 2>/dev/null; then
      tcp_ok=true
      pass "TCP connectivity (timeout+nc) to ${db_host}:${db_port}"
    fi
  fi

  if [[ "${tcp_ok}" != "true" ]]; then
    # Try curl as last resort
    if curl -sf --max-time 5 "http://${db_host}:${db_port}" 2>/dev/null; then
      tcp_ok=true
      pass "TCP connectivity (curl) to ${db_host}:${db_port}"
    fi
  fi

  if [[ "${tcp_ok}" != "true" ]]; then
    fail "Cannot reach database at ${db_host}:${db_port} via TCP"
    log "  This likely means IPv6 AAAA record is returned but IPv6 is not functional"
    log "  Solution: Set DATABASE_URL to use IPv4 directly, or disable IPv6 on the VPS"
  fi

  # Test PostgreSQL connectivity (if psql is available)
  if [[ "${tcp_ok}" == "true" ]] && command -v docker >/dev/null 2>&1; then
    local pg_test
    pg_test=$(docker run --rm --network hadha postgres:16-alpine \
      pg_isready -h "${db_host}" -p "${db_port}" -U "${db_user}" -d "${db_name}" 2>&1 || echo "FAIL")
    if echo "${pg_test}" | grep -q "accepting connections"; then
      pass "PostgreSQL server accepting connections"
    else
      warn "PostgreSQL connectivity test inconclusive: ${pg_test}"
    fi
  fi
}

# ── External Services ─────────────────────────────────────────────────────────
check_external_services() {
  section "External Services"

  # GitHub Container Registry
  if curl -sf --max-time 10 "https://ghcr.io/v2/" -o /dev/null 2>/dev/null; then
    pass "GitHub Container Registry (ghcr.io)"
  else
    fail "Cannot reach GitHub Container Registry"
  fi

  # Resend (email)
  if curl -sf --max-time 10 "https://api.resend.com/" -o /dev/null 2>/dev/null; then
    pass "Resend API (api.resend.com)"
  else
    warn "Cannot reach Resend API — email notifications will fail"
  fi

  # Supabase API
  if [[ -f "${ENV_FILE}" ]]; then
    local supabase_url
    supabase_url=$(grep -E '^SUPABASE_URL=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-)
    if [[ -n "${supabase_url}" ]]; then
      if curl -sf --max-time 10 "${supabase_url}/rest/v1/" -o /dev/null 2>/dev/null; then
        pass "Supabase API (${supabase_url})"
      else
        warn "Cannot reach Supabase API — auth/storage may fail"
      fi
    fi
  fi

  # Cloudflare R2
  if [[ -f "${ENV_FILE}" ]]; then
    local r2_endpoint
    r2_endpoint=$(grep -E '^CLOUDFLARE_R2_ENDPOINT=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-)
    if [[ -n "${r2_endpoint}" ]]; then
      if curl -sf --max-time 10 "${r2_endpoint}" -o /dev/null 2>/dev/null; then
        pass "Cloudflare R2 (${r2_endpoint})"
      else
        warn "Cannot reach Cloudflare R2 — file uploads may fail"
      fi
    fi
  fi
}

# ── SSL Certificates ──────────────────────────────────────────────────────────
check_ssl() {
  section "SSL Certificates"

  if [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
    local cert_file="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
    if [[ -f "${cert_file}" ]]; then
      local expiry
      expiry=$(openssl x509 -enddate -noout -in "${cert_file}" 2>/dev/null | cut -d= -f2)
      if [[ -n "${expiry}" ]]; then
        local expiry_epoch now_epoch days_left
        expiry_epoch=$(date -d "${expiry}" +%s 2>/dev/null || echo "0")
        now_epoch=$(date +%s)
        days_left=$(( (expiry_epoch - now_epoch) / 86400 ))

        if [[ "${days_left}" -gt 30 ]]; then
          pass "SSL certificate valid for ${days_left} more days"
        elif [[ "${days_left}" -gt 0 ]]; then
          warn "SSL certificate expires in ${days_left} days — renew soon"
        else
          fail "SSL certificate has EXPIRED"
        fi
      fi
    fi
  else
    warn "No SSL certificates found at /etc/letsencrypt/live/${DOMAIN}"
  fi
}

# ── Disk Space ────────────────────────────────────────────────────────────────
check_disk() {
  section "Disk Space"

  local avail_kb
  avail_kb=$(df -k / | tail -1 | awk '{print $4}')
  local avail_gb=$(( avail_kb / 1024 / 1024 ))

  if [[ "${avail_gb}" -gt 10 ]]; then
    pass "Available disk space: ${avail_gb}GB"
  elif [[ "${avail_gb}" -gt 5 ]]; then
    warn "Low disk space: ${avail_gb}GB (recommend >10GB)"
  else
    fail "Critically low disk space: ${avail_gb}GB (need >5GB minimum)"
  fi
}

# ── IPv4-Only Database URL Generation ─────────────────────────────────────────
generate_ipv4_url() {
  section "IPv4 Database URL Fallback"

  if [[ ! -f "${ENV_FILE}" ]]; then
    return
  fi

  local db_url
  db_url=$(grep -E '^DATABASE_URL=' "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-)

  if [[ -z "${db_url}" ]]; then
    return
  fi

  # Check if already using IPv4 (by IP address)
  local db_host
  db_host=$(echo "${db_url}" | sed -n 's|.*@\([^:/]*\).*|\1|p')

  if [[ -z "${db_host}" ]]; then
    return
  fi

  # If hostname doesn't look like an IP, check if IPv4 is available
  if [[ ! "${db_host}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    local ipv4
    ipv4=$(getent ahostsv4 "${db_host}" 2>/dev/null | head -1 | awk '{print $1}')

    if [[ -n "${ipv4}" ]]; then
      log "  Database hostname: ${db_host}"
      log "  IPv4 address: ${ipv4}"
      log ""
      log "  If IPv6 connectivity fails, replace DATABASE_URL in .env.production with:"
      log "  ${db_url//${db_host}/${ipv4}}"
      log ""
      log "  Or add to /etc/gai.conf:"
      log "  precedence ::ffff:0:0/96  100"
      log ""
    fi
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  Hadha.co — Pre-Deployment Network Validation              ║"
  echo "║  $(date +'%Y-%m-%d %H:%M:%S %Z')                              ║"
  echo "╚══════════════════════════════════════════════════════════════╝"

  detect_ip_support
  check_dns
  check_docker
  check_database
  check_external_services
  check_ssl
  check_disk
  generate_ipv4_url

  # ── Summary ──────────────────────────────────────────────────────────────
  echo ""
  echo "══════════════════════════════════════════════════════════════"
  echo "  Validation Summary"
  echo "══════════════════════════════════════════════════════════════"
  echo "  ✅ Pass:  ${PASS}"
  echo "  ❌ Fail:  ${FAIL}"
  echo "  ⚠️  Warn:  ${WARN}"
  echo "══════════════════════════════════════════════════════════════"

  if [[ "${CRITICAL}" == "true" ]]; then
    echo "  ❌ VALIDATION FAILED — deployment should NOT proceed"
    echo ""
    echo "  Fix the issues above and re-run this script."
    echo "  Do NOT deploy until all critical checks pass."
    echo "══════════════════════════════════════════════════════════════"
    return 1
  elif [[ "${FAIL}" -gt 0 ]]; then
    echo "  ⚠️  VALIDATION PASSED WITH WARNINGS — review above"
    echo "══════════════════════════════════════════════════════════════"
    return 0
  else
    echo "  ✅ ALL CHECKS PASSED — deployment may proceed"
    echo "══════════════════════════════════════════════════════════════"
    return 0
  fi
}

main "$@"
