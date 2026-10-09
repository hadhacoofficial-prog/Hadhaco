#!/usr/bin/env bash
# =============================================================================
# Hadha — Cloudflare Authenticated Origin Pulls (mTLS) toggle
#
# Usage (on the VPS, as root or a docker-capable user):
#   origin-pull.sh status
#   origin-pull.sh enable  --yes     # only Cloudflare can reach :443
#   origin-pull.sh disable           # instant rollback
#
# PRE-REQUISITE (Cloudflare dashboard): SSL/TLS -> Origin Server ->
# "Authenticated Origin Pulls" = ON for the hadha.co zone. Enabling here first
# makes every request fail with HTTP 400 until Cloudflare presents its cert.
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/hadha}"
DIR="${APP_DIR}/nginx/origin-pull"
CA="${DIR}/cloudflare-origin-pull-ca.pem"
CONF="${DIR}/enforce.conf"
NGINX="hadha-nginx"

die() { echo "ERROR: $*" >&2; exit 1; }

reload_checked() {
  docker exec "${NGINX}" nginx -t >/dev/null 2>&1 || return 1
  docker kill -s HUP "${NGINX}" >/dev/null
}

case "${1:-status}" in
  status)
    if [[ -f "${CONF}" ]]; then echo "origin-pull: ENFORCED"; else echo "origin-pull: off"; fi
    [[ -f "${CA}" ]] && echo "CA present: ${CA}" || echo "CA missing: ${CA} (run a deploy first)"
    ;;
  enable)
    [[ "${2:-}" == "--yes" ]] || die "refusing without --yes. Enable 'Authenticated Origin Pulls' in Cloudflare first."
    [[ -f "${CA}" ]] || die "CA not found at ${CA} (run a deploy first)"
    openssl x509 -in "${CA}" -noout -subject | grep -q "origin-pull.cloudflare.net" \
      || die "${CA} is not the Cloudflare origin-pull CA"
    cat > "${CONF}" <<'CONF'
# Managed by deployment/origin-pull.sh — remove with: origin-pull.sh disable
ssl_client_certificate /etc/nginx/origin-pull/cloudflare-origin-pull-ca.pem;
ssl_verify_client on;
CONF
    if reload_checked; then
      echo "origin-pull: ENFORCED (rollback: origin-pull.sh disable)"
    else
      rm -f "${CONF}"
      die "nginx config test failed; enforcement not applied"
    fi
    ;;
  disable)
    rm -f "${CONF}"
    reload_checked || die "nginx reload failed after removing ${CONF}"
    echo "origin-pull: off"
    ;;
  *) die "usage: $0 {status|enable --yes|disable}" ;;
esac
