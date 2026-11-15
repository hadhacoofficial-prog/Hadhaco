#!/usr/bin/env bash
# =============================================================================
# db-cutover.sh — move the application database from Supabase to the local
# PostgreSQL container (hadha-postgres).
#
#   db-cutover.sh rehearse    non-disruptive: dump Supabase, restore into a
#                             scratch database, compare, run alembic + an
#                             asyncpg smoke query. Touches nothing live.
#   db-cutover.sh cutover     maintenance window (~2-4 min): stop writers,
#                             final dump, restore, verify EXACT equality,
#                             switch .env.production, restart. Any failure
#                             after the writers stop rolls back automatically.
#   db-cutover.sh rollback    point the app back at Supabase.
#
# Supabase is never written to. After a successful cutover it stays intact as a
# fallback; rolling back after the app has taken new writes loses those writes.
#
# Prereqs: scripts/db-setup.sh has run (hadha-postgres healthy).
# =============================================================================
set -euo pipefail

APP_DIR="/opt/hadha"
ENV_FILE="${APP_DIR}/.env.production"
PG_ENV="${APP_DIR}/.env.postgres"
APP_COMPOSE="${APP_DIR}/docker-compose.application.yml"
WORK="${APP_DIR}/backups/db-cutover"
SOURCE_URL_FILE="${WORK}/source.url"
PG_IMAGE="postgres:17.6-alpine"
NETWORK="hadha"
PG_CONTAINER="hadha-postgres"
NEW_DB="hadha"
SCRATCH_DB="hadha_rehearsal"
APP_SERVICES=(backend celery-worker-media celery-worker-general celery-beat)
APP_CONTAINERS=(hadha-celery-beat hadha-celery-worker-general hadha-celery-worker-media hadha-backend)

ROLLBACK_ARMED=0
on_exit() {
  local rc=$?
  if (( ROLLBACK_ARMED )) && (( rc != 0 )); then
    ROLLBACK_ARMED=0
    log "FAILED (exit ${rc}) — rolling back automatically"
    cmd_rollback || log "AUTOMATIC ROLLBACK FAILED: run: db-cutover.sh rollback"
  fi
}
trap on_exit EXIT

log()  { echo "[$(date +'%H:%M:%S')] $*"; }
die()  { log "ERROR: $*"; exit 1; }

env_get() { grep -E "^$1=" "$2" | tail -1 | cut -d= -f2- | tr -d '\r'; }

# Upsert KEY=VALUE in a file without sed (the value needs no escaping) and
# without replacing the inode, so owner/mode stay.
env_set() {
  local key="$1" val="$2" file="$3" tmp
  tmp="$(mktemp)"
  { grep -v "^${key}=" "${file}" || true; } > "${tmp}"
  printf '%s=%s\n' "${key}" "${val}" >> "${tmp}"
  cat "${tmp}" > "${file}"
  rm -f "${tmp}"
}

pg_user="$(env_get POSTGRES_USER "${PG_ENV}")"
pg_pass="$(env_get POSTGRES_PASSWORD "${PG_ENV}")"
[[ -n "${pg_user}" && -n "${pg_pass}" ]] || die "cannot read ${PG_ENV}"

# psql inside the new container (trust the unix socket — no password needed).
psql_new() { # db args...
  local db="$1"; shift
  docker exec -i "${PG_CONTAINER}" psql -X -v ON_ERROR_STOP=1 -U "${pg_user}" -d "${db}" "$@"
}

# Run a pg client tool against Supabase from a throwaway container.
pg_src() { # tool args...
  local url; url="$(cat "${SOURCE_URL_FILE}")"
  docker run --rm --network "${NETWORK}" -v "${WORK}:/work" "${PG_IMAGE}" "$@" "${url}"
}
psql_src() { docker run --rm --network "${NETWORK}" "${PG_IMAGE}" psql -X -A -t -F '|' -v ON_ERROR_STOP=1 "$(cat "${SOURCE_URL_FILE}")" "$@"; }

