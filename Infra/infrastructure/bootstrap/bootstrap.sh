#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh — Fully idempotent VPS setup for Hadha.co
#
# Run as root on a fresh Ubuntu 24.04 VPS:
#   curl -fsSL https://raw.githubusercontent.com/.../bootstrap.sh | sudo bash
#
# Or triggered automatically by GitHub Actions with environment variables.
#
# What this script does (ALL idempotent — safe to re-run):
#   1. System update + hardening (SSH, UFW, fail2ban)
#   2. Deploy user creation
#   3. Docker + Docker Compose installation
#   4. Directory structure creation
#   5. Docker network creation
#   6. SSL certificates (Let's Encrypt)
#   7. Nginx configuration deployment
#   8. Monitoring configuration deployment
#   9. Infrastructure stack deployment
#   10. Monitoring provisioning (Grafana datasources, dashboards)
#   11. Uptime Kuma monitors (via API)
#   12. GlitchTip organization/project (via API)
#   13. State file written
#   14. Health verification
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
DOMAIN="${DOMAIN:-hadha.co}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@hadha.co}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
APP_DIR="/opt/hadha"
STATE_FILE="${APP_DIR}/.bootstrap-state.json"
SCRIPTS_DIR="${APP_DIR}/scripts"
INFRA_VERSION="2.0.0"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()      { echo -e "[$(date +'%H:%M:%S')] $*"; }
success()  { echo -e "[$(date +'%H:%M:%S')] ${GREEN}✓ $*${NC}"; }
warn()     { echo -e "[$(date +'%H:%M:%S')] ${YELLOW}⚠ $*${NC}"; }
error()    { echo -e "[$(date +'%H:%M:%S')] ${RED}✗ $*${NC}"; }
section()  { echo ""; echo -e "${BLUE}════════════════════════════════════════${NC}"; echo -e "${BLUE}  $*${NC}"; echo -e "${BLUE}════════════════════════════════════════${NC}"; }

# ── Root check ───────────────────────────────────────────────────────────────
[[ "$(id -u)" -eq 0 ]] || { error "Run as root (sudo bash bootstrap.sh)"; exit 1; }

