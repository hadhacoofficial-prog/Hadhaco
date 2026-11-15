"""
First-party identity: password login, rotating sessions, email-verification and
password-reset tokens, and Google account linking.

Pure persistence/logic — no HTTP concerns. Routers own cookies, e-mail dispatch
and Redis profile-cache invalidation. Methods flush but never commit, except
`refresh_session`'s reuse path, which must persist a revocation even though it
raises (the request-scoped transaction would otherwise roll it back).
"""

from __future__ import annotations

import ipaddress
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import UserRole
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    RateLimitError,
    ValidationError,
)
from app.core.redis import safe_redis_delete, safe_redis_get
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    make_csrf_token,
    mark_sessions_revoked,
    verify_password,
)
from app.modules.auth.models import (
    AuthSession,
    AuthToken,
    OAuthIdentity,
    UserCredential,
)
from app.modules.profiles.models import Profile

log = structlog.get_logger(__name__)

TOKEN_EMAIL_VERIFY = "email_verify"
TOKEN_PASSWORD_RESET = "password_reset"

# Brute-force lockout, independent of the per-IP rate limiter. Per (email, IP)
# so a stranger cannot lock a known address out from elsewhere with 5 guesses;
# the higher per-email cap still stops a distributed guesser.
LOGIN_LOCKOUT_THRESHOLD = 5
LOGIN_EMAIL_LOCKOUT_THRESHOLD = 25
LOGIN_LOCKOUT_WINDOW_SECONDS = 15 * 60

MAX_USER_AGENT_LENGTH = 512


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


def _safe_ip(ip: str | None) -> str | None:
    """INET column: store only a parseable address (never raise on odd proxies)."""
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def _lockout_key(email: str, ip: str | None = None) -> str:
    digest = hash_opaque_token(f"{email}|{ip}" if ip else email)[:32]
    return f"auth:login_fail:{digest}"


async def _bump_failures(redis: aioredis.Redis, key: str) -> None:
    """Atomic INCR + window start (EXPIRE ... NX keeps the original window).
    Fail-open like the other Redis helpers: a Redis outage must not block login."""
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, LOGIN_LOCKOUT_WINDOW_SECONDS, nx=True)
        await pipe.execute()
    except Exception:
        log.warning("login_lockout_redis_unavailable", exc_info=True)


@dataclass(frozen=True)
class IssuedSession:
    profile: Profile
    session_id: str
    access_token: str
    access_ttl: int
    # None when the caller's refresh cookie is already the current one (a
    # grace-window refresh) — the cookie must then be left untouched.
    refresh_token: str | None
    refresh_ttl: int
    csrf_token: str


