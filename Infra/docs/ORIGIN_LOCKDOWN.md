# Origin lockdown & SSH hardening runbook

Closes two gaps from the 2026-10-09 live-stack audit: the origin
(`147.93.110.191`) answers directly, bypassing Cloudflare, and SSH hardening
is unverified. Nothing here is enabled by a normal deploy.

## 1. Cloudflare Authenticated Origin Pulls (mTLS)

nginx rejects any TLS client that does not present Cloudflare's client
certificate, so direct hits to the IP (or a leaked origin address) get HTTP 400.

Order matters — enabling nginx first takes the site down:

1. Deploy (ships `nginx/origin-pull/cloudflare-origin-pull-ca.pem` and the
   `/etc/nginx/origin-pull` mount; enforcement stays **off**).
2. Cloudflare dashboard → hadha.co → SSL/TLS → Origin Server →
   **Authenticated Origin Pulls = On**. Harmless on its own.
3. On the VPS: `./origin-pull.sh enable --yes`
4. Verify: `https://hadha.co` works; direct
   `curl -k --resolve hadha.co:443:147.93.110.191 https://hadha.co/` returns 400.
5. Rollback any time: `./origin-pull.sh disable`.

Notes: port 80 only redirects/serves ACME and is unaffected. Internal Docker
healthchecks use plain HTTP on 127.0.0.1 and are unaffected. Cloudflare's CA is
valid until 2029-11-01.

## 2. Network-level allowlist (Hostinger firewall)

Docker-published ports bypass `ufw`, so restrict at the Hostinger firewall:
allow 80/443 from Cloudflare's published ranges
(<https://www.cloudflare.com/ips/>) and 22 from the admin IP(s) only. Take a
manual snapshot first and keep the hPanel browser console as a way back in.

## 3. SSH hardening

`./harden-ssh.sh` (dry run) then `./harden-ssh.sh --apply`, as root. It refuses
to run without an existing `authorized_keys`, writes
`/etc/ssh/sshd_config.d/00-hadha-hardening.conf` (key-only, no password,
`PermitRootLogin prohibit-password`), validates with `sshd -t`, and reloads.
Keep the current session open and confirm a second key login before closing it.
