#!/usr/bin/env bash
# =============================================================================
# backup.sh — Pre-deployment backup of Docker state and volumes
#
# Usage:
#   ./backup.sh
#
# Creates a timestamped backup in /opt/hadha/backups/ containing:
#   - Current image tag metadata (JSON)
#   - Redis volume data (tar.gz)
#   - docker-compose.production.yml snapshot
#   - nginx configuration
#   - .env file checksums (no secret values)
#
# Database: Supabase (managed PostgreSQL) — no local pg_dump performed.
#   Use the Supabase dashboard for point-in-time recovery.
# =============================================================================

set -euo pipefail

BACKUP_RETENTION="${BACKUP_RETENTION:-30}"

APP_DIR="/opt/hadha"
BACKEND_CONTAINER="hadha-backend"
FRONTEND_CONTAINER="hadha-frontend"
REDIS_VOLUME_NAME="hadha_redis_data"

BACKUP_DIR="${APP_DIR}/backups"
TIMESTAMP=$(date +'%Y%m%dT%H%M%S')
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"
LOG_FILE="${APP_DIR}/backup.log"
STEP_START=0

log()        { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "${LOG_FILE}"; }
log_step()   { STEP_START=$(date +%s); log ""; log "── $* ──"; }
log_done()   { log "   ✓ done ($(( $(date +%s) - STEP_START ))s)"; }
log_skip()   { log "   ⊘ skipped: $*"; }
log_warn()   { log "   [WARN] $*"; }

mkdir -p "${BACKUP_PATH}"
log "════ BACKUP STARTED ════"
log "Destination : ${BACKUP_PATH}"
log "Database    : Supabase (managed) — no local pg_dump"

# =============================================================================
# Step 1: Capture current running image tags
# =============================================================================
log_step "Step 1: Image metadata"
CURRENT_BACKEND=$(docker inspect "${BACKEND_CONTAINER}"   \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")
CURRENT_FRONTEND=$(docker inspect "${FRONTEND_CONTAINER}" \
  --format='{{.Config.Image}}' 2>/dev/null || echo "")

cat > "${BACKUP_DIR}/metadata_${TIMESTAMP}.json" <<EOF
{
  "timestamp":      "${TIMESTAMP}",
  "backend_image":  "${CURRENT_BACKEND}",
  "frontend_image": "${CURRENT_FRONTEND}",
  "git_sha":        "${GIT_COMMIT_SHA:-unknown}",
  "git_author":     "${GIT_COMMIT_AUTHOR:-unknown}"
}
EOF
log "  Backend  : ${CURRENT_BACKEND:-not running}"
log "  Frontend : ${CURRENT_FRONTEND:-not running}"
log_done

# =============================================================================
# Step 2: Backup Redis volume
# =============================================================================
log_step "Step 2: Redis volume backup"
REDIS_VOLUME=$(docker volume ls -q 2>/dev/null | grep -Fx "${REDIS_VOLUME_NAME}" | head -1 || echo "")
if [[ -n "${REDIS_VOLUME}" ]]; then
  log "  Backing up volume: ${REDIS_VOLUME}"
  if docker run --rm \
      -v "${REDIS_VOLUME}:/data:ro" \
      -v "${BACKUP_PATH}:/backup" \
      alpine:3.20 \
      tar czf "/backup/redis_data.tar.gz" -C /data . 2>/dev/null; then
    REDIS_SIZE=$(du -sh "${BACKUP_PATH}/redis_data.tar.gz" 2>/dev/null | cut -f1 || echo "?")
    log "  Backup size: ${REDIS_SIZE}"
    log_done
  else
    log_warn "Redis volume backup failed — continuing (Redis data is cache; service is not interrupted)"
  fi
else
  log_skip "No Redis volume found matching '${REDIS_VOLUME_NAME}'"
fi

# =============================================================================
# Step 3: Compose file snapshot
# =============================================================================
log_step "Step 3: Compose file snapshot"
COMPOSE_SRC=$(ls "${APP_DIR}"/docker-compose.*.yml 2>/dev/null | head -1 || echo "")
if [[ -f "${COMPOSE_SRC}" ]]; then
  cp "${COMPOSE_SRC}" "${BACKUP_PATH}/docker-compose.yml"
  log "  Saved: $(basename "${COMPOSE_SRC}")"
  log_done
else
  log_skip "No docker-compose.*.yml found in ${APP_DIR}"
fi

# =============================================================================
# Step 4: Nginx configuration
# =============================================================================
log_step "Step 4: Nginx configuration"
if [[ -d "${APP_DIR}/nginx" ]]; then
  cp -r "${APP_DIR}/nginx" "${BACKUP_PATH}/nginx"
  NGINX_FILES=$(find "${BACKUP_PATH}/nginx" -type f | wc -l)
  log "  Copied ${NGINX_FILES} nginx config file(s)"
  log_done
else
  log_skip "${APP_DIR}/nginx directory not found"
fi

# =============================================================================
# Step 5: .env file checksums
# =============================================================================
log_step "Step 5: .env checksums"
ENV_COUNT=0
for env_file in "${APP_DIR}"/.env.*; do
  [[ -f "${env_file}" ]] || continue
  sha256sum "${env_file}" >> "${BACKUP_PATH}/env_checksums.txt"
  log "  Checksum: $(basename "${env_file}")"
  ENV_COUNT=$(( ENV_COUNT + 1 ))
done
if (( ENV_COUNT > 0 )); then
  log_done
else
  log_skip "No .env.* files found in ${APP_DIR}"
fi

# =============================================================================
# Step 6: Backup rotation
# =============================================================================
log_step "Step 6: Backup rotation (keeping last ${BACKUP_RETENTION})"
BACKUP_COUNT=$(find "${BACKUP_DIR}" -maxdepth 1 -name "[0-9]*" -type d 2>/dev/null | wc -l)
log "  Current backup count: ${BACKUP_COUNT}"

if (( BACKUP_COUNT > BACKUP_RETENTION )); then
  EXCESS=$(( BACKUP_COUNT - BACKUP_RETENTION ))
  log "  Removing ${EXCESS} old backup(s)..."

  ls -dt "${BACKUP_DIR}"/[0-9]*/ 2>/dev/null \
    | tail -n "+$(( BACKUP_RETENTION + 1 ))" \
    | while read -r old_dir; do
        TS=$(basename "${old_dir}")
        rm -rf "${old_dir}"
        rm -f "${BACKUP_DIR}/metadata_${TS}.json" 2>/dev/null || true
        log "  Removed: ${TS}"
      done
fi

FINAL_COUNT=$(find "${BACKUP_DIR}" -maxdepth 1 -name "[0-9]*" -type d 2>/dev/null | wc -l)
log "  Retained backups: ${FINAL_COUNT}"
log_done

log ""
log "════ BACKUP COMPLETE ════"
log "Path : ${BACKUP_PATH}"