# ── Fingerprint: row counts, sequences, structure ────────────────────────────
FINGERPRINT_SQL=$(cat <<'SQL'
select 'rows:' || table_name || '=' ||
       (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
  from information_schema.tables
 where table_schema = 'public' and table_type = 'BASE TABLE'
union all
select 'seq:' || sequencename || '=' || coalesce(last_value::text, 'null')
  from pg_sequences where schemaname = 'public'
union all
-- Partial-index predicates are left out: the server re-deparses them after a
-- restore (same meaning, different text), which would be a false mismatch.
select 'indexes:' || count(*) || ':' || coalesce(md5(string_agg(indexname || regexp_replace(indexdef, ' WHERE .*$', ''), E'\n' order by indexname)), '')
  from pg_indexes where schemaname = 'public'
union all
select 'columns:' || count(*) || ':' || coalesce(md5(string_agg(table_name || '.' || column_name || ':' || data_type || ':' || is_nullable, E'\n' order by table_name, column_name)), '')
  from information_schema.columns c
 where c.table_schema = 'public'
   -- tables only: extension views (pg_stat_statements) live in a different schema on Supabase
   and exists (select 1 from information_schema.tables t
                where t.table_schema = c.table_schema and t.table_name = c.table_name
                  and t.table_type = 'BASE TABLE')
union all
select 'constraints:' || count(*) || ':' || coalesce(md5(string_agg(conrelid::regclass::text || conname || contype::text, E'\n' order by conrelid::regclass::text, conname)), '')
  from pg_constraint where connamespace = 'public'::regnamespace
union all
select 'alembic:' || version_num from public.alembic_version
order by 1;
SQL
)

fingerprint_src() { psql_src -c "${FINGERPRINT_SQL}"; }
fingerprint_new() { psql_new "$1" -A -t -c "${FINGERPRINT_SQL}"; }

require_state() {
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "${PG_CONTAINER}" 2>/dev/null || true)" == "healthy" ]] \
    || die "${PG_CONTAINER} is not healthy — run scripts/db-setup.sh first"
  local free_kb; free_kb="$(df --output=avail -k "${APP_DIR}" | tail -1 | tr -d ' ')"
  (( free_kb > 2000000 )) || die "less than 2 GB free on ${APP_DIR}"
  ( umask 077; mkdir -p "${WORK}" )
}

load_source_url() {
  if [[ -f "${SOURCE_URL_FILE}" ]]; then return 0; fi
  local url; url="$(env_get DATABASE_URL "${ENV_FILE}")"
  [[ "${url}" == *supabase* ]] || die "DATABASE_URL does not point at Supabase (already cut over?) and ${SOURCE_URL_FILE} is missing"
  # pg tools need a plain postgresql:// URL (no SQLAlchemy driver suffix).
  ( umask 077; printf '%s\n' "${url/postgresql+asyncpg:/postgresql:}" > "${SOURCE_URL_FILE}" )
}

dump_source() { # <outfile-in-WORK> [extra pg_dump args]
  local out="$1"; shift
  pg_src pg_dump -Fc --no-owner --no-privileges -f "/work/${out}" "$@"
  [[ -s "${WORK}/${out}" ]] || die "dump ${out} is empty"
  log "  dump ${out}: $(du -h "${WORK}/${out}" | cut -f1)"
}

restore_into() { # <db> <dumpfile>
  # The dump carries `CREATE SCHEMA public`, which already exists in the target
  # (the extensions live there), so that one TOC entry is skipped.
  docker exec -i "${PG_CONTAINER}" sh -c 'cat > /tmp/restore.dump' < "${WORK}/$2"
  docker exec -e TARGET_DB="$1" "${PG_CONTAINER}" sh -c '
    set -e
    pg_restore -l /tmp/restore.dump | grep -v " SCHEMA - public " > /tmp/restore.list
    rc=0
    pg_restore --exit-on-error --no-owner --no-privileges -L /tmp/restore.list \
      -U "$POSTGRES_USER" -d "$TARGET_DB" /tmp/restore.dump || rc=$?
    rm -f /tmp/restore.dump /tmp/restore.list
    exit $rc'
}

make_extensions() { # <db>
  psql_new "$1" -q <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_trgm   WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS btree_gin WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS unaccent  WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pgcrypto  WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;
SQL
}

new_db_url() { # <db> <driver>
  printf '%s://%s:%s@%s:5432/%s' "$2" "${pg_user}" "${pg_pass}" "${PG_CONTAINER}" "$1"
}

