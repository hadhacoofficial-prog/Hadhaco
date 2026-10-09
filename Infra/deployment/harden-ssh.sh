#!/usr/bin/env bash
# =============================================================================
# Hadha — SSH hardening (key-only, no password logins)
#
# Run on the VPS as root:  sudo ./harden-ssh.sh [--apply]
# Without --apply it only reports what it would do (dry run).
#
# Lockout guards: refuses to apply unless root or the deploy user already has
# a non-empty authorized_keys, validates with `sshd -t`, and reloads (does not
# restart) sshd so existing sessions survive. KEEP YOUR CURRENT SESSION OPEN
# and confirm a second login works before closing it.
# =============================================================================
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
DROPIN="/etc/ssh/sshd_config.d/00-hadha-hardening.conf"
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true

[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 1; }

has_keys() { [[ -s "$1/.ssh/authorized_keys" ]]; }
KEYS_OK=false
has_keys /root && KEYS_OK=true
getent passwd "${DEPLOY_USER}" >/dev/null && has_keys "$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)" && KEYS_OK=true

echo "Effective sshd settings now:"
sshd -T 2>/dev/null | grep -E "^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|maxauthtries|x11forwarding) " || true

if ! $KEYS_OK; then
  echo "REFUSING: no authorized_keys for root or '${DEPLOY_USER}'. Add a key first." >&2
  exit 1
fi

if ! $APPLY; then
  echo "Dry run OK (keys found). Re-run with --apply to write ${DROPIN}."
  exit 0
fi

# 00- prefix: sshd uses the FIRST value it sees, so this must sort before
# cloud-init's 50-cloud-init.conf (which often sets PasswordAuthentication yes).
cat > "${DROPIN}" <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
CONF
chmod 644 "${DROPIN}"

if ! sshd -t; then
  rm -f "${DROPIN}"
  echo "sshd -t failed; change reverted" >&2
  exit 1
fi
systemctl reload ssh 2>/dev/null || systemctl reload sshd
echo "Applied. Verify in a NEW terminal before closing this session:"
echo "  ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@<host>   # must be denied"
sshd -T | grep -E "^(passwordauthentication|permitrootlogin) "