class IdentityService:
    # ── Lookups ──────────────────────────────────────────────────────────────

    async def _profile_by_email(self, db: AsyncSession, email: str) -> Profile | None:
        result = await db.execute(
            select(Profile).where(
                Profile.email == normalize_email(email), Profile.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def _deleted_profile_exists(self, db: AsyncSession, email: str) -> bool:
        """profiles.email is unique across soft-deleted rows, so a closed
        account's address cannot be re-registered; say so instead of failing
        with a bare conflict."""
        result = await db.execute(
            select(Profile.id).where(
                Profile.email == normalize_email(email), Profile.deleted_at.is_not(None)
            )
        )
        return result.first() is not None

    async def _profile_by_id(
        self, db: AsyncSession, user_id: uuid.UUID | str
    ) -> Profile | None:
        result = await db.execute(
            select(Profile).where(Profile.id == user_id, Profile.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_credential(
        self, db: AsyncSession, user_id: uuid.UUID | str, *, for_update: bool = False
    ) -> UserCredential | None:
        stmt = select(UserCredential).where(UserCredential.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await db.execute(stmt)).scalar_one_or_none()

    # ── Registration ─────────────────────────────────────────────────────────

    async def register(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
        full_name: str | None,
        binder: str | None = None,
    ) -> tuple[Profile, str]:
        """Create an unverified password account. Returns (profile, raw verify token).

        An existing *unverified, password-only* registration is taken over by
        the new one (so a squatter who typed someone else's address cannot
        block the real owner); anything else is a conflict.
        """
        email = normalize_email(email)
        name = (full_name or "").strip() or None
        password_hash = await hash_password(password)
        existing = await self._profile_by_email(db, email)
        if existing is None and await self._deleted_profile_exists(db, email):
            raise ConflictError(
                "This account has been closed. Please contact support.",
                code="ACCOUNT_DELETED",
            )

        if existing is not None:
            cred = await self.get_credential(db, existing.id, for_update=True)
            has_identity = (
                await db.execute(
                    select(OAuthIdentity.id).where(OAuthIdentity.user_id == existing.id)
                )
            ).first() is not None
            if (
                cred is None
                or cred.email_verified_at is not None
                or has_identity
                or not existing.is_active
            ):
                raise ConflictError(
                    "An account with this email already exists.", code="EMAIL_EXISTS"
                )
            cred.password_hash = password_hash
            cred.password_changed_at = _now()
            if name:
                existing.full_name = name
            await db.flush()
            profile = existing
        else:
            profile = Profile(
                id=uuid.uuid4(),
                email=email,
                full_name=name or email.split("@", 1)[0],
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=False,
            )
            db.add(profile)
            try:
                await db.flush()
            except IntegrityError as exc:
                raise ConflictError(
                    "An account with this email already exists.", code="EMAIL_EXISTS"
                ) from exc
            db.add(
                UserCredential(
                    user_id=profile.id,
                    password_hash=password_hash,
                    password_changed_at=_now(),
                )
            )
            await db.flush()

        token = await self._create_token(
            db,
            profile.id,
            TOKEN_EMAIL_VERIFY,
            timedelta(hours=settings.AUTH_VERIFY_TTL_HOURS),
            binder=binder,
        )
        return profile, token

    # ── Password login ───────────────────────────────────────────────────────

    async def authenticate_password(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        *,
        email: str,
        password: str,
        ip: str | None = None,
    ) -> Profile:
        email = normalize_email(email)
        key = _lockout_key(email, ip)
        email_key = _lockout_key(email)
        raw = await safe_redis_get(redis, key)
        raw_email = await safe_redis_get(redis, email_key)
        if (raw is not None and int(raw) >= LOGIN_LOCKOUT_THRESHOLD) or (
            raw_email is not None and int(raw_email) >= LOGIN_EMAIL_LOCKOUT_THRESHOLD
        ):
            raise RateLimitError(
                "Too many failed sign-in attempts. Try again in a few minutes.",
                code="ACCOUNT_LOCKED",
            )

        profile = await self._profile_by_email(db, email)
        cred = await self.get_credential(db, profile.id) if profile else None
        # Always runs one bcrypt comparison, so timing does not reveal whether
        # the account exists.
        ok = await verify_password(password, cred.password_hash if cred else None)
        if not ok or profile is None or cred is None:
            await _bump_failures(redis, key)
            await _bump_failures(redis, email_key)
            raise AuthenticationError(
                "Invalid email or password", code="INVALID_CREDENTIALS"
            )

        # Checked only after the password is proven, so these states are not
        # an account-enumeration oracle.
        if not profile.is_active:
            raise AuthorizationError("Account is inactive", code="ACCOUNT_INACTIVE")
        if cred.email_verified_at is None:
            raise AuthorizationError(
                "Please verify your email address before signing in.",
                code="EMAIL_NOT_VERIFIED",
            )
        await safe_redis_delete(redis, key)
        return profile

    # ── Sessions ─────────────────────────────────────────────────────────────

    def _access_for(self, profile: Profile, session_id: str) -> tuple[str, int]:
        return create_access_token(
            user_id=str(profile.id),
            email=profile.email,
            role=profile.role,
            session_id=session_id,
        )

    @staticmethod
    def _refresh_ttl_seconds(surface: str) -> int:
        days = (
            settings.AUTH_ADMIN_REFRESH_TTL_DAYS
            if surface == "admin"
            else settings.AUTH_REFRESH_TTL_DAYS
        )
        return days * 24 * 3600

    async def issue_session(
        self,
        db: AsyncSession,
        profile: Profile,
        *,
        surface: str,
        ip: str | None,
        user_agent: str | None,
    ) -> IssuedSession:
        refresh = generate_opaque_token()
        ttl = self._refresh_ttl_seconds(surface)
        row = AuthSession(
            id=uuid.uuid4(),
            user_id=profile.id,
            refresh_hash=hash_opaque_token(refresh),
            surface=surface,
            ip_address=_safe_ip(ip),
            user_agent=(user_agent or "")[:MAX_USER_AGENT_LENGTH] or None,
            expires_at=_now() + timedelta(seconds=ttl),
        )
        db.add(row)
        await db.flush()
        sid = str(row.id)
        access, access_ttl = self._access_for(profile, sid)
        return IssuedSession(
            profile=profile,
            session_id=sid,
            access_token=access,
            access_ttl=access_ttl,
            refresh_token=refresh,
            refresh_ttl=ttl,
            csrf_token=make_csrf_token(sid),
        )

    async def refresh_session(
        self, db: AsyncSession, *, refresh_token: str
    ) -> IssuedSession:
        """Exchange a refresh token for a new access token, rotating the refresh
        token. A token that was already rotated away is tolerated for
        AUTH_REFRESH_GRACE_SECONDS (parallel tabs); presented later it means the
        token leaked, so the whole session is revoked."""
        now = _now()
        digest = hash_opaque_token(refresh_token)

        row = (
            await db.execute(
                select(AuthSession)
                .where(AuthSession.refresh_hash == digest)
                .with_for_update()
            )
        ).scalar_one_or_none()
        new_refresh: str | None = None

        if row is not None:
            self._assert_live(row, now)
            new_refresh = generate_opaque_token()
            row.prev_refresh_hash = row.refresh_hash
            row.refresh_hash = hash_opaque_token(new_refresh)
            row.rotated_at = now
        else:
            row = (
                await db.execute(
                    select(AuthSession)
                    .where(AuthSession.prev_refresh_hash == digest)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                # Not a known token at all — possibly one rotated away more than
                # one step ago by a racing tab. Distinct code so the caller does
                # NOT clear the (possibly newer) cookies it still holds.
                raise AuthenticationError("Invalid session", code="SESSION_UNKNOWN")
            self._assert_live(row, now)
            within_grace = row.rotated_at is not None and (
                now - row.rotated_at
            ) <= timedelta(seconds=settings.AUTH_REFRESH_GRACE_SECONDS)
            if not within_grace:
                log.warning(
                    "auth_refresh_reuse_detected",
                    session_id=str(row.id),
                    user_id=str(row.user_id),
                )
                row.revoked_at = now
                await db.commit()
                await mark_sessions_revoked([str(row.id)])
                raise AuthenticationError("Invalid session", code="SESSION_INVALID")

        profile = await self._profile_by_id(db, row.user_id)
        if profile is None or not profile.is_active:
            row.revoked_at = now
            await db.commit()
            await mark_sessions_revoked([str(row.id)])
            raise AuthenticationError("Invalid session", code="SESSION_INVALID")

        row.last_used_at = now
        sid = str(row.id)
        access, access_ttl = self._access_for(profile, sid)
        return IssuedSession(
            profile=profile,
            session_id=sid,
            access_token=access,
            access_ttl=access_ttl,
            refresh_token=new_refresh,
            refresh_ttl=self._refresh_ttl_seconds(row.surface),
            csrf_token=make_csrf_token(sid),
        )

    @staticmethod
    def _assert_live(row: AuthSession, now: datetime) -> None:
        if row.revoked_at is not None or row.expires_at <= now:
            raise AuthenticationError("Session expired", code="SESSION_EXPIRED")

    async def session_for_refresh(
        self, db: AsyncSession, refresh_token: str
    ) -> AuthSession | None:
        digest = hash_opaque_token(refresh_token)
        result = await db.execute(
            select(AuthSession).where(
                (AuthSession.refresh_hash == digest)
                | (AuthSession.prev_refresh_hash == digest)
            )
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, db: AsyncSession, session_id: str) -> None:
        await db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await mark_sessions_revoked([session_id])

    async def revoke_user_sessions(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | str,
        *,
        except_session_id: str | None = None,
    ) -> int:
        stmt = (
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now())
            .returning(AuthSession.id)
        )
        if except_session_id:
            stmt = stmt.where(AuthSession.id != except_session_id)
        ids = [str(r) for r in (await db.execute(stmt)).scalars().all()]
        await mark_sessions_revoked(ids)
        return len(ids)

    async def cleanup_expired_sessions(self, db: AsyncSession) -> int:
        """Drop sessions/tokens long past use (called by the existing hourly
        cleanup worker)."""
        cutoff = _now() - timedelta(days=1)
        s = await db.execute(
            delete(AuthSession).where(
                (AuthSession.expires_at < cutoff) | (AuthSession.revoked_at < cutoff)
            )
        )
        t = await db.execute(delete(AuthToken).where(AuthToken.expires_at < cutoff))
        return int(s.rowcount or 0) + int(t.rowcount or 0)

    # ── One-time tokens ──────────────────────────────────────────────────────

    async def _create_token(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        purpose: str,
        ttl: timedelta,
        *,
        binder: str | None = None,
    ) -> str:
        now = _now()
        # One live link per purpose: a new request invalidates older ones.
        await db.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw = generate_opaque_token()
        db.add(
            AuthToken(
                user_id=user_id,
                purpose=purpose,
                token_hash=hash_opaque_token(raw),
                binder_hash=hash_opaque_token(binder) if binder else None,
                expires_at=now + ttl,
            )
        )
        await db.flush()
        return raw

    async def _consume_token(
        self, db: AsyncSession, raw: str, purpose: str
    ) -> AuthToken:
        now = _now()
        token = (
            await db.execute(
                select(AuthToken)
                .where(
                    AuthToken.token_hash == hash_opaque_token(raw),
                    AuthToken.purpose == purpose,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if token is None or token.used_at is not None or token.expires_at <= now:
            raise ValidationError(
                "This link is invalid or has expired.", code="TOKEN_INVALID"
            )
        token.used_at = now
        return token

    # ── Email verification ───────────────────────────────────────────────────

    async def verify_email(
        self, db: AsyncSession, raw_token: str, binder: str | None
    ) -> Profile:
        """Confirm the mailbox. The password stored at registration was never
        proven to belong to the mailbox owner (anyone can register someone
        else's address), so it only survives when the link is opened in the
        browser that requested it. Otherwise (link opened elsewhere, e.g. a
        phone mail app) it is discarded and the verified owner sets their own
        — closing the "pre-hijack" where an attacker registers a victim's
        address with a password they know."""
        token = await self._consume_token(db, raw_token, TOKEN_EMAIL_VERIFY)
        profile = await self._profile_by_id(db, token.user_id)
        if profile is None or not profile.is_active:
            raise ValidationError(
                "This link is invalid or has expired.", code="TOKEN_INVALID"
            )
        same_browser = bool(
            binder
            and token.binder_hash
            and secrets.compare_digest(token.binder_hash, hash_opaque_token(binder))
        )
        if not same_browser:
            cred = await self.get_credential(db, profile.id, for_update=True)
            if cred is not None and cred.email_verified_at is None:
                cred.password_hash = None
                cred.password_changed_at = None
                await self.revoke_user_sessions(db, profile.id)
        await self._mark_verified(db, profile)
        return profile

    async def _mark_verified(self, db: AsyncSession, profile: Profile) -> None:
        cred = await self.get_credential(db, profile.id, for_update=True)
        if cred is None:
            db.add(UserCredential(user_id=profile.id, email_verified_at=_now()))
        elif cred.email_verified_at is None:
            cred.email_verified_at = _now()
        profile.is_verified = True
        await db.flush()

    async def issue_verification_token(
        self, db: AsyncSession, email: str, binder: str | None = None
    ) -> tuple[Profile, str] | None:
        """For "resend link": only for an unverified password account. Returns
        None (caller still answers 200) for anything else."""
        profile = await self._profile_by_email(db, email)
        if profile is None or not profile.is_active:
            return None
        cred = await self.get_credential(db, profile.id)
        if cred is None or cred.password_hash is None or cred.email_verified_at:
            return None
        raw = await self._create_token(
            db,
            profile.id,
            TOKEN_EMAIL_VERIFY,
            timedelta(hours=settings.AUTH_VERIFY_TTL_HOURS),
            binder=binder,
        )
        return profile, raw

    # ── Password reset / change ──────────────────────────────────────────────

    async def issue_reset_token(
        self, db: AsyncSession, email: str
    ) -> tuple[Profile, str] | None:
        profile = await self._profile_by_email(db, email)
        if profile is None or not profile.is_active:
            return None
        raw = await self._create_token(
            db,
            profile.id,
            TOKEN_PASSWORD_RESET,
            timedelta(minutes=settings.AUTH_RESET_TTL_MINUTES),
        )
        return profile, raw

    async def reset_password(
        self, db: AsyncSession, raw_token: str, new_password: str
    ) -> Profile:
        token = await self._consume_token(db, raw_token, TOKEN_PASSWORD_RESET)
        profile = await self._profile_by_id(db, token.user_id)
        if profile is None or not profile.is_active:
            raise ValidationError(
                "This link is invalid or has expired.", code="TOKEN_INVALID"
            )
        await self._set_password(db, profile, new_password)
        # Receiving the link proves control of the mailbox.
        await self._mark_verified(db, profile)
        await self.revoke_user_sessions(db, profile.id)
        return profile

    async def change_password(
        self,
        db: AsyncSession,
        profile: Profile,
        *,
        current_password: str | None,
        new_password: str,
        keep_session_id: str | None,
    ) -> None:
        cred = await self.get_credential(db, profile.id, for_update=True)
        if cred is not None and cred.password_hash is not None:
            if not current_password or not await verify_password(
                current_password, cred.password_hash
            ):
                raise ValidationError(
                    "Current password is incorrect.", code="INVALID_CURRENT_PASSWORD"
                )
        await self._set_password(db, profile, new_password)
        await self.revoke_user_sessions(
            db, profile.id, except_session_id=keep_session_id
        )

    async def has_password(self, db: AsyncSession, user_id: uuid.UUID | str) -> bool:
        cred = await self.get_credential(db, user_id)
        return cred is not None and cred.password_hash is not None

    async def _set_password(
        self, db: AsyncSession, profile: Profile, new_password: str
    ) -> None:
        hashed = await hash_password(new_password)
        cred = await self.get_credential(db, profile.id, for_update=True)
        if cred is None:
            db.add(
                UserCredential(
                    user_id=profile.id,
                    password_hash=hashed,
                    password_changed_at=_now(),
                )
            )
        else:
            cred.password_hash = hashed
            cred.password_changed_at = _now()
        await db.flush()

    # ── Google ───────────────────────────────────────────────────────────────

    async def login_with_google(
        self,
        db: AsyncSession,
        *,
        subject: str,
        email: str,
        email_verified: bool,
        full_name: str | None,
    ) -> Profile:
        if not email_verified:
            raise AuthenticationError(
                "Your Google email address is not verified.",
                code="GOOGLE_EMAIL_UNVERIFIED",
            )
        email = normalize_email(email)
        now = _now()

        identity = (
            await db.execute(
                select(OAuthIdentity).where(
                    OAuthIdentity.provider == "google",
                    OAuthIdentity.provider_subject == subject,
                )
            )
        ).scalar_one_or_none()

        if identity is not None:
            profile = await self._profile_by_id(db, identity.user_id)
            if profile is None:
                raise AuthenticationError("Account not found", code="ACCOUNT_NOT_FOUND")
            identity.last_login_at = now
        else:
            profile = await self._profile_by_email(db, email)
            if profile is None and await self._deleted_profile_exists(db, email):
                raise AuthorizationError(
                    "This account has been closed. Please contact support.",
                    code="ACCOUNT_DELETED",
                )
            if profile is None:
                profile = Profile(
                    id=uuid.uuid4(),
                    email=email,
                    full_name=(full_name or "").strip() or email.split("@", 1)[0],
                    role=UserRole.CUSTOMER,
                    is_active=True,
                    is_verified=True,
                )
                db.add(profile)
                try:
                    await db.flush()
                except IntegrityError as exc:
                    raise ConflictError(
                        "An account with this email already exists.",
                        code="EMAIL_EXISTS",
                    ) from exc
            else:
                # Linking to a password account that never proved its mailbox:
                # whoever set that password may not own the address, so it is
                # discarded (the real owner just authenticated via Google).
                cred = await self.get_credential(db, profile.id, for_update=True)
                if cred is not None and cred.email_verified_at is None:
                    cred.password_hash = None
                    await self.revoke_user_sessions(db, profile.id)
            db.add(
                OAuthIdentity(
                    user_id=profile.id,
                    provider="google",
                    provider_subject=subject,
                    email=email,
                    last_login_at=now,
                )
            )
            await db.flush()

        if not profile.is_active:
            raise AuthorizationError("Account is inactive", code="ACCOUNT_INACTIVE")
        await self._mark_verified(db, profile)
        return profile
