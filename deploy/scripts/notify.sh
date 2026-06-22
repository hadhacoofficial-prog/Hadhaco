#!/usr/bin/env bash
# =============================================================================
# notify.sh — Send deployment notifications via Resend
#
# Usage (success):
#   ./notify.sh success <env> <tag> <sha> <author> <duration_seconds> "" ""
#
# Usage (failure):
#   ./notify.sh failure <env> <tag> <sha> <author> <duration_seconds> <reason> <logs>
# =============================================================================

set -uo pipefail

STATUS="${1:?Usage: $0 <success|failure> ...}"
ENVIRONMENT="${2:-unknown}"
IMAGE_TAG="${3:-unknown}"
COMMIT_SHA="${4:-unknown}"
COMMIT_AUTHOR="${5:-unknown}"
DURATION="${6:-0}"
FAIL_REASON="${7:-}"
FAIL_LOGS="${8:-}"

RESEND_API_KEY="${RESEND_API_KEY:?RESEND_API_KEY is required}"
FROM_EMAIL="${RESEND_FROM_EMAIL:-noreply@hadha.co}"
TO_EMAIL="${RESEND_TO_EMAIL:-admin@hadha.co}"
SERVER_IP=$(curl -sf https://ipinfo.io/ip 2>/dev/null || hostname -I | awk '{print $1}')
TIMESTAMP=$(date -u +'%Y-%m-%dT%H:%M:%S UTC')
SHORT_SHA="${COMMIT_SHA:0:8}"
ENV_UPPER=$(echo "${ENVIRONMENT}" | tr '[:lower:]' '[:upper:]')

# ── Shared styles ─────────────────────────────────────────────────────────────
FONT="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;"
FONT_MONO="font-family: 'SF Mono', 'Fira Code', monospace;"

build_success_html() {
  cat <<HTML
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="${FONT} background:#f9fafb; margin:0; padding:0;">
<div style="max-width:600px; margin:40px auto; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.1);">
  <div style="background:#16a34a; padding:24px 32px;">
    <h1 style="margin:0; color:#fff; font-size:20px;">✅ Deployment Succeeded</h1>
    <p style="margin:4px 0 0; color:#dcfce7; font-size:14px;">${ENV_UPPER} · ${TIMESTAMP}</p>
  </div>
  <div style="padding:32px;">
    <table style="width:100%; border-collapse:collapse; font-size:14px;">
      <tr><td style="padding:8px 0; color:#6b7280; width:40%;">Environment</td><td style="padding:8px 0; font-weight:600;">${ENVIRONMENT}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Version / Tag</td><td style="padding:8px 0; font-weight:600; ${FONT_MONO}">${IMAGE_TAG}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Commit SHA</td><td style="padding:8px 0; ${FONT_MONO}">${SHORT_SHA}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Author</td><td style="padding:8px 0;">${COMMIT_AUTHOR}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Duration</td><td style="padding:8px 0;">${DURATION}s</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Server IP</td><td style="padding:8px 0; ${FONT_MONO}">${SERVER_IP}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Health Checks</td><td style="padding:8px 0; color:#16a34a; font-weight:600;">All passed ✓</td></tr>
    </table>
  </div>
  <div style="padding:16px 32px; background:#f9fafb; border-top:1px solid #e5e7eb; font-size:12px; color:#9ca3af; text-align:center;">
    Hadha.co Deployment System
  </div>
</div>
</body>
</html>
HTML
}

build_failure_html() {
  local escaped_logs
  escaped_logs=$(echo "${FAIL_LOGS}" | head -100 | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
  cat <<HTML
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="${FONT} background:#f9fafb; margin:0; padding:0;">
<div style="max-width:600px; margin:40px auto; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.1);">
  <div style="background:#dc2626; padding:24px 32px;">
    <h1 style="margin:0; color:#fff; font-size:20px;">🔴 Deployment Failed</h1>
    <p style="margin:4px 0 0; color:#fecaca; font-size:14px;">${ENV_UPPER} · ${TIMESTAMP}</p>
  </div>
  <div style="padding:32px;">
    <table style="width:100%; border-collapse:collapse; font-size:14px;">
      <tr><td style="padding:8px 0; color:#6b7280; width:40%;">Environment</td><td style="padding:8px 0; font-weight:600;">${ENVIRONMENT}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Commit SHA</td><td style="padding:8px 0; ${FONT_MONO}">${SHORT_SHA}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Author</td><td style="padding:8px 0;">${COMMIT_AUTHOR}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Failed Step</td><td style="padding:8px 0; color:#dc2626; font-weight:600;">${FAIL_REASON}</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Rollback</td><td style="padding:8px 0;">Automatic rollback attempted</td></tr>
      <tr><td style="padding:8px 0; color:#6b7280;">Duration</td><td style="padding:8px 0;">${DURATION}s</td></tr>
    </table>
    <div style="margin-top:24px;">
      <p style="color:#374151; font-size:14px; font-weight:600;">Last 100 log lines:</p>
      <pre style="${FONT_MONO} background:#1f2937; color:#d1fae5; padding:16px; border-radius:6px; font-size:11px; overflow-x:auto; white-space:pre-wrap;">${escaped_logs}</pre>
    </div>
  </div>
  <div style="padding:16px 32px; background:#f9fafb; border-top:1px solid #e5e7eb; font-size:12px; color:#9ca3af; text-align:center;">
    Hadha.co Deployment System · Immediate attention required
  </div>
</div>
</body>
</html>
HTML
}

# ── Compose and send ──────────────────────────────────────────────────────────
case "${STATUS}" in
  success)
    SUBJECT="✅ [${ENV_UPPER}] Deployment succeeded · ${SHORT_SHA}"
    HTML_BODY=$(build_success_html)
    ;;
  failure)
    SUBJECT="🔴 [${ENV_UPPER}] Deployment FAILED · ${SHORT_SHA}"
    HTML_BODY=$(build_failure_html)
    ;;
  *)
    echo "[ERROR] Unknown status: ${STATUS}"
    exit 1
    ;;
esac

# Escape HTML for JSON (double-quotes and backslashes)
JSON_HTML=$(echo "${HTML_BODY}" | python3 -c "
import sys, json
print(json.dumps(sys.stdin.read()))
" 2>/dev/null || echo '"<p>Notification body generation failed</p>"')

HTTP_STATUS=$(curl -s -o /tmp/resend_response.json -w "%{http_code}" \
  --max-time 10 \
  -X POST "https://api.resend.com/emails" \
  -H "Authorization: Bearer ${RESEND_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"from\":    \"${FROM_EMAIL}\",
    \"to\":      [\"${TO_EMAIL}\"],
    \"subject\": \"${SUBJECT}\",
    \"html\":    ${JSON_HTML}
  }")

if [[ "${HTTP_STATUS}" =~ ^2 ]]; then
  echo "[notify] Email sent (${HTTP_STATUS}): ${SUBJECT}"
else
  echo "[notify] Email failed (${HTTP_STATUS}): $(cat /tmp/resend_response.json 2>/dev/null)"
  exit 1
fi
