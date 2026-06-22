#!/usr/bin/env bash
# =============================================================================
# notify.sh — Send deployment notifications via Resend
#
# Usage (success):
#   ./notify.sh success <env> <tag> <sha> <author> <duration_seconds> "" "" ""
#
# Usage (failure):
#   ./notify.sh failure <env> <tag> <sha> <author> <duration_seconds> \
#               <failed_step> <rollback_status> <log_tail>
# =============================================================================

set -uo pipefail

STATUS="${1:?Usage: $0 <success|failure> ...}"
ENVIRONMENT="${2:-unknown}"
IMAGE_TAG="${3:-unknown}"
COMMIT_SHA="${4:-unknown}"
COMMIT_AUTHOR="${5:-unknown}"
DURATION="${6:-0}"
FAIL_STEP="${7:-}"
ROLLBACK_STATUS="${8:-}"
FAIL_LOGS="${9:-}"

RESEND_API_KEY="${RESEND_API_KEY:?RESEND_API_KEY is required}"

# H-3 FIX: was hardcoded /tmp/resend_response.json — concurrent notify.sh
# invocations would clobber each other's file. mktemp guarantees uniqueness.
RESPONSE_FILE=$(mktemp /tmp/resend_response.XXXXXX.json)
trap 'rm -f "${RESPONSE_FILE}"' EXIT
FROM_EMAIL="${RESEND_FROM_EMAIL:-noreply@hadha.co}"
TO_EMAIL="${RESEND_TO_EMAIL:-admin@hadha.co}"
SERVER_IP=$(curl -sf --max-time 5 https://ipinfo.io/ip 2>/dev/null \
            || hostname -I 2>/dev/null | awk '{print $1}' \
            || echo "unknown")
TIMESTAMP=$(date -u +'%Y-%m-%dT%H:%M:%S UTC')
SHORT_SHA="${COMMIT_SHA:0:8}"
ENV_UPPER=$(echo "${ENVIRONMENT}" | tr '[:lower:]' '[:upper:]')

FONT="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;"
FONT_MONO="font-family: 'SF Mono', 'Fira Code', monospace;"

# ── Row helper ────────────────────────────────────────────────────────────────
row() {
  local label="$1" value="$2" extra="${3:-}"
  echo "<tr><td style='padding:8px 0;color:#6b7280;width:40%;'>${label}</td><td style='padding:8px 0;${extra}'>${value}</td></tr>"
}

# ── Success email ─────────────────────────────────────────────────────────────
build_success_html() {
  cat <<HTML
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="${FONT} background:#f9fafb;margin:0;padding:0;">
<div style="max-width:600px;margin:40px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);">
  <div style="background:#16a34a;padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:20px;">✅ Deployment Succeeded</h1>
    <p style="margin:4px 0 0;color:#dcfce7;font-size:14px;">${ENV_UPPER} · ${TIMESTAMP}</p>
  </div>
  <div style="padding:32px;">
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      $(row "Environment"    "${ENVIRONMENT}"                          "font-weight:600;")
      $(row "Image Tag"      "${IMAGE_TAG}"                           "${FONT_MONO}font-weight:600;")
      $(row "Commit SHA"     "${SHORT_SHA}"                           "${FONT_MONO}")
      $(row "Author"         "${COMMIT_AUTHOR}")
      $(row "Duration"       "${DURATION}s")
      $(row "Server IP"      "${SERVER_IP}"                           "${FONT_MONO}")
      $(row "Health Checks"  "All passed ✓"                          "color:#16a34a;font-weight:600;")
    </table>
  </div>
  <div style="padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;text-align:center;">
    Hadha.co Deployment System
  </div>
</div>
</body></html>
HTML
}

# ── Failure email ─────────────────────────────────────────────────────────────
build_failure_html() {
  local escaped_logs
  escaped_logs=$(echo "${FAIL_LOGS}" | head -100 \
    | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')

  local rollback_color="#6b7280"
  case "${ROLLBACK_STATUS}" in
    succeeded)              rollback_color="#16a34a" ;;
    *FAILED*|*manual*)      rollback_color="#dc2626" ;;
    *skipped*)              rollback_color="#d97706" ;;
  esac

  cat <<HTML
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="${FONT} background:#f9fafb;margin:0;padding:0;">
<div style="max-width:600px;margin:40px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);">
  <div style="background:#dc2626;padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:20px;">🔴 Deployment Failed</h1>
    <p style="margin:4px 0 0;color:#fecaca;font-size:14px;">${ENV_UPPER} · ${TIMESTAMP}</p>
  </div>
  <div style="padding:32px;">
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      $(row "Environment"      "${ENVIRONMENT}"                        "font-weight:600;")
      $(row "Image Tag"        "${IMAGE_TAG}"                         "${FONT_MONO}font-weight:600;")
      $(row "Commit SHA"       "${SHORT_SHA}"                         "${FONT_MONO}")
      $(row "Author"           "${COMMIT_AUTHOR}")
      $(row "Duration"         "${DURATION}s")
      $(row "Failed Step"      "${FAIL_STEP:-unknown}"                "color:#dc2626;font-weight:600;")
      $(row "Rollback Status"  "${ROLLBACK_STATUS:-not attempted}"    "color:${rollback_color};font-weight:600;")
      $(row "Server IP"        "${SERVER_IP}"                         "${FONT_MONO}")
    </table>
    <div style="margin-top:24px;">
      <p style="color:#374151;font-size:14px;font-weight:600;">Last 100 log lines:</p>
      <pre style="${FONT_MONO} background:#1f2937;color:#d1fae5;padding:16px;border-radius:6px;font-size:11px;overflow-x:auto;white-space:pre-wrap;">${escaped_logs}</pre>
    </div>
  </div>
  <div style="padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;text-align:center;">
    Hadha.co Deployment System · Immediate attention required
  </div>
</div>
</body></html>
HTML
}

# ── Build and send ────────────────────────────────────────────────────────────
case "${STATUS}" in
  success)
    SUBJECT="✅ [${ENV_UPPER}] Deployed ${IMAGE_TAG} · ${SHORT_SHA}"
    HTML_BODY=$(build_success_html)
    ;;
  failure)
    SUBJECT="🔴 [${ENV_UPPER}] Deployment FAILED · ${SHORT_SHA}"
    HTML_BODY=$(build_failure_html)
    ;;
  *)
    echo "[ERROR] Unknown status: ${STATUS}. Use 'success' or 'failure'."
    exit 1
    ;;
esac

# Escape HTML for embedding in a JSON string
JSON_HTML=$(printf '%s' "${HTML_BODY}" | python3 -c "
import sys, json
print(json.dumps(sys.stdin.read()))
" 2>/dev/null || echo '"<p>Notification body generation failed</p>"')

HTTP_STATUS=$(curl -s -o "${RESPONSE_FILE}" -w "%{http_code}" \
  --max-time 15 \
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
  echo "[notify] Email sent (HTTP ${HTTP_STATUS}): ${SUBJECT}"
else
  echo "[notify] Email failed (HTTP ${HTTP_STATUS}): $(cat "${RESPONSE_FILE}" 2>/dev/null)"
  exit 1
fi
