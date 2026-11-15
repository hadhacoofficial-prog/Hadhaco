#!/usr/bin/env bash
# =============================================================================
# db-backup.sh — logical backup of the application database.
#
#   db-backup.sh                      hourly cron job (installed by db-setup.sh)
#   db-backup.sh --pre-deploy <tag>   gate run by deploy.sh BEFORE migrations
#
# Both: pg_dump -Fc, validated with pg_restore -l, sha256 next to the file.
#
# Hourly: keeps every dump for 2 days, then the 00:xx UTC dump of each day for
#   14 days; encrypted off-site copy is best-effort (exit 2 if it fails).
#
# --pre-deploy: STRICT. Dumps whichever database the app currently uses (the
#   local container, or Supabase while the app still points there), encrypts it,
#   uploads it, then downloads it back, decrypts it and runs pg_restore -l on
#   the round-tripped copy. Any failure exits 1, so the deploy stops before it
#   touches the schema. Keeps the newest 15 locally and off-site.
#   Emergency bypass for a manual deploy: SKIP_PREDEPLOY_BACKUP=1.
#
# Off-site config (/opt/hadha/.env.backup, mode 600):
#   BACKUP_S3_ENDPOINT=https://<project>.storage.supabase.co/storage/v1/s3
#   BACKUP_S3_REGION=ap-southeast-1          (default: auto, for R2)
#   BACKUP_S3_BUCKET=<a PRIVATE bucket — never the public media bucket>
#   BACKUP_S3_ACCESS_KEY=...
#   BACKUP_S3_SECRET_KEY=...
#   BACKUP_ENCRYPTION_KEY=<long random passphrase; keep a copy OFF the server>
# Decrypt: openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_ENCRYPTION_KEY \
#            -in <file>.dump.enc -out <file>.dump
# =============================================================================
set -euo pipefail

APP_DIR="/opt/hadha"
ENV_FILE="${APP_DIR}/.env.production"
DIR="${APP_DIR}/backups/db"
CONTAINER="hadha-postgres"
OFFSITE_ENV="${APP_DIR}/.env.backup"
PG_IMAGE="postgres:17.6-alpine"
AWS_CLI_IMAGE="amazon/aws-cli:2.22.0"
NETWORK="hadha"
PREDEPLOY_KEEP=15

MODE="hourly"
TAG=""
if [[ "${1:-}" == "--pre-deploy" ]]; then
  MODE="predeploy"
  TAG="$(printf '%s' "${2:-manual}" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-40)"
fi

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] db-backup(${MODE}): $*"; }
die() { log "ERROR: $*"; exit 1; }

if [[ "${MODE}" == "predeploy" && "${SKIP_PREDEPLOY_BACKUP:-0}" == "1" ]]; then
  log "SKIP_PREDEPLOY_BACKUP=1 — pre-deploy backup bypassed by operator"
  exit 0
fi

( umask 077; mkdir -p "${DIR}" )
ts="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ "${MODE}" == "predeploy" ]]; then
  name="predeploy-${ts}-${TAG}"
else
  name="hadha-${ts}"
fi
part="${DIR}/.${name}.dump.part"
final="${DIR}/${name}.dump"
enc="${final}.enc"
trap 'rm -f "${part}" "${enc}"' EXIT

# ── Which database does the app use right now? ───────────────────────────────
db_url=""
[[ -f "${ENV_FILE}" ]] && db_url="$(grep -E '^DATABASE_URL=' "${ENV_FILE}" | tail -1 | cut -d= -f2- | tr -d '\r')"
use_local=false
if [[ "${MODE}" == "hourly" || -z "${db_url}" || "${db_url}" == *"@${CONTAINER}:"* ]]; then
  use_local=true
fi

