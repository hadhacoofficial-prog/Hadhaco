# Security audit remediation (2026-10-09)

Source: `security-audit/run-1/` (git-ignored; REPORT.md, FINDINGS-DETAIL.md, NEEDS-VALIDATION.md).
No production data or database was modified; the only DB change is the additive, idempotent
migration `0067_supabase_data_api_hardening` (run `alembic upgrade head` on deploy).

| Finding | Fix |
|---|---|
| 2FA setup replaced an enabled factor | `AuthService.setup_2fa` raises 409 when a factor is enabled (disable it first with a valid code) |
| Razorpay signature not bound to order | `verify_and_fulfill` requires `payload.razorpay_order_id == order.razorpay_order_id`; duplicate payment id on another order is rejected |
| SSE broadcast leaked email/phone | per-event allowlist in `core/events.py` (`_SSE_PUBLIC_FIELDS`) |
| Role change with no ceiling | super_admin only, never self; `set_status` requires actor rank > target rank, never self |
| `cancel_order` after dispatch | blocked once `fulfillment_status != pending` |
| Template editor stored XSS | preview sanitised with DOMPurify (`admin/src/lib/sanitizeHtml.ts`) |
| Logo URL SSRF | `core/safe_fetch.py` (https only, public IPs, pinned IP, no redirects, image-only, 2 MB cap); schema validation on write |
| Analytics unbounded payload | field/size limits in schema + nginx 16k body cap on that route |
| Cart ownership / item binding | owner or X-Session-ID required; item must belong to the cart |
| Support internal notes | stripped for customers (`customer_view`) |
| Coupon audience/context only in preview | `apply_and_reserve` now enforces the same checks with server-derived context; phone audience fails closed |
| Invoice markup injection | address/company text XML-escaped; invoice objects use an unguessable key, no public URL persisted |
| Unbounded image decode | `assert_pixel_budget` (50 MP) before any decode; CMS upload folder/extension validated |
| JWKS refetch DoS | 10 s refetch cooldown; fast path without lock |
| Profiler path cardinality | route template keys + 500-entry cap |
| Audit-log attribution / X-Request-ID | unverified JWT sub no longer logged as actor; request id validated; peer-aware client IP |
| uvicorn trusted all forwarders | `--forwarded-allow-ips` limited to private ranges; nginx sets `X-Forwarded-For $remote_addr` |
| WhatsApp webhook empty secret | signature check fails closed when `WHATSAPP_WEBHOOK_SECRET` is empty (set it in production or delivery callbacks are rejected) |
| payment.failed then late capture | reservations released-and-never-completed now route to `refund_required` |
| Logout revocation route | revokes `auth.sessions` rows directly (best-effort, savepoint) |
| Returns restock trust | items must belong to the order, quantity capped, row-locked status update; fixed `admin["sub"]` TypeError in returns and fraud routers |
| nginx exposed `/metrics`, `/health/metrics`, `/health/ready` | 404 on the public vhost (Prometheus scrapes internally) |
| Prod workflow dispatch from any ref | job-level `github.ref == refs/heads/main`, `image_tag` via env + format check |
| Supabase RLS/grants/views | migration 0067: security_invoker views, revoke anon/authenticated on `public`, RLS on all tables, trigger blocking role/is_active changes from Data API roles |

## Deliberately not changed
- **CSP `unsafe-inline`/`unsafe-eval`** (storefront/admin nginx): removing needs nonce support in the SSR bundle and browser verification; not safe to change blind. The XSS sink it amplified is fixed.
- Third-party Actions pinned by tag, mutable image tags, dev `docker-compose.yml` default credentials: hardening items listed in REPORT.md.
- Customer `user_id` remains in SSE payloads (the client scopes cache invalidation with it); a per-user channel is the long-term design.

## Operator checks (cannot be verified from the repo)
1. Set `WHATSAPP_WEBHOOK_SECRET` in `.env.production`.
2. After deploy, confirm in Supabase: anon/authenticated hold no privileges on `public` tables/views.
3. GitHub: restrict the `production` environment to `main` with required reviewers.
4. Cloudflare R2: confirm the `invoices/` prefix is not publicly served (old invoices keep their old keys).
