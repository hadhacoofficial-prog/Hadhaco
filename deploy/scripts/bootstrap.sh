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
#   4. Monitoring auth directory setup
#   5. Let's Encrypt SSL certificate setup (all subdomains)
#   6. Deploy scripts installation
#   7. Systemd service for auto-start
# =============================================================================

set -euo pipefail

DOMAIN="${DOMAIN:-hadha.co}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@hadha.co}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

log()     { echo "[$(date +'%H:%M:%S')] $*"; }
success() { echo "[$(date +'%H:%M:%S')] ✓ $*"; }
section() { echo ""; echo "══════════════════════════════"; echo "  $*"; echo "══════════════════════════════"; }

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
success "Fail2ban configured"

section "2. Firewall setup (UFW)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
success "UFW firewall configured"

section "3. Deploy user"
if ! id "${DEPLOY_USER}" &>/dev/null; then
  useradd -m -s /bin/bash "${DEPLOY_USER}"
  usermod -aG docker "${DEPLOY_USER}" 2>/dev/null || true
  success "Created deploy user: ${DEPLOY_USER}"
else
  success "Deploy user already exists: ${DEPLOY_USER}"
fi

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

section "5. Directory structure"
for dir in \
  /opt/hadha \
  /opt/hadha/nginx/conf.d \
  /opt/hadha/scripts \
  /opt/hadha/backups \
  /opt/hadha/dozzle \
  /var/www/certbot; do
  mkdir -p "${dir}"
done

chown -R "${DEPLOY_USER}:${DEPLOY_USER}" /opt/hadha
success "Directories created"

section "6. Monitoring auth"
# Authentication for Redis Commander and Dozzle is injected at deploy time
# from GitHub Secrets (REDIS_UI_USERNAME/REDIS_UI_PASSWORD, DOZZLE_USERNAME/DOZZLE_PASSWORD).
# deploy.sh generates /opt/hadha/dozzle/users.yml (bcrypt-hashed) automatically.
# Nothing needs to be created here — no plaintext passwords on the server at bootstrap.
success "Monitoring auth: credentials injected from GitHub Secrets at each deploy"

section "7. Nginx configuration"
cat > /opt/hadha/nginx/nginx.conf <<'NGINXEOF'
# Placeholder — will be replaced by deploy pipeline
events { worker_connections 1024; }
http { server { listen 80; return 200 "ok\n"; } }
NGINXEOF
success "Nginx placeholder config created"

section "8. SSL certificates (Let's Encrypt)"
log "Requesting certificate for ${DOMAIN} and all subdomains..."

# Temporarily start a plain HTTP server for ACME challenge
docker run -d --name certbot-temp \
  -p 80:80 \
  -v /var/www/certbot:/usr/share/nginx/html/. \
  nginx:alpine 2>/dev/null || true

sleep 2

# Single certificate covering all subdomains via Subject Alternative Names
certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "${ADMIN_EMAIL}" \
  --agree-tos \
  --no-eff-email \
  -d "${DOMAIN}" \
  -d "www.${DOMAIN}" \
  -d "api.${DOMAIN}" \
  -d "admin.${DOMAIN}" \
  -d "redis.${DOMAIN}" \
  -d "dozzle.${DOMAIN}" \
  2>/dev/null && success "Certificate obtained for all subdomains" || \
    log "[WARN] Certificate request failed — run certbot manually after DNS propagates"

docker stop certbot-temp 2>/dev/null && docker rm certbot-temp 2>/dev/null || true

# Auto-renew via cron
echo "0 3 * * * root certbot renew --quiet --post-hook 'docker exec hadha-nginx nginx -s reload'" \
  > /etc/cron.d/certbot-renew
success "Certbot auto-renewal configured"

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

section "10. Generate secret values"
REDIS_PW=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || \
           openssl rand -hex 32)
REDIS_UI_PW=$(python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || \
              openssl rand -hex 16)
DOZZLE_PW=$(python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || \
            openssl rand -hex 16)
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Generated secrets (save all of these securely):"
echo ""
echo "  GitHub Secret    REDIS_PASSWORD     = ${REDIS_PW}"
echo "  GitHub Secret    REDIS_UI_USERNAME  = hadha-admin"
echo "  GitHub Secret    REDIS_UI_PASSWORD  = ${REDIS_UI_PW}"
echo "  GitHub Secret    DOZZLE_USERNAME    = hadha-admin"
echo "  GitHub Secret    DOZZLE_PASSWORD    = ${DOZZLE_PW}"
echo ""
echo "  Server .env:     REDIS_PASSWORD=${REDIS_PW}"
echo ""
echo "  See DEVOPS.md for the full list of required GitHub Secrets."
echo "═══════════════════════════════════════════════════════"
echo ""

section "Bootstrap complete"
echo ""
echo "Next steps:"
echo "  1. Point DNS A records to this server for all subdomains:"
echo "       ${DOMAIN}        api.${DOMAIN}"
echo "       www.${DOMAIN}    admin.${DOMAIN}"
echo "       redis.${DOMAIN}  dozzle.${DOMAIN}"
echo "  2. Copy the SSH private key above to GitHub Secret: SSH_PRIVATE_KEY"
echo "  3. Set remaining GitHub Secrets (see DEVOPS.md)"
echo "  4. Copy .env files:"
echo "       /opt/hadha/.env.production         (backend config)"
echo "       /opt/hadha/.env.frontend.production (frontend config)"
echo "  5. Push to main branch to trigger first deployment"
echo ""
echo "Server IP: $(curl -sf https://ipinfo.io/ip 2>/dev/null || hostname -I | awk '{print $1}')"