dump_database() {
  if "${use_local}"; then
    [[ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || echo false)" == "true" ]] \
      || die "${CONTAINER} is not running"
    # Nothing to protect before the first restore (the cutover fills the database).
    # shellcheck disable=SC2016  # $POSTGRES_* are expanded inside the container
    local tables
    # shellcheck disable=SC2016
    tables="$(docker exec -i "${CONTAINER}" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<< "select count(*) from pg_tables where schemaname = 'public'")"
    if [[ "${tables}" == "0" ]]; then
      if [[ "${MODE}" == "predeploy" ]]; then
        log "local database is empty — nothing to back up"; exit 0
      fi
      log "database is empty — skipping"; exit 0
    fi
    # shellcheck disable=SC2016
    docker exec "${CONTAINER}" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges' > "${part}"
  else
    # App still on an external database (Supabase): dump it read-only through a
    # throwaway client container (pg_dump must be >= the server version).
    docker run --rm --network "${NETWORK}" "${PG_IMAGE}" \
      pg_dump "${db_url/postgresql+asyncpg:/postgresql:}" -Fc --no-owner --no-privileges > "${part}"
  fi
}

dump_database || die "pg_dump failed"

# A truncated or corrupt archive must never be trusted.
docker run --rm -i "${PG_IMAGE}" pg_restore -l < "${part}" > /dev/null || die "dump failed validation (pg_restore -l)"
size="$(stat -c %s "${part}")"
(( size > 10000 )) || die "dump is suspiciously small (${size} bytes)"
mv "${part}" "${final}"
( cd "${DIR}" && sha256sum "$(basename "${final}")" > "$(basename "${final}").sha256" )
log "wrote ${final} (${size} bytes, source: $("${use_local}" && echo local || echo external))"

# ── Local retention ──────────────────────────────────────────────────────────
if [[ "${MODE}" == "hourly" ]]; then
  find "${DIR}" -maxdepth 1 -name 'hadha-*.dump*' -mmin +2880 ! -name 'hadha-????????T00*' -delete
  find "${DIR}" -maxdepth 1 -name 'hadha-*.dump*' -mmin +20160 -delete
else
  find "${DIR}" -maxdepth 1 -name 'predeploy-*.dump' -printf '%T@ %p\n' | sort -nr | tail -n +$((PREDEPLOY_KEEP + 1)) | cut -d' ' -f2- \
    | while read -r old; do rm -f "${old}" "${old}.sha256"; done
fi

# ── Off-site copy ────────────────────────────────────────────────────────────
if [[ ! -f "${OFFSITE_ENV}" ]]; then
  [[ "${MODE}" == "predeploy" ]] && die "no ${OFFSITE_ENV}: refusing to deploy without an off-site copy"
  exit 0
fi

remote_prefix="db"
[[ "${MODE}" == "predeploy" ]] && remote_prefix="db/predeploy"

offsite() {
  (
    set -a
    # shellcheck disable=SC1090
    . "${OFFSITE_ENV}"
    set +a
    : "${BACKUP_S3_ENDPOINT:?}" "${BACKUP_S3_BUCKET:?}" "${BACKUP_S3_ACCESS_KEY:?}" \
      "${BACKUP_S3_SECRET_KEY:?}" "${BACKUP_ENCRYPTION_KEY:?}"
    export BACKUP_ENCRYPTION_KEY
    openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_ENCRYPTION_KEY -in "${final}" -out "${enc}"
    local_enc_size="$(stat -c %s "${enc}")"

    # Path-style addressing: S3-compatible hosts other than AWS need it.
    # shellcheck disable=SC2016  # expanded by the inner sh, not here
    docker run --rm --entrypoint sh \
      -e AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
      -e AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
      -e AWS_DEFAULT_REGION="${BACKUP_S3_REGION:-auto}" \
      -e EP="${BACKUP_S3_ENDPOINT}" -e BUCKET="${BACKUP_S3_BUCKET}" \
      -e PREFIX="${remote_prefix}" -e MODE="${MODE}" -e KEEP="${PREDEPLOY_KEEP}" \
      -e FILE="/data/$(basename "${enc}")" -e WANT_SIZE="${local_enc_size}" \
      -v "${DIR}:/data:ro" \
      "${AWS_CLI_IMAGE}" -c '
        set -e
        aws configure set default.s3.addressing_style path
        key="$PREFIX/$(basename "$FILE")"
        aws --endpoint-url "$EP" s3 cp "$FILE" "s3://$BUCKET/$key" --only-show-errors
        got="$(aws --endpoint-url "$EP" s3api head-object --bucket "$BUCKET" --key "$key" --query ContentLength --output text)"
        [ "$got" = "$WANT_SIZE" ] || { echo "remote size $got != local $WANT_SIZE" >&2; exit 1; }
        if [ "$MODE" = "predeploy" ]; then
          # newest KEEP pre-deploy copies stay
          aws --endpoint-url "$EP" s3 ls "s3://$BUCKET/$PREFIX/" | awk "{print \$4}" | grep "^predeploy-.*\.dump\.enc\$" | sort -r | tail -n +$((KEEP + 1)) \
            | while read -r old; do aws --endpoint-url "$EP" s3 rm "s3://$BUCKET/$PREFIX/$old" --only-show-errors; done
        else
          # hourly copies older than 2 days (except 00:xx UTC) and anything older than 14 days
          aws --endpoint-url "$EP" s3 ls "s3://$BUCKET/$PREFIX/" | awk "{print \$4}" | grep "^hadha-.*\.dump\.enc\$" | sort -r | \
          while read -r k; do
            d=${k#hadha-}; day=${d%%T*}; hour=${d#*T}; hour=${hour%%[0-9][0-9][0-9][0-9]Z*}
            age_days=$(( ( $(date -u +%s) - $(date -u -d "${day:0:4}-${day:4:2}-${day:6:2}" +%s) ) / 86400 ))
            if [ "$age_days" -gt 14 ] || { [ "$age_days" -gt 2 ] && [ "$hour" != "00" ]; }; then
              aws --endpoint-url "$EP" s3 rm "s3://$BUCKET/$PREFIX/$k" --only-show-errors
            fi
          done
        fi
      '
  )
}

# Download the object back, decrypt it and make sure pg_restore can read it:
# proves the bytes in the bucket are restorable with the key we hold.
roundtrip() {
  (
    set -a
    # shellcheck disable=SC1090
    . "${OFFSITE_ENV}"
    set +a
    export BACKUP_ENCRYPTION_KEY
    tmpd="$(mktemp -d)"
    trap 'rm -rf "${tmpd}"' EXIT
    chmod 777 "${tmpd}"
    # shellcheck disable=SC2016
    docker run --rm --entrypoint sh \
      -e AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
      -e AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
      -e AWS_DEFAULT_REGION="${BACKUP_S3_REGION:-auto}" \
      -e EP="${BACKUP_S3_ENDPOINT}" -e BUCKET="${BACKUP_S3_BUCKET}" \
      -e KEY="${remote_prefix}/$(basename "${enc}")" \
      -v "${tmpd}:/out" \
      "${AWS_CLI_IMAGE}" -c '
        set -e
        aws configure set default.s3.addressing_style path
        aws --endpoint-url "$EP" s3 cp "s3://$BUCKET/$KEY" /out/remote.enc --only-show-errors
      '
    openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_ENCRYPTION_KEY -in "${tmpd}/remote.enc" -out "${tmpd}/remote.dump"
    docker run --rm -i "${PG_IMAGE}" pg_restore -l < "${tmpd}/remote.dump" > /dev/null
    cmp -s "${tmpd}/remote.dump" "${final}"
  )
}

if [[ "${MODE}" == "predeploy" ]]; then
  offsite   || die "off-site upload failed — deploy must not continue"
  roundtrip || die "off-site copy failed the download/decrypt/restore check — deploy must not continue"
  log "OK: pre-deploy backup uploaded and verified restorable (${remote_prefix}/$(basename "${enc}"))"
else
  offsite   || { log "ERROR: off-site upload failed (local backup is intact)"; exit 2; }
  log "uploaded encrypted copy off-site"
fi
