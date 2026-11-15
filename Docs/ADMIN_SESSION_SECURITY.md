# Admin Session & 2FA Security

Reference for the admin authentication/2FA/session system: first-party auth
(HttpOnly-cookie sessions, HS256 access token) + FastAPI backend enforcement + a server-side `AdminSession` table. This
document does not change the architecture described in the original 2FA
audit — it covers the operational hygiene and dashboard features layered on
top of it.

## AdminSession lifecycle

`AdminSession` (`app/modules/profiles/models.py`) is the single source of
truth for whether a given login session has completed 2FA. One row exists
per (admin user, login session) — the session id is the `sid` claim of the
signed access token (`auth_sessions.id`) and cannot be forged by the client.

| Column | Purpose |
|---|---|
| `supabase_session_id` | Correlates the row to one login session (`auth_sessions.id`, the token's `sid` claim); stable across access-token refresh. The column name is historical |
| `is_2fa_verified` / `verified_at` / `expires_at` | Set by `POST /auth/admin/2fa/validate`; `expires_at` is `verified_at + 12h` (absolute, not idle-based) |
| `last_activity_at` / `last_seen_ip` / `last_seen_user_agent` | Throttled activity tracking (see below) for the security dashboard |
| `device_name` / `browser_name` / `os_name` | Best-effort, regex-based UA parsing — no external dependency |

**Row creation**: a lightweight, `is_2fa_verified=False` row is created (or touched) for *every* admin login — 2FA-enabled or not — via `AuthService.ensure_admin_session_tracked`, invoked through the shared `AuthService.track_admin_login_if_new_session` helper. That helper is called from `GET /me` (`profiles/router.py`), the actual endpoint the admin frontend calls once per page load — not `/auth/verify-token`, which the frontend never calls and which only exists as a harmless no-op integration point for other clients that might use it per its own docs. Session tracking and the `admin_login` audit event are deduped independently via two separate Redis keys (`admin:session_tracked:{session_id}` and `admin:login_logged:{session_id}`) so each side effect fires exactly once per session lifetime regardless of which one existed first. This exists purely so the security dashboard's Active Sessions list reflects "you're logged in here" universally, not only for 2FA-tracked sessions — `require_admin`/`require_super_admin` still skip the actual verification check entirely when `Admin2FA.is_enabled` is false, so this row carries no security weight for non-2FA accounts (see "Active Sessions without 2FA" below). A successful `/2fa/validate` (`AuthService.mark_admin_session_2fa_verified`) later upgrades this same row to `is_2fa_verified=True` — `ensure_admin_session_tracked`'s own upsert never touches `is_2fa_verified`/`verified_at`/`expires_at` on conflict, so a plain login-presence touch can never regress an already-verified session back to unverified.

Creation/update is a single `INSERT ... ON CONFLICT (user_id, supabase_session_id) DO UPDATE` (Postgres upsert), not a SELECT followed by a Python `if record: update() else: insert()`. The latter has a genuine race: two concurrent successful validations for the same session could both see "no row yet" and both attempt an `INSERT`, and the second would raise an unhandled `IntegrityError` against the unique index. The upsert makes the decision atomic at the database level regardless of concurrency. TOTP replay protection (`last_used_counter`) has the same shape for the same reason — a single conditional `UPDATE ... WHERE last_used_counter IS NULL OR last_used_counter < :new`, checked by `rowcount`, not a Python read-then-compare.

**Row deletion** (any of):
- Logout (`POST /auth/logout`) — deletes only that one session's row.
- Force-logout (`POST /auth/force-logout/{user_id}`, super-admin only) — deletes every row for the target user and revokes all their login sessions.
- 2FA disabled or reset (self-service or super-admin force-reset) — deletes every row for the user, so a stale "verified" row can't silently satisfy the gate again the moment 2FA is re-enabled.
- **Admin deactivation** (`ProfileService.set_status(is_active=False)`) — deletes every row for the user. Deactivated accounts are already rejected earlier, at `get_current_user` (before they'd ever reach the 2FA gate); this is pure hygiene plus an audit trail (`admin_sessions_revoked_on_deactivation`), not a new authorization check.
- **Hourly cleanup worker** (see below).
- **User-initiated revocation** from the security dashboard (see below).

## Session expiration & cleanup worker

Expired sessions (`expires_at` in the past) are already rejected at request
time by `AuthService.is_admin_session_2fa_verified` — the cleanup worker
never affects correctness, only table size.

`app/workers/admin_session_cleanup.py`, registered in
`app/workers/queue.py` alongside the existing APScheduler jobs
(`reservation_expiry`, `cms_publish`, `media_generation`,
`notification_retry`, `partition_manager`):

- Runs every hour (`IntervalTrigger`, `max_instances=1`, `coalesce=True`).
- Single `DELETE ... WHERE expires_at < NOW() - INTERVAL '1 hour'` — the 1h grace window is `ADMIN_SESSION_CLEANUP_GRACE` in `auth/service.py`.
- Logs the count deleted (`admin_sessions_cleaned_up`); a no-op run logs at debug level.
- Idempotent — running it twice with nothing new expired deletes zero rows the second time.

Migration `0049_admin_session_activity_tracking` also runs a one-time deploy
cleanup (same predicate, plus rows that never got verified and are >24h old)
so environments upgrading from earlier revisions start clean.

## Activity tracking

`AuthService.touch_admin_session_activity`, called from
`app.core.dependencies._ensure_2fa_session` on every already-2FA-verified
admin request — **never** on requests from accounts without 2FA enabled
(there's no row to update), and throttled to once per
`ADMIN_SESSION_ACTIVITY_THROTTLE` (5 minutes) per session so it isn't a
write on every single request. Failures are swallowed (best-effort) so a
Postgres hiccup never blocks the actual request.

## Client IP capture

Every place that records or reasons about a client IP — `AdminSession.ip_address`/`last_seen_ip`, audit log entries, `is_new_device`'s location check — goes through `app.middleware.rate_limit.get_client_ip` (the same reverse-proxy-aware helper the rate limiter has always used: `X-Real-IP` → `X-Forwarded-For` → raw socket address), never `request.client.host` directly. Behind any reverse proxy (Nginx, Cloudflare, the Docker Compose setup used in dev), `request.client.host` is the proxy's own address for every request — using it directly would silently record the same IP for every admin regardless of where they actually connected from, making `is_new_device`'s location check permanently blind (every login "looks like" a recognized IP) and destroying the audit trail's forensic value for incident response. This was an actual bug in the auth router and dependency chain, not a hypothetical — fixed by reusing the existing helper rather than adding a second IP-extraction implementation.

## Security dashboard

`Settings → Security` (`admin.settings.security.tsx`):

- **Two-Factor Authentication** — existing setup/status/disable/regenerate card, unchanged.
- **Active Sessions** (`ActiveSessionsPanel`) — every `AdminSession` row for the current user (2FA-tracked or not, see above), current session flagged, device/browser/OS/IP/last-activity/expiry shown. Actions: log out one other session, log out all other sessions, log out everywhere (including the current tab — full sign-out, redirects to `/admin/login`).
- **Recent Activity** (`LoginHistoryPanel`) — reuses the existing `/admin/audit-logs` endpoint filtered to the current admin's own `actor_id`, paginated. No second logging/listing system — every event below is already written through the existing `AuditService`.

### Revoking sessions

Revoking a session (single, "others" or all) revokes the underlying login session as well as deleting the local `AdminSession` row: the `auth_sessions` row is marked revoked (no refresh is possible any more) and the session id is put on a Redis deny-list, so the access token already in that browser stops working on its next request. This holds for accounts with and without 2FA. If Redis is unavailable the deny-list write is skipped (fail-open), so an already-issued access token can stay valid until it expires (at most `AUTH_ACCESS_TTL_SECONDS`, 15 minutes); the session can no longer be refreshed.

## Session revocation endpoints

All under `/auth/admin/sessions`, rate-limited (`rate_limit_admin_sessions`, 30/min), require `require_admin` (2FA-aware):

| Endpoint | Effect |
|---|---|
| `GET /auth/admin/sessions` | List this user's sessions, `is_current` flagged against the request's own `session_id` |
| `DELETE /auth/admin/sessions/{session_row_id}` | Revoke one session by its row id. Ownership-checked (404 if it doesn't belong to the caller — same response whether the id is someone else's or simply doesn't exist, no existence leak). **Refuses to delete the caller's own current session** (`403 CANNOT_REVOKE_CURRENT_SESSION`) — that must go through `/revoke-all` or `/logout` instead, so a session can't be torn down by accident via what looks like "log out one other device". |
| `POST /auth/admin/sessions/revoke-others` | Revoke every session except the caller's own |
| `POST /auth/admin/sessions/revoke-all` | Revoke every session of this user, including the caller's own, and clear the caller's cookies |

`session_row_id` is typed as `uuid.UUID` in the route signature (as are the
`user_id` path params on `force_logout` and `force_reset_2fa`) — FastAPI
rejects a malformed value with a clean `422` before it ever reaches a query.
Passing a non-UUID string straight into a query against a native `uuid`
column would otherwise surface as an uncaught `asyncpg` type-cast error
(`500`), a real input-validation gap fixed in this pass.

Repeated `DELETE` calls for an already-deleted session id are safe —
standard idempotent-DELETE semantics: 200 the first time, 404 every time
after (the row is equally gone either way, no side effects on retry). 

## Login history / audit flow

Every event below already exists as a distinct `action` on the shared
`audit_logs` table (`AuditService.log`, same infrastructure as
role-changes/status-changes elsewhere in the app — no separate table):

`admin_login` (deduped per `session_id` via a Redis key so page reloads don't spam it), `admin_logout`, `admin_force_logout`, `2fa_setup_initiated`, `2fa_enabled`, `2fa_verify_success` (carries `metadata.method` = `"totp"` or `"backup_code"`), `2fa_backup_code_used` (fired alongside `2fa_verify_success` specifically when a backup code — not a TOTP code — matched), `2fa_verify_failed`, `2fa_locked_out`, `2fa_disabled`, `2fa_backup_codes_regenerated`, `2fa_force_reset`, `admin_session_revoked`, `admin_sessions_revoked_others`, `admin_sessions_revoked_all`, `admin_sessions_revoked_on_deactivation`.

The cleanup worker deliberately does **not** write to `audit_logs` — it only
logs to the application logger (`admin_sessions_cleaned_up`), since it's a
system/background action, not an actor-driven security event. This keeps
the audit table free of hourly noise regardless of how many sessions get
swept.

Query any of it directly via `GET /admin/audit-logs` (`actor_id`, `action`,
`resource_type`, `date_from`/`date_to`, pagination — all pre-existing
filters, none added for this feature).

## Login notifications (optional, off by default)

Gated behind a single feature flag, `admin_login_notifications`, managed the
same way as every other flag (`Settings → Feature Flags` — no separate
config surface). When enabled, `AuthService.is_new_device` fires an email
via the existing Resend/notification dispatcher
(`NotificationDispatcher.send_email`) for:

- A new sign-in from an unrecognized IP **or** an unrecognized browser+OS combination.
- 2FA disabled.
- Backup codes regenerated.

`is_new_device` checks IP and device recognition as two **independent**
signals (two separate queries), not one combined condition — a login from a
brand-new IP still counts as new even if the browser/OS matches an existing
session, and vice versa. (An earlier single-query version conflated the two
via one `OR`'d clause, which by De Morgan's law only fired when *both*
signals were unrecognized — under-notifying genuine new-location logins
from an already-seen browser. Fixed and covered by
`test_is_new_device_true_when_ip_new_even_if_device_recognized`.)

Both the raw `User-Agent` header and the value written to
`last_seen_user_agent`/`user_agent` are capped at `MAX_USER_AGENT_LENGTH`
(512 chars, `_sanitize_user_agent` in `auth/service.py`) before they ever
reach the parsing regexes or a database write — real UA strings top out
around 200-300 chars, so anything far longer is either malformed or a
probe, and the Text columns would otherwise accept it unbounded.

Delivery failures never propagate — a notification-send error must never
block the request that triggered it — but they are logged
(`admin_security_notification_failed`, with `exc_info`), not silently
swallowed. A bare `except Exception: pass` would let every notification
quietly stop working (a Resend outage, a bad flag value, a typo) with no
way to notice; the fix keeps the "never block/never raise" guarantee while
staying observable.

Also fires (only when there was actually something to revoke, so routine
single-device logout hygiene doesn't spam an email) on
`POST /auth/admin/sessions/revoke-others`. `revoke-all` deliberately does
**not** send one — the caller who just clicked it already knows, since it
signs them out of their own current tab immediately.

This is a foundation, not a full templating
system: plain-text-ish HTML, no per-event customization UI yet (see
Recommendations in the original audit for further hardening ideas —
WebAuthn/FIDO2, idle timeout, device binding — none of which are
implemented here).

## Trusted reverse proxy

`get_client_ip` (`app/middleware/rate_limit.py`) only honors `X-Real-IP`/`X-Forwarded-For` when the request's *direct* TCP peer (`request.client.host`) is itself a recognized reverse proxy — private/loopback ranges by default, plus anything in `TRUSTED_PROXY_IPS` (comma-separated). If the API is ever reachable directly (bypassing the reverse proxy) from an address outside that set, forwarding headers are ignored entirely and the real socket peer is used. Without this, any client that could reach the API directly could spoof its own rate-limit key, its own audit-log IP, and defeat `is_new_device`'s location check by claiming to be an IP it has "seen before."

## Access token verification

`verify_access_token` (`app/core/security.py`) checks the HS256 signature (key derived from `SECRET_KEY`), issuer, audience, expiry and the presence of `sub`/`sid`; there is no external key fetch, so no upstream outage can affect verification. Revocation is checked separately against the Redis deny-list (`is_session_revoked`) by the request dependency.

## Logout revocation is best-effort

`AuthService.logout` (also used by `force_logout` and `revoke-all`) revokes the user's login sessions inside a SAVEPOINT and logs a warning on failure rather than propagating. Routers call this *before* clearing the local `AdminSession` row, so the local security state (what our own `require_admin` gate checks) clears even if the revocation itself fails.

## Replay vs. wrong-code in the audit trail

`validate_2fa_detailed` now returns `"replay"` (not a bare failure) when a TOTP code was cryptographically valid but already consumed this time-step, and the `2fa_verify_failed` audit event carries `metadata.reason` accordingly (`"replay"` vs `"invalid_code"`). A replayed code is a materially different signal — evidence of a captured/intercepted code — from a random wrong guess, and is now distinguishable without cross-referencing anything else.

## JWT / rate-limit observability

`verify_access_token` logs a warning (never the raw token — only the failure reason) on every rejection path: invalid or malformed token, bad signature, wrong issuer/audience, missing claims. Expired-token rejections log at `info` rather than `warning`, since tokens naturally and routinely expire — that alone isn't suspicious the way a signature/format failure is. `check_rate_limit` now logs `rate_limit_exceeded` (key prefix, path, IP, count, limit) when a client is actually throttled — previously the only rate-limit log line fired when *Redis itself* was unavailable, never when a client actually hit the limit.

## Time synchronization

TOTP verification and the replay-protection counter both derive from the app server's wall clock (`time.time()`), same as the TOTP standard requires. A **backward** jump in the server clock (e.g. an uncorrected VM/container clock issue resolved by an NTP step rather than a gradual slew) could cause `_current_totp_counter()` to compute a value at or below a previously-stored `last_used_counter`, which the atomic replay check would then treat as an already-consumed step — every subsequent otherwise-valid code would be rejected for every 2FA-enabled admin until the clock caught back up. This requires an actual clock regression, not routine drift (which pyotp's `valid_window=1` already tolerates, and which any correctly configured NTP client corrects via slewing rather than stepping). Existing recovery path if it ever happens: a super-admin's `force_reset_2fa` deletes the affected user's `Admin2FA` row entirely (clearing `last_used_counter`), unblocking them on next enrollment. Recommendation: monitor server clock health / NTP sync status as an infrastructure SLO; no code change is warranted for what is fundamentally an infrastructure correctness requirement, not an application bug — session expiry and the cleanup worker's cutoff are unaffected since both write and compare using the same app-server clock (never mixed with Postgres's own `NOW()`), so they stay internally consistent regardless of *absolute* clock correctness.

## Database and Redis failure modes (reviewed, no gaps found)

- **Database outage/restart, deadlocks, serialization failures**: every write goes through the existing `get_db()` session pattern (commit on success, rollback on any exception) — a failure at any point rolls back the whole transaction, so no partial `AdminSession`/`Admin2FA` state can persist. The new atomic upsert/conditional-update (this system's own writes) can't deadlock against itself: a single-table, single-row conflict target just serializes concurrent writers, it doesn't cross-lock. Uncaught failures surface as a generic 500 via the existing global exception handler — not a security gap, since nothing partially authenticates.
- **Redis outage**: confirmed intentional, and correct per this review's own requirement ("Redis outages must not block authentication"). `is_admin_session_2fa_verified` — the actual security gate — has **no Redis dependency at all**; only the secondary hardening layers (per-IP rate limiting, per-account lockout, the admin-login audit dedup key) degrade during a Redis outage, and all fail *open* by design, matching `safe_redis_get`/`safe_redis_setex`'s existing circuit-breaker behavior. The accepted tradeoff: brute-force protection is temporarily reduced during a genuine Redis outage, which is strictly better than the alternative (failing closed and locking out every admin, including legitimate ones, on any Redis blip). One minor, non-security side effect: the admin-login dedup key can't function without Redis, so `admin_login` audit events log once per `GET /me` call instead of once per session during an outage — audit-log volume increases slightly, nothing breaks.

## Long-term maintenance and retention

- `admin_sessions` stays small by construction — bounded by (admin count × active sessions), pruned by six independent deletion paths plus the hourly cleanup worker. No retention policy needed.
- `admin_2fa` — one row per 2FA-enabled admin. Bounded, no growth concern.
- `audit_logs` — already monthly-partitioned (`partition_manager` worker, confirmed) for query performance, but **that worker only creates new partitions, never drops old ones** — the table grows without bound indefinitely. This is a genuine long-term operational item, but retention period (30 days? 1 year? 7 years for compliance?) is a business/compliance decision this review isn't positioned to make unilaterally, and auto-deleting security audit data by default would be a worse mistake than leaving it growing. **Recommendation**: decide a retention window with whoever owns compliance requirements, then add a `DROP TABLE audit_logs_YYYY_MM` (or move-to-cold-storage) step to `partition_manager` for partitions older than that window — the partitioning scheme already makes this a cheap, single-statement-per-month operation once the policy is decided.

## Disaster recovery and key rotation

`ENCRYPTION_KEY` (Fernet, encrypts `Admin2FA.totp_secret`) now supports safe rotation via `MultiFernet`: `_get_fernet()` builds a `MultiFernet` from `[ENCRYPTION_KEY, *ENCRYPTION_KEY_LEGACY.split(",")]` — encrypts with the primary (first) key, decrypts with any key in the list. **Rotation runbook**: generate a new key → set it as `ENCRYPTION_KEY` → move the old key into `ENCRYPTION_KEY_LEGACY` → deploy. Every existing encrypted `totp_secret` keeps decrypting correctly with zero migration step and zero admin re-enrollment; new/re-saved secrets encrypt under the new key going forward. Drop an old key from `ENCRYPTION_KEY_LEGACY` only once nothing still depends on it.

**Key loss** (as opposed to rotation) is unrecoverable by design — if `ENCRYPTION_KEY` (and every legacy key) is genuinely lost, every existing `totp_secret` is permanently undecryptable, since Fernet is symmetric encryption with no recovery mechanism. The only path back is per-user: a super-admin's `force_reset_2fa` (already exists) clears the affected user's `Admin2FA` row, forcing re-enrollment. There is no bulk "reset 2FA for every admin" endpoint today; if a full key loss ever occurs, restoring access is a manual per-admin operation with the tooling that exists. Treat `ENCRYPTION_KEY`/`ENCRYPTION_KEY_LEGACY` with the same backup rigor as the database itself (secrets-manager backup, not just an environment variable on one box).
