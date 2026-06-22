#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh — First-time VPS setup for Hadha.co
#
# Run as root or with sudo on a fresh Ubuntu 24.04 VPS:
#   curl -fsSL https://raw.githubusercontent.com/hadhacoofficial-prog/Hadhaco/main/deploy/scripts/bootstrap.sh | sudo bash
#
# What this script does:
#   1. System hardening (SSH, firewall, fail2ban)
#   2. Docker + Docker Compose installation
#   3. Directory structure creation
#   4. Nginx htpasswd generation (monitoring auth)
#   5. Let's Encrypt SSL certificate setup
#   6. Deploy scripts installation
#   7. Systemd service for auto-start
# =============================================================================

set -euo pipefail

DOMAIN="${DOMAIN:-hadha.co}"
STAGING_DOMAIN="${STAGING_DOMAIN:-staging.hadha.co}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@hadha.co}"
MONITORING_USER="${MONITORING_USER:-hadha-admin}"
MONITORING_PASSWORD="${MONITORING_PASSWORD:?Set MONITORING_PASSWORD before running}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

log()     { echo "[$(date +'%H:%M:%S')] $*"; }
success() { echo "[$(date +'%H:%M:%S')] ✓ $*"; }
section() { echo ""; echo "══════════════════════════════"; echo "  $*"; echo "══════════════════════════════"; }

# ── Must run as root ──────────────────────────────────────────────────────────
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root (sudo bash bootstrap.sh)"; exit 1; }

section "1. System update and hardening"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  curl wget git unzip jq \
  ufw fail2ban \
  apache2-utils \
  certbot \
  python3-certbot-nginx \
  htop ncdu \
  logrotate

# Configure fail2ban for SSH and nginx
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s

[nginx-http-auth]
enabled  = true
filter   = nginx-http-auth
port     = http,https
logpath  = /var/log/nginx/error.log

[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
port     = http,https
logpath  = /var/log/nginx/error.log
EOF

systemctl enable fail2ban
systemctl restart fail2ban
success "Fail2ban configured"

# ── Firewall ──────────────────────────────────────────────────────────────────
section "2. Firewall setup (UFW)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
success "UFW firewall configured"

# ── Create deploy user ────────────────────────────────────────────────────────
section "3. Deploy user"
if ! id "${DEPLOY_USER}" &>/dev/null; then
  useradd -m -s /bin/bash "${DEPLOY_USER}"
  usermod -aG docker "${DEPLOY_USER}" 2>/dev/null || true
  success "Created deploy user: ${DEPLOY_USER}"
else
  success "Deploy user already exists: ${DEPLOY_USER}"
fi

# ── Docker installation ───────────────────────────────────────────────────────
section "4. Docker installation"
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
  usermod -aG docker "${DEPLOY_USER}"
  success "Docker installed"
else
  success "Docker already installed: $(docker --version)"
fi

# ── Directory structure ───────────────────────────────────────────────────────
section "5. Directory structure"
for dir in \
  /opt/hadha \
  /opt/hadha/nginx/conf.d \
  /opt/hadha/scripts \
  /opt/hadha/backups \
  /opt/hadha-staging \
  /opt/hadha-staging/nginx/conf.d \
  /opt/hadha-staging/scripts \
  /opt/hadha-staging/backups \
  /var/www/certbot; do
  mkdir -p "${dir}"
done

chown -R "${DEPLOY_USER}:${DEPLOY_USER}" /opt/hadha /opt/hadha-staging
success "Directories created"

# ── Nginx htpasswd for monitoring tools ───────────────────────────────────────
section "6. Monitoring auth (htpasswd)"
htpasswd -bc /opt/hadha/nginx/htpasswd "${MONITORING_USER}" "${MONITORING_PASSWORD}"
cp /opt/hadha/nginx/htpasswd /opt/hadha-staging/nginx/htpasswd
success "htpasswd created for user: ${MONITORING_USER}"

# ── Nginx config files ────────────────────────────────────────────────────────
section "7. Nginx configuration"
# These will be overwritten by deploy — create placeholders
cat > /opt/hadha/nginx/nginx.conf <<'NGINXEOF'
# Placeholder — will be replaced by deploy pipeline
events { worker_connections 1024; }
http { server { listen 80; return 200 "ok\n"; } }
NGINXEOF

cp /opt/hadha/nginx/nginx.conf /opt/hadha-staging/nginx/nginx.conf
success "Nginx placeholder configs created"

# ── Let's Encrypt certificates ────────────────────────────────────────────────
section "8. SSL certificates (Let's Encrypt)"
log "Requesting certificate for ${DOMAIN} and ${STAGING_DOMAIN}..."

# Temporarily start a plain HTTP server for ACME challenge
docker run -d --name certbot-temp \
  -p 80:80 \
  -v /var/www/certbot:/usr/share/nginx/html/. \
  nginx:alpine 2>/dev/null || true

sleep 2

certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "${ADMIN_EMAIL}" \
  --agree-tos \
  --no-eff-email \
  -d "${DOMAIN}" \
  -d "www.${DOMAIN}" \
  2>/dev/null && success "Production certificate obtained" || \
    log "[WARN] Certificate request failed — run certbot manually after DNS propagates"

certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "${ADMIN_EMAIL}" \
  --agree-tos \
  --no-eff-email \
  -d "${STAGING_DOMAIN}" \
  2>/dev/null && success "Staging certificate obtained" || \
    log "[WARN] Staging certificate request failed"

docker stop certbot-temp 2>/dev/null && docker rm certbot-temp 2>/dev/null || true

# ── Auto-renew via cron ───────────────────────────────────────────────────────
echo "0 3 * * * root certbot renew --quiet --post-hook 'docker exec hadha-nginx nginx -s reload'" \
  > /etc/cron.d/certbot-renew
success "Certbot auto-renewal configured"

# ── SSH key for GitHub Actions ────────────────────────────────────────────────
section "9. GitHub Actions deploy key"
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
echo "═══════════════════════════════════════════════════════"
echo "  COPY THE FOLLOWING TO GitHub Secret: SSH_PRIVATE_KEY"
echo "═══════════════════════════════════════════════════════"
cat "${SSH_DIR}/id_ed25519_github"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
section "Bootstrap complete"
echo ""
echo "Next steps:"
echo "  1. Copy the SSH private key above to GitHub Secret: SSH_PRIVATE_KEY"
echo "  2. Set remaining GitHub Secrets (see DEVOPS.md)"
echo "  3. Copy .env files to /opt/hadha/.env.production and /opt/hadha/.env.frontend.production"
echo "  4. Copy docker-compose files to /opt/hadha/"
echo "  5. Push to main branch to trigger first deployment"
echo ""
echo "Server IP: $(curl -sf https://ipinfo.io/ip 2>/dev/null || hostname -I | awk '{print $1}')"