app_smoke() { # <db> — import the real app config and query through asyncpg
  local sanitized; sanitized="$(mktemp)"
  tr -d '\r' < "${ENV_FILE}" | sed '/^$/d' > "${sanitized}"
  local image; image="$(docker inspect -f '{{.Config.Image}}' hadha-backend)"
  docker run --rm -i --network "${NETWORK}" --env-file "${sanitized}" \
    -e DATABASE_URL="$(new_db_url "$1" postgresql+asyncpg)" \
    -e ALEMBIC_DATABASE_URL="$(new_db_url "$1" postgresql+psycopg)" \
    "${image}" python - <<'PY'
import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def main() -> None:
    async with AsyncSessionLocal() as s:
        users = (await s.execute(text("select count(*) from profiles"))).scalar_one()
        products = (await s.execute(text("select count(*) from products"))).scalar_one()
        creds = (await s.execute(text("select count(*) from user_credentials"))).scalar_one()
    print(f"smoke ok: profiles={users} products={products} credentials={creds}")

asyncio.run(main())
PY
  local rc=$?
  rm -f "${sanitized}"
  return "${rc}"
}

alembic_current() { # <db>
  local sanitized; sanitized="$(mktemp)"
  tr -d '\r' < "${ENV_FILE}" | sed '/^$/d' > "${sanitized}"
  local image; image="$(docker inspect -f '{{.Config.Image}}' hadha-backend)"
  docker run --rm --network "${NETWORK}" --env-file "${sanitized}" \
    -e DATABASE_URL="$(new_db_url "$1" postgresql+asyncpg)" \
    -e ALEMBIC_DATABASE_URL="$(new_db_url "$1" postgresql+psycopg)" \
    "${image}" alembic -c alembic/alembic.ini current 2>&1 | grep -E '^[0-9a-z_]+( \(head\))?$' || true
  rm -f "${sanitized}"
}

# ── rehearse ─────────────────────────────────────────────────────────────────
cmd_rehearse() {
  require_state; load_source_url
  local t0 ts; t0=$(date +%s); ts=$(date +%Y%m%d-%H%M%S)
  log "rehearsal: source reachable?"
  psql_src -c 'select version()' >/dev/null || die "cannot reach Supabase"

  log "rehearsal: dumping Supabase (public schema, read-only)"
  dump_source "rehearsal-${ts}.dump" -n public

  log "rehearsal: restoring into scratch database ${SCRATCH_DB}"
  psql_new postgres -q -c "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)" -c "CREATE DATABASE ${SCRATCH_DB} OWNER ${pg_user}"
  make_extensions "${SCRATCH_DB}"
  restore_into "${SCRATCH_DB}" "rehearsal-${ts}.dump"

  log "rehearsal: comparing"
  fingerprint_src > "${WORK}/fp-src.txt"
  fingerprint_new "${SCRATCH_DB}" > "${WORK}/fp-new.txt"
  if diff -u "${WORK}/fp-src.txt" "${WORK}/fp-new.txt" > "${WORK}/fp.diff"; then
    log "  fingerprints identical ($(wc -l < "${WORK}/fp-src.txt") facts)"
  else
    log "  DIFFERENCES (expected only if production took writes since the dump):"
    sed -n '1,40p' "${WORK}/fp.diff"
  fi

  log "rehearsal: alembic state on the restored copy:"
  alembic_current "${SCRATCH_DB}"
  log "rehearsal: app smoke test through asyncpg:"
  app_smoke "${SCRATCH_DB}" || die "app smoke failed against restored copy"

  if [[ "${KEEP_SCRATCH:-0}" != "1" ]]; then
    psql_new postgres -q -c "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)"
  fi
  log "REHEARSAL OK in $(( $(date +%s) - t0 ))s (nothing live touched)"
}

# ── rollback ─────────────────────────────────────────────────────────────────
recreate_app() {
  # compose interpolates the image variables of every service, so export all three.
  BACKEND_IMAGE="$(cat "${WORK}/images.backend")" STOREFRONT_IMAGE="$(cat "${WORK}/images.storefront")" \
  ADMIN_IMAGE="$(cat "${WORK}/images.admin")" \
    docker compose --env-file "${ENV_FILE}" -f "${APP_COMPOSE}" up -d --force-recreate --no-deps "${APP_SERVICES[@]}"
}