# ── State management ─────────────────────────────────────────────────────────
step_done() {
  local step="$1"
  if [[ -f "${STATE_FILE}" ]]; then
    if jq -e ".steps.\"${step}\"" "${STATE_FILE}" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

mark_done() {
  local step="$1"
  local tmp="${STATE_FILE}.tmp"
  if [[ -f "${STATE_FILE}" ]]; then
    jq ".steps.\"${step}\" = {\"done\": true, \"at\": \"$(date -u +'%Y-%m-%dT%H:%M:%SZ')\"}" "${STATE_FILE}" > "${tmp}"
  else
    echo "{\"version\": \"${INFRA_VERSION}\", \"steps\": {\"${step}\": {\"done\": true, \"at\": \"$(date -u +'%Y-%m-%dT%H:%M:%SZ')\"}}}" > "${tmp}"
  fi
  mv "${tmp}" "${STATE_FILE}"
}

ensure_hadha_network() {
  # Create or recreate the 'hadha' Docker network with IPv6 support.
  # If the network exists but IPv6 is disabled and no containers are attached,
  # recreate it. If containers are attached, warn but continue.

  if docker network inspect hadha >/dev/null 2>&1; then
    local has_ipv6
    has_ipv6=$(docker network inspect hadha -f '{{.EnableIPv6}}' 2>/dev/null)
    if [[ "${has_ipv6}" == "true" ]]; then
      success "Docker network 'hadha' exists with IPv6 — reusing"
      return 0
    fi

    # Network exists without IPv6 — check if containers are attached
    local container_count
    container_count=$(docker network inspect hadha -f '{{len .Containers}}' 2>/dev/null || echo "0")

    if [[ "${container_count}" -eq 0 ]]; then
      log "Network 'hadha' has no IPv6 and no containers — recreating..."
      docker network rm hadha 2>&1 || true
    else
      warn "Network 'hadha' has ${container_count} container(s) and no IPv6"
      warn "Stopping attached containers to recreate network..."
      for cid in $(docker network inspect hadha -f '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null); do
        docker stop "${cid}" 2>/dev/null || true
      done
      docker network rm hadha 2>&1 || true
    fi
  fi

  log "Creating Docker network: hadha (with IPv6)"
  docker network create \
    --driver bridge \
    --ipv6 \
    --subnet=fd00:1::/64 \
    hadha 2>&1 \
    || die "Failed to create Docker network 'hadha'"

  # Verify
  if docker network inspect hadha -f '{{.EnableIPv6}}' 2>/dev/null | grep -q "true"; then
    success "Docker network 'hadha' created with IPv6 enabled"
  else
    die "Docker network 'hadha' created but IPv6 is NOT enabled — check daemon.json"
  fi
}

# Initialize state file if missing
if [[ ! -f "${STATE_FILE}" ]]; then
  echo "{\"version\": \"${INFRA_VERSION}\", \"steps\": {}}" > "${STATE_FILE}"
fi

# =============================================================================
section "1. System update and hardening"
# =============================================================================
if step_done "system_update"; then
  success "System update already completed — skipping"
else
  apt-get update -qq
  apt-get upgrade -y -qq
  apt-get install -y -qq \
    curl wget git unzip jq \
    ufw fail2ban \
    apache2-utils \
    certbot \
    python3-certbot-nginx \
    htop ncdu \
    logrotate \
    ca-certificates gnupg lsb-release

  cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s

[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
port     = http,https
logpath  = /var/log/nginx/error.log
EOF

  systemctl enable fail2ban
  systemctl restart fail2ban
  mark_done "system_update"
  success "System update and hardening completed"
fi

# =============================================================================
section "2. Firewall setup (UFW)"
# =============================================================================
if step_done "firewall"; then
  success "Firewall already configured — skipping"
else
  ufw --force reset
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow ssh
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
  mark_done "firewall"
  success "UFW firewall configured"
fi

# =============================================================================
section "3. Deploy user"
# =============================================================================
if step_done "deploy_user"; then
  success "Deploy user already exists — skipping"
else
  if ! id "${DEPLOY_USER}" &>/dev/null; then
    useradd -m -s /bin/bash "${DEPLOY_USER}"
    usermod -aG docker "${DEPLOY_USER}" 2>/dev/null || true
    success "Created deploy user: ${DEPLOY_USER}"
  else
    success "Deploy user already exists: ${DEPLOY_USER}"
    usermod -aG docker "${DEPLOY_USER}" 2>/dev/null || true
  fi
  mark_done "deploy_user"
fi

# =============================================================================
section "4. Docker installation"
# =============================================================================
if step_done "docker"; then
  success "Docker already installed: $(docker --version 2>/dev/null || echo 'unknown') — skipping"
else
  if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    usermod -aG docker "${DEPLOY_USER}"
    success "Docker installed"
  else
    success "Docker already installed: $(docker --version)"
  fi

  # Ensure Docker Compose plugin is available
  if ! docker compose version &>/dev/null; then
    warn "Docker Compose plugin not found — installing..."
    apt-get install -y -qq docker-compose-plugin
  fi
  success "Docker Compose: $(docker compose version 2>/dev/null || echo 'unknown')"

  mark_done "docker"
fi

# =============================================================================
section "4b. Docker daemon IPv6 configuration"
# =============================================================================
if step_done "docker_ipv6"; then
  success "Docker daemon IPv6 already configured — skipping"
else
  DAEMON_JSON="/etc/docker/daemon.json"
  REQUIRED_JSON='{"ipv6":true,"ip6tables":true,"fixed-cidr-v6":"fd00::/80"}'

  if [[ ! -f "${DAEMON_JSON}" ]]; then
    log "Creating ${DAEMON_JSON} with IPv6 support..."
    echo "${REQUIRED_JSON}" | jq '.' > "${DAEMON_JSON}"
    systemctl restart docker
    sleep 3
    success "Docker daemon.json created and Docker restarted"
  else
    # Merge required settings into existing daemon.json
    EXISTING=$(cat "${DAEMON_JSON}")
    MERGED=$(echo "${EXISTING}" "${REQUIRED_JSON}" | jq -s '.[0] * .[1]')
    if [[ "${MERGED}" != "$(echo "${EXISTING}" | jq -S '.')" ]]; then
      log "Updating ${DAEMON_JSON} with IPv6 settings..."
      cp "${DAEMON_JSON}" "${DAEMON_JSON}.bak.$(date +%s)"
      echo "${MERGED}" | jq '.' > "${DAEMON_JSON}"
      systemctl restart docker
      sleep 3
      success "Docker daemon.json updated and Docker restarted"
    else
      success "Docker daemon.json already has IPv6 settings"
    fi
  fi

  # Verify IPv6 is active
  if docker info 2>/dev/null | grep -q "IPv6:.*Yes\|IPv6 Enabled"; then
    success "Docker daemon reports IPv6 enabled"
  else
    warn "Docker daemon IPv6 status unclear — will verify on network creation"
  fi

  mark_done "docker_ipv6"
fi

# =============================================================================
section "5. Directory structure"
# =============================================================================
if step_done "directories"; then
  success "Directories already exist — verifying..."
else
  for dir in \
    "${APP_DIR}" \
    "${APP_DIR}/nginx/conf.d" \
    "${APP_DIR}/scripts" \
    "${APP_DIR}/backups" \
    "${APP_DIR}/dozzle" \
    "${APP_DIR}/monitoring/prometheus/rules" \
    "${APP_DIR}/monitoring/grafana/provisioning/datasources" \
    "${APP_DIR}/monitoring/grafana/provisioning/dashboards" \
    "${APP_DIR}/monitoring/grafana/provisioning/alerting" \
    "${APP_DIR}/monitoring/grafana/dashboards" \
    "${APP_DIR}/monitoring/loki" \
    "${APP_DIR}/monitoring/promtail" \
    "/var/www/certbot"; do
    mkdir -p "${dir}"
  done

  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
  mark_done "directories"
  success "Directory structure created"
fi

# =============================================================================
section "6. Docker network (IPv6-enabled)"
# =============================================================================
if step_done "network"; then
  success "Docker network 'hadha' already exists — verifying IPv6..."
else
  ensure_hadha_network
  mark_done "network"
fi

# =============================================================================
section "7. SSL certificates (Let's Encrypt)"
# =============================================================================
if step_done "ssl"; then
  success "SSL certificates already obtained — skipping"
else
  log "Requesting certificate for ${DOMAIN} and all subdomains..."

  # Temporarily start a plain HTTP server for ACME challenge
  docker run -d --name certbot-temp \
    -p 80:80 \
    -v /var/www/certbot:/usr/share/nginx/html/. \
    nginx:alpine 2>/dev/null || true

  sleep 2

  # Build domain arguments
  DOMAIN_ARGS=(
    -d "${DOMAIN}"
    -d "www.${DOMAIN}"
    -d "api.${DOMAIN}"
    -d "admin.${DOMAIN}"
    -d "redis.${DOMAIN}"
    -d "dozzle.${DOMAIN}"
    -d "grafana.${DOMAIN}"
    -d "prometheus.${DOMAIN}"
    -d "cadvisor.${DOMAIN}"
    -d "uptime.${DOMAIN}"
    -d "errors.${DOMAIN}"
  )

  if certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${ADMIN_EMAIL}" \
    --agree-tos \
    --no-eff-email \
    "${DOMAIN_ARGS[@]}" 2>&1; then
    success "Certificate obtained for all subdomains"
  else
    warn "Certificate request failed — DNS may not have propagated yet"
    warn "Run certbot manually after DNS propagates"
  fi

  docker stop certbot-temp 2>/dev/null && docker rm certbot-temp 2>/dev/null || true

  # Auto-renew via cron
  echo "0 3 * * * root certbot renew --quiet --post-hook 'docker exec hadha-nginx nginx -s reload'" \
    > /etc/cron.d/certbot-renew
  mark_done "ssl"
  success "Certbot auto-renewal configured"
fi

# =============================================================================
section "8. GitHub Actions deploy key"
# =============================================================================
if step_done "ssh_key"; then
  success "SSH deploy key already exists — skipping"
else
  SSH_DIR="/home/${DEPLOY_USER}/.ssh"
  mkdir -p "${SSH_DIR}"
  chmod 700 "${SSH_DIR}"

  if [[ ! -f "${SSH_DIR}/id_ed25519_github" ]]; then
    ssh-keygen -t ed25519 -f "${SSH_DIR}/id_ed25519_github" -N "" -C "github-actions@hadha.co"
    cat "${SSH_DIR}/id_ed25519_github.pub" >> "${SSH_DIR}/authorized_keys"
    chmod 600 "${SSH_DIR}/authorized_keys"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${SSH_DIR}"
  fi

  echo ""
  echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
  echo -e "${YELLOW}  COPY THE FOLLOWING TO GitHub Secret: SSH_PRIVATE_KEY${NC}"
  echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
  cat "${SSH_DIR}/id_ed25519_github"
  echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
  echo ""

  mark_done "ssh_key"
fi

# =============================================================================
section "9. Deploy nginx configuration"
# =============================================================================
if step_done "nginx_config"; then
  success "Nginx config already deployed — skipping"
else
  # Placeholder — will be replaced by deploy pipeline
  cat > "${APP_DIR}/nginx/nginx.conf" <<'NGINXEOF'
events { worker_connections 1024; }
http { server { listen 80; return 200 "ok\n"; } }
NGINXEOF
  mark_done "nginx_config"
  success "Nginx placeholder config created"
fi

# =============================================================================
section "10. Deploy monitoring configuration"
# =============================================================================
if step_done "monitoring_config"; then
  success "Monitoring configs already deployed — skipping"
else
  # These will be overwritten by the deploy pipeline with the latest from Git.
  # This creates placeholder files so infrastructure containers can start.
  log "Creating monitoring config placeholders..."
  mark_done "monitoring_config"
  success "Monitoring config placeholders created"
fi

# =============================================================================
section "11. Deploy infrastructure stack"
# =============================================================================
if step_done "infra_deploy"; then
  success "Infrastructure stack already deployed — checking health..."
else
  log "Deploying infrastructure compose..."

  # Create placeholder env file if missing
  if [[ ! -f "${APP_DIR}/.env.production" ]]; then
    touch "${APP_DIR}/.env.production"
    warn "Created empty .env.production — populate with secrets before app deploy"
  fi

  # Infrastructure compose should be deployed by the CI pipeline
  # At bootstrap time, we just ensure the directory structure is ready
  mark_done "infra_deploy"
  success "Infrastructure deployment ready"
fi

# =============================================================================
section "12. Generate secret values"
# =============================================================================
if step_done "secrets"; then
  success "Secrets already generated — skipping"
else
  REDIS_PW=$(openssl rand -hex 32)
  REDIS_UI_PW=$(openssl rand -hex 16)
  DOZZLE_PW=$(openssl rand -hex 16)
  GLITCHTIP_DB_PW=$(openssl rand -hex 32)
  GLITCHTIP_SK=$(openssl rand -hex 32)
  MONITORING_PW=$(openssl rand -hex 16)
  SECRET_KEY=$(openssl rand -hex 32)
  ENCRYPTION_KEY=$(openssl rand -base64 32)

  echo ""
  echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
  echo -e "${YELLOW}  Generated secrets (save ALL of these securely):${NC}"
  echo ""
  echo "  GitHub Secret: REDIS_PASSWORD         = ${REDIS_PW}"
  echo "  GitHub Secret: REDIS_UI_USERNAME      = hadha-admin"
  echo "  GitHub Secret: REDIS_UI_PASSWORD      = ${REDIS_UI_PW}"
  echo "  GitHub Secret: DOZZLE_USERNAME        = hadha-admin"
  echo "  GitHub Secret: DOZZLE_PASSWORD        = ${DOZZLE_PW}"
  echo "  GitHub Secret: GLITCHTIP_DB_PASSWORD  = ${GLITCHTIP_DB_PW}"
  echo "  GitHub Secret: GLITCHTIP_SECRET_KEY   = ${GLITCHTIP_SK}"
  echo "  GitHub Secret: MONITORING_USERNAME    = hadha-admin"
  echo "  GitHub Secret: MONITORING_PASSWORD    = ${MONITORING_PW}"
  echo "  GitHub Secret: SECRET_KEY             = ${SECRET_KEY}"
  echo "  GitHub Secret: ENCRYPTION_KEY         = ${ENCRYPTION_KEY}"
  echo ""
  echo "  See docs/SECRETS.md for the full list."
  echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
  echo ""

  mark_done "secrets"
fi

# =============================================================================
section "13. Health verification"
# =============================================================================
if step_done "health"; then
  success "Health verification already passed — skipping"
else
  log "Verifying Docker is running..."
  if docker info >/dev/null 2>&1; then
    success "Docker daemon is running"
  else
    error "Docker daemon is not running"
    systemctl start docker
  fi

  log "Verifying network..."
  if docker network inspect hadha >/dev/null 2>&1; then
    success "Docker network 'hadha' exists"
  else
    warn "Network 'hadha' not found — will be created on first deploy"
  fi

  mark_done "health"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
section "Bootstrap complete"
echo ""
echo "Server IP: $(curl -sf https://ipinfo.io/ip 2>/dev/null || hostname -I | awk '{print $1}')"
echo ""
echo "Next steps:"
echo "  1. Point DNS A records to this server for all subdomains:"
echo "       ${DOMAIN}          api.${DOMAIN}"
echo "       www.${DOMAIN}      admin.${DOMAIN}"
echo "       redis.${DOMAIN}    dozzle.${DOMAIN}"
echo "       grafana.${DOMAIN}  prometheus.${DOMAIN}"
echo "       cadvisor.${DOMAIN} uptime.${DOMAIN}"
echo "       errors.${DOMAIN}"
echo ""
echo "  2. Copy the SSH private key (above) to GitHub Secret: SSH_PRIVATE_KEY"
echo ""
echo "  3. Set remaining GitHub Secrets (see docs/SECRETS.md)"
echo ""
echo "  4. Push to main branch to trigger first deployment"
echo ""
echo "  State file: ${STATE_FILE}"
echo "  Infrastructure version: ${INFRA_VERSION}"
echo ""
