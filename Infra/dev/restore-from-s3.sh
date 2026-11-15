#!/bin/sh
# =============================================================================
# restore-from-s3.sh — local dev stack: fill the dev database from the newest
# production backup in the S3 bucket, then scrub it (scrub.sql).
#
# Run by the `db-restore` service of the root docker-compose.yml, after the
# dev `postgres` is healthy and before migrations/backend start. Needs the
# BACKUP_S3_* values and BACKUP_ENCRYPTION_KEY from Backend/.env.
#
#   * Skips when the dev database already has data (keeps your local changes).
#   * FORCE_RESTORE=1 drops the schema and restores the newest backup again:
#       FORCE_RESTORE=1 docker compose up db-restore
#   * BACKUP_KEY=hadha-<ts>.dump.enc (or predeploy-...) restores a specific one.
#
# The raw dump holds production personal data. It only ever exists inside this
# container (/tmp) and the dev database, and scrub.sql runs immediately after
# the restore — it replaces emails, names, phones and addresses, drops logs,
# sessions, tokens and 2FA secrets, and gives every account the password
# printed at the end.
# =============================================================================
set -eu

log() { echo "[db-restore] $*"; }

: "${BACKUP_S3_ENDPOINT:?set BACKUP_S3_ENDPOINT in Backend/.env}"
: "${BACKUP_S3_BUCKET:?set BACKUP_S3_BUCKET in Backend/.env}"
: "${BACKUP_S3_ACCESS_KEY:?set BACKUP_S3_ACCESS_KEY in Backend/.env}"
: "${BACKUP_S3_SECRET_KEY:?set BACKUP_S3_SECRET_KEY in Backend/.env}"
: "${BACKUP_ENCRYPTION_KEY:?set BACKUP_ENCRYPTION_KEY in Backend/.env}"
: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}"

psqlq() { psql -X -At -v ON_ERROR_STOP=1 "$@"; }

FORCE="${FORCE_RESTORE:-0}"
if [ "${FORCE}" != "1" ] && [ "$(psqlq -c "select to_regclass('public.profiles') is not null")" = "t" ]; then
  n="$(psqlq -c 'select count(*) from public.profiles')"
  if [ "$(psqlq -c "select to_regclass('public._dev_scrubbed') is not null")" = "t" ]; then
    log "dev database already restored and scrubbed (${n} profiles) — skipping. FORCE_RESTORE=1 refreshes it."
    exit 0
  fi
  if [ "${n}" -gt 0 ]; then
    # Data without the marker = an earlier restore was interrupted before the
    # scrub ran. Never keep that: start over.
    log "found unscrubbed data from an interrupted restore — restoring again"
    FORCE=1
  fi
fi

log "installing curl/openssl"
apk add --no-cache curl openssl >/dev/null

# S3 over plain curl (SigV4, path-style): no aws-cli needed, so the install
# above stays a couple of seconds.
s3_get() { # <path-after-bucket-or-empty> <extra curl args...>
  _path="$1"; shift
  curl -sSf --aws-sigv4 "aws:amz:${BACKUP_S3_REGION:-auto}:s3" \
    --user "${BACKUP_S3_ACCESS_KEY}:${BACKUP_S3_SECRET_KEY}" \
    "${BACKUP_S3_ENDPOINT%/}/${BACKUP_S3_BUCKET}${_path}" "$@"
}

key="${BACKUP_KEY:-}"
if [ -z "${key}" ]; then
  # Hourly backups sort by timestamp, so the last name is the newest.
  key="$(s3_get '?list-type=2&prefix=db/hadha-' | grep -o '<Key>[^<]*</Key>' | sed 's#<Key>db/##; s#</Key>##' | grep '^hadha-.*\.dump\.enc$' | sort | tail -1 || true)"
  prefix="db"
else
  case "${key}" in predeploy-*) prefix="db/predeploy" ;; *) prefix="db" ;; esac
fi
[ -n "${key}" ] || { log "no backups found in bucket ${BACKUP_S3_BUCKET} under db/"; exit 1; }

log "downloading ${key}"
s3_get "/${prefix}/${key}" -o /tmp/backup.dump.enc
export BACKUP_ENCRYPTION_KEY
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_ENCRYPTION_KEY -in /tmp/backup.dump.enc -out /tmp/backup.dump \
  || { log "decryption failed — is BACKUP_ENCRYPTION_KEY the one used on the server?"; exit 1; }
rm -f /tmp/backup.dump.enc
pg_restore -l /tmp/backup.dump > /tmp/full.list || { log "downloaded file is not a valid dump"; exit 1; }

if [ "${FORCE}" = "1" ]; then
  log "dropping schema public before restoring"
  psqlq -q -c 'DROP SCHEMA IF EXISTS public CASCADE' -c 'CREATE SCHEMA public'
fi

# Extensions live in `public` (the restored index definitions reference
# public.gin_trgm_ops). The dump's own schema/extension entries are skipped.
psql -X -q -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_trgm   WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS btree_gin WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS unaccent  WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pgcrypto  WITH SCHEMA public;
SQL
grep -v -E ' SCHEMA - public | EXTENSION ' /tmp/full.list > /tmp/restore.list

log "restoring"
pg_restore --exit-on-error --no-owner --no-privileges -L /tmp/restore.list -d "${PGDATABASE}" /tmp/backup.dump
rm -f /tmp/backup.dump /tmp/full.list /tmp/restore.list

log "scrubbing personal data"
psql -X -q -v ON_ERROR_STOP=1 -f /dev-db/scrub.sql

log "done — dev logins (password for every account: DevPass123!):"
psqlq -F '  ' -c "select email, role from public.profiles where role in ('admin','super_admin') order by email"