cmd_rollback() {
  local latest; latest="$(find "${APP_DIR}" -maxdepth 1 -name '.env.production.pre-pg-cutover.*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2- || true)"
  [[ -n "${latest}" ]] || die "no ${ENV_FILE}.pre-pg-cutover.* backup to restore"
  log "restoring ${latest} -> ${ENV_FILE}"
  cat "${latest}" > "${ENV_FILE}"
  [[ -f "${WORK}/images.backend" ]] || die "image record missing in ${WORK}; recreate the app via deploy.sh"
  recreate_app
  log "ROLLED BACK to Supabase. Writes taken since the cutover are only in ${PG_CONTAINER}."
}

# ── cutover ──────────────────────────────────────────────────────────────────
cmd_cutover() {
  require_state; load_source_url
  [[ "$(env_get DATABASE_URL "${ENV_FILE}")" == *supabase* ]] || die "app already points at the local database"
  local ts t0 existing; ts=$(date +%Y%m%d-%H%M%S); t0=$(date +%s)

  existing="$(psql_new "${NEW_DB}" -A -t -c "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")"
  [[ "${existing}" == "0" ]] || die "target database ${NEW_DB} already has ${existing} tables — refusing to overwrite"

  echo
  echo "This stops the API and workers, copies Supabase -> ${PG_CONTAINER}, and switches the app."
  echo "Supabase is not modified. Type CUTOVER to continue:"
  read -r answer
  [[ "${answer}" == "CUTOVER" ]] || die "aborted"

  # Record what to restart (and roll back to) before anything is stopped.
  docker inspect -f '{{.Config.Image}}' hadha-backend    > "${WORK}/images.backend"
  docker inspect -f '{{.Config.Image}}' hadha-storefront > "${WORK}/images.storefront"
  docker inspect -f '{{.Config.Image}}' hadha-admin      > "${WORK}/images.admin"
  cp -p "${ENV_FILE}" "${ENV_FILE}.pre-pg-cutover.${ts}"

  log "safety: full Supabase backup (all schemas)"
  dump_source "full-supabase-${ts}.dump"

  log "maintenance: stopping writers"
  ROLLBACK_ARMED=1   # from here on any failure puts the app back on Supabase
  docker stop -t 30 "${APP_CONTAINERS[@]}" >/dev/null
  sleep 3

  log "final dump (public schema)"
  dump_source "final-${ts}.dump" -n public

  log "restoring into ${NEW_DB}"
  make_extensions "${NEW_DB}"
  restore_into "${NEW_DB}" "final-${ts}.dump"

  log "verifying exact equality with Supabase"
  fingerprint_src > "${WORK}/fp-src.txt"
  fingerprint_new "${NEW_DB}" > "${WORK}/fp-new.txt"
  diff -u "${WORK}/fp-src.txt" "${WORK}/fp-new.txt" || die "source and copy differ"
  log "  identical ($(wc -l < "${WORK}/fp-src.txt") facts)"
  psql_new "${NEW_DB}" -q -c 'ANALYZE'

  log "switching ${ENV_FILE}"
  env_set DATABASE_URL "$(new_db_url "${NEW_DB}" postgresql+asyncpg)" "${ENV_FILE}"
  env_set ALEMBIC_DATABASE_URL "$(new_db_url "${NEW_DB}" postgresql+psycopg)" "${ENV_FILE}"

  log "starting API and workers on the local database"
  recreate_app
  for _ in $(seq 1 36); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' hadha-backend 2>/dev/null || true)" == "healthy" ]] && break
    sleep 5
  done
  [[ "$(docker inspect -f '{{.State.Health.Status}}' hadha-backend)" == "healthy" ]] || die "backend not healthy after switch"
  app_smoke "${NEW_DB}"

  ROLLBACK_ARMED=0
  log "CUTOVER COMPLETE in $(( $(date +%s) - t0 ))s. Supabase left untouched as fallback."
  log "Rollback (loses writes since now): db-cutover.sh rollback"
}

case "${1:-}" in
  rehearse) cmd_rehearse ;;
  cutover)  cmd_cutover ;;
  rollback) cmd_rollback ;;
  *) echo "usage: $0 rehearse|cutover|rollback" >&2; exit 2 ;;
esac
