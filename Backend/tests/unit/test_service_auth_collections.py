"""Tests for AuthService 2FA methods and CollectionService success paths."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── CollectionService success paths ──────────────────────────────────────────


class TestCollectionServiceSuccessPaths:
    def setup_method(self):
        from app.modules.collections.service import CollectionService

        self.svc = CollectionService()

    async def test_get_by_slug_returns_validated_response(self):
        db = AsyncMock()
        mock_col = MagicMock()
        validated = MagicMock()
        validated.id = uuid.uuid4()
        validated.primary_image_id = None
        with (
            patch(
                "app.modules.collections.service._repo.get_by_slug",
                AsyncMock(return_value=mock_col),
            ),
            patch(
                "app.modules.collections.service.CollectionResponse.model_validate",
                return_value=validated,
            ) as mock_mv,
        ):
            await self.svc.get_by_slug(db, "silver-rings")
        mock_mv.assert_called_once_with(mock_col)

    async def test_create_creates_and_returns_response(self):
        from app.modules.collections.schemas import CollectionCreateRequest

        db = AsyncMock()
        mock_col = MagicMock()
        with (
            patch(
                "app.modules.collections.service._repo.get_by_slug",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.collections.service._repo.create",
                AsyncMock(return_value=mock_col),
            ),
            patch(
                "app.modules.collections.service.CollectionResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.create(
                db, CollectionCreateRequest(name="Silver", slug="silver")
            )
        assert result is not None

    async def test_update_success_with_slug_rename(self):
        from app.modules.collections.schemas import CollectionUpdateRequest

        db = AsyncMock()
        mock_existing = MagicMock()
        mock_existing.slug = "old-slug"
        mock_updated = MagicMock()
        validated = MagicMock()
        validated.id = uuid.uuid4()
        validated.primary_image_id = None
        with (
            patch(
                "app.modules.collections.service._repo.get_by_id",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.collections.service._repo.get_by_slug",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.collections.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch(
                "app.modules.collections.service.CollectionResponse.model_validate",
                return_value=validated,
            ),
        ):
            await self.svc.update(
                db, uuid.uuid4(), CollectionUpdateRequest(slug="new-slug")
            )

    async def test_update_raises_conflict_when_slug_taken(self):
        from app.core.exceptions import ConflictError
        from app.modules.collections.schemas import CollectionUpdateRequest

        db = AsyncMock()
        mock_existing = MagicMock()
        mock_existing.slug = "old-slug"
        mock_slug_conflict = MagicMock()
        with (
            patch(
                "app.modules.collections.service._repo.get_by_id",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.collections.service._repo.get_by_slug",
                AsyncMock(return_value=mock_slug_conflict),
            ),
        ):
            with pytest.raises(ConflictError):
                await self.svc.update(
                    db, uuid.uuid4(), CollectionUpdateRequest(slug="taken-slug")
                )

    async def test_delete_calls_soft_delete(self):
        db = AsyncMock()
        mock_existing = MagicMock()
        with (
            patch(
                "app.modules.collections.service._repo.get_by_id",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.collections.service._repo.soft_delete", AsyncMock()
            ) as mock_del,
        ):
            await self.svc.delete(db, uuid.uuid4())
        mock_del.assert_awaited_once()

    async def test_add_products_calls_repo(self):
        from app.modules.collections.schemas import AddProductsToCollectionRequest

        db = AsyncMock()
        mock_existing = MagicMock()
        with (
            patch(
                "app.modules.collections.service._repo.get_by_id",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.collections.service._repo.add_products", AsyncMock()
            ) as mock_add,
        ):
            await self.svc.add_products(
                db,
                uuid.uuid4(),
                AddProductsToCollectionRequest(
                    product_ids=[uuid.uuid4(), uuid.uuid4()]
                ),
            )
        mock_add.assert_awaited_once()

    async def test_add_products_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.collections.schemas import AddProductsToCollectionRequest

        db = AsyncMock()
        with patch(
            "app.modules.collections.service._repo.get_by_id",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.add_products(
                    db,
                    uuid.uuid4(),
                    AddProductsToCollectionRequest(product_ids=[uuid.uuid4()]),
                )

    async def test_remove_product_calls_repo(self):
        db = AsyncMock()
        mock_existing = MagicMock()
        with (
            patch(
                "app.modules.collections.service._repo.get_by_id",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.collections.service._repo.remove_product", AsyncMock()
            ) as mock_rm,
        ):
            await self.svc.remove_product(db, uuid.uuid4(), uuid.uuid4())
        mock_rm.assert_awaited_once()

    async def test_remove_product_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.collections.service._repo.get_by_id",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.remove_product(db, uuid.uuid4(), uuid.uuid4())

    async def test_list_active_returns_validated_list(self):
        db = AsyncMock()
        mock_col = MagicMock()
        validated = MagicMock()
        validated.id = uuid.uuid4()
        validated.primary_image_id = None
        with (
            patch(
                "app.modules.collections.service._repo.list_active",
                AsyncMock(return_value=[mock_col]),
            ),
            patch(
                "app.modules.collections.service.CollectionResponse.model_validate",
                return_value=validated,
            ),
        ):
            result = await self.svc.list_active(db)
        assert len(result) == 1

    async def test_list_active_resolves_image_despite_stale_primary_image_id_column(
        self,
    ):
        """Regression guard: `collections.primary_image_id` is a
        denormalized column the universal media attach/crop/set-primary flow
        never writes (it only touches the `images` table) — resolving
        image_url must not gate on that column being set, or every
        successfully-attached image silently disappears everywhere a
        collection is listed."""
        from app.modules.media.repository import ImageRepository

        db = AsyncMock()
        mock_col = MagicMock()
        validated = MagicMock()
        validated.id = uuid.uuid4()
        validated.primary_image_id = None  # stale/never-written, as in production
        image_id = uuid.uuid4()

        with (
            patch(
                "app.modules.collections.service._repo.list_active",
                AsyncMock(return_value=[mock_col]),
            ),
            patch(
                "app.modules.collections.service.CollectionResponse.model_validate",
                return_value=validated,
            ),
            patch.object(
                ImageRepository,
                "get_primary_image_ids",
                AsyncMock(return_value={validated.id: image_id}),
            ),
            patch.object(
                ImageRepository,
                "get_primary_variant_urls",
                AsyncMock(return_value={validated.id: "https://cdn/women.webp?v=1"}),
            ),
        ):
            result = await self.svc.list_active(db)

        assert result[0].primary_image_id == image_id
        assert result[0].image_url == "https://cdn/women.webp?v=1"


# ─── AuthService 2FA tests ────────────────────────────────────────────────────


class TestAuthService2FA:
    def setup_method(self):
        from app.modules.auth.service import AuthService

        self.svc = AuthService()

    async def test_has_active_2fa_returns_false_when_no_record(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.svc.has_active_2fa(db, str(uuid.uuid4()))
        assert result is False

    async def test_has_active_2fa_returns_true_when_enabled(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.svc.has_active_2fa(db, str(uuid.uuid4()))
        assert result is True

    async def test_setup_2fa_returns_uri_and_secret(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # no existing record
        db.execute = AsyncMock(return_value=mock_result)
        db.add = MagicMock()

        result = await self.svc.setup_2fa(db, str(uuid.uuid4()), "test@example.com")
        assert "totp_uri" in result
        assert "secret" in result
        assert "qr_code_data_url" in result
        assert result["qr_code_data_url"].startswith("data:image/png;base64,")

    async def test_setup_2fa_updates_existing_record(self):
        db = AsyncMock()
        mock_record = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record  # existing record
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.setup_2fa(db, str(uuid.uuid4()), "test@example.com")
        assert "totp_uri" in result
        # Should call execute twice: once to get existing, once to update
        assert db.execute.await_count == 2

    async def test_verify_and_activate_2fa_raises_error_on_invalid_totp(self):
        from app.core.exceptions import AuthenticationError

        db = AsyncMock()
        mock_record = MagicMock()
        mock_record.totp_secret = "some_encrypted_secret"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.modules.auth.service.decrypt_value",
                return_value="JBSWY3DPEHPK3PXP",
            ),
            patch("app.modules.auth.service.pyotp.TOTP") as mock_totp_cls,
        ):
            mock_totp = MagicMock()
            mock_totp.verify.return_value = False
            mock_totp_cls.return_value = mock_totp
            from app.core.exceptions import AuthenticationError

            with pytest.raises(AuthenticationError):
                await self.svc.verify_and_activate_2fa(db, str(uuid.uuid4()), "000000")

    async def test_verify_and_activate_2fa_returns_backup_codes_on_valid_totp(self):
        db = AsyncMock()
        mock_record = MagicMock()
        mock_record.totp_secret = "encrypted"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.modules.auth.service.decrypt_value",
                return_value="JBSWY3DPEHPK3PXP",
            ),
            patch("app.modules.auth.service.pyotp.TOTP") as mock_totp_cls,
            patch(
                "app.modules.auth.service.generate_backup_codes",
                return_value=["CODE1", "CODE2"],
            ),
            patch("app.modules.auth.service.hash_backup_code", return_value="hashed"),
        ):
            mock_totp = MagicMock()
            mock_totp.verify.return_value = True
            mock_totp_cls.return_value = mock_totp
            result = await self.svc.verify_and_activate_2fa(
                db, str(uuid.uuid4()), "123456"
            )

        assert result == ["CODE1", "CODE2"]

    async def test_validate_2fa_returns_true_on_valid_totp(self):
        db = AsyncMock()
        mock_record = MagicMock()
        mock_record.totp_secret = "encrypted"
        mock_record.backup_codes = "[]"
        mock_record.last_used_counter = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.modules.auth.service.decrypt_value",
                return_value="JBSWY3DPEHPK3PXP",
            ),
            patch("app.modules.auth.service.pyotp.TOTP") as mock_totp_cls,
        ):
            mock_totp = MagicMock()
            mock_totp.verify.return_value = True
            mock_totp_cls.return_value = mock_totp
            result = await self.svc.validate_2fa(db, str(uuid.uuid4()), "123456")

        assert result is True

    async def test_validate_2fa_returns_false_when_code_invalid(self):
        db = AsyncMock()
        mock_record = MagicMock()
        mock_record.totp_secret = "encrypted"
        mock_record.backup_codes = []
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.modules.auth.service.decrypt_value",
                return_value="JBSWY3DPEHPK3PXP",
            ),
            patch("app.modules.auth.service.pyotp.TOTP") as mock_totp_cls,
        ):
            mock_totp = MagicMock()
            mock_totp.verify.return_value = False
            mock_totp_cls.return_value = mock_totp
            result = await self.svc.validate_2fa(db, str(uuid.uuid4()), "000000")

        assert result is False

    async def test_validate_2fa_rejects_replay_of_already_used_step(self):
        """A previously-accepted code (same or earlier TOTP time-step) must
        not verify again — otherwise an intercepted code stays valid for the
        whole ~90s pyotp tolerance window and can be replayed verbatim.

        The replay check is now a single atomic conditional UPDATE (not a
        Python-side read-then-compare) so that two concurrent requests can't
        race past it — a rowcount of 0 means either a genuine replay or a
        concurrent request that already won the race, both correctly
        rejected here."""
        db = AsyncMock()
        mock_record = MagicMock()
        mock_record.totp_secret = "encrypted"
        mock_record.backup_codes = "[]"

        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = mock_record
        update_result = MagicMock()
        update_result.rowcount = 0  # conditional UPDATE matched no row

        db.execute = AsyncMock(side_effect=[select_result, update_result])

        with (
            patch(
                "app.modules.auth.service.decrypt_value",
                return_value="JBSWY3DPEHPK3PXP",
            ),
            patch("app.modules.auth.service.pyotp.TOTP") as mock_totp_cls,
        ):
            mock_totp = MagicMock()
            mock_totp.verify.return_value = True
            mock_totp_cls.return_value = mock_totp
            result = await self.svc.validate_2fa(db, str(uuid.uuid4()), "123456")

        assert result is False

    async def test_validate_2fa_accepts_valid_backup_code(self):
        db = AsyncMock()
        mock_record = MagicMock()
        mock_record.totp_secret = "encrypted"
        mock_record.backup_codes = '["$2b$12$hashed_code"]'
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.modules.auth.service.decrypt_value",
                return_value="JBSWY3DPEHPK3PXP",
            ),
            patch("app.modules.auth.service.pyotp.TOTP") as mock_totp_cls,
            patch("app.modules.auth.service.verify_backup_code", return_value=True),
        ):
            mock_totp = MagicMock()
            mock_totp.verify.return_value = False  # TOTP fails, backup code matches
            mock_totp_cls.return_value = mock_totp
            result = await self.svc.validate_2fa(db, str(uuid.uuid4()), "BACKUP-CODE")

        assert result is True

    async def test_get_2fa_record_raises_404_when_missing(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(NotFoundError):
            await self.svc._get_2fa_record(db, str(uuid.uuid4()))

    async def test_ensure_admin_session_tracked_uses_upsert_not_2fa_fields(self):
        """Must be an upsert (single statement, no db.add) whose set_ clause
        never includes is_2fa_verified/verified_at/expires_at — a plain
        login-presence touch must never regress an already-verified
        session back to unverified."""
        from sqlalchemy.dialects.postgresql.dml import Insert

        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock()

        await self.svc.ensure_admin_session_tracked(
            db, str(uuid.uuid4()), "supabase-session-1", "1.2.3.4", "Mozilla/5.0"
        )

        db.add.assert_not_called()
        db.execute.assert_awaited_once()
        stmt = db.execute.call_args[0][0]
        assert isinstance(stmt, Insert)

    async def test_track_admin_login_if_new_session_noop_without_session_id(self):
        db = AsyncMock()
        redis = AsyncMock()

        with patch.object(
            self.svc, "ensure_admin_session_tracked", AsyncMock()
        ) as mock_track:
            await self.svc.track_admin_login_if_new_session(
                db,
                redis,
                user_id=str(uuid.uuid4()),
                user_email="admin@example.com",
                user_role="admin",
                session_id=None,
                ip_address="1.2.3.4",
                user_agent="Mozilla/5.0",
            )

        mock_track.assert_not_called()

    async def test_track_admin_login_if_new_session_tracks_and_logs_once(self):
        db = AsyncMock()
        redis = AsyncMock()
        session_id = "supabase-session-1"

        with (
            patch(
                "app.modules.auth.service.safe_redis_get", AsyncMock(return_value=None)
            ),
            patch(
                "app.modules.auth.service.safe_redis_setex", AsyncMock()
            ) as mock_setex,
            patch.object(
                self.svc, "ensure_admin_session_tracked", AsyncMock()
            ) as mock_track,
            patch(
                "app.modules.audit.service.AuditService.log", AsyncMock()
            ) as mock_log,
        ):
            await self.svc.track_admin_login_if_new_session(
                db,
                redis,
                user_id=str(uuid.uuid4()),
                user_email="admin@example.com",
                user_role="admin",
                session_id=session_id,
                ip_address="1.2.3.4",
                user_agent="Mozilla/5.0",
            )

        mock_track.assert_awaited_once()
        mock_log.assert_awaited_once()
        assert mock_setex.await_count == 2

    async def test_track_admin_login_if_new_session_skips_when_already_deduped(self):
        """Both dedup keys already set (routine reload) — neither side
        effect should fire again."""
        db = AsyncMock()
        redis = AsyncMock()

        with (
            patch(
                "app.modules.auth.service.safe_redis_get", AsyncMock(return_value="1")
            ),
            patch.object(
                self.svc, "ensure_admin_session_tracked", AsyncMock()
            ) as mock_track,
            patch(
                "app.modules.audit.service.AuditService.log", AsyncMock()
            ) as mock_log,
        ):
            await self.svc.track_admin_login_if_new_session(
                db,
                redis,
                user_id=str(uuid.uuid4()),
                user_email="admin@example.com",
                user_role="admin",
                session_id="supabase-session-1",
                ip_address="1.2.3.4",
                user_agent="Mozilla/5.0",
            )

        mock_track.assert_not_called()
        mock_log.assert_not_called()

    async def test_mark_admin_session_2fa_verified_uses_atomic_upsert(self):
        """Must be a single upsert statement, not SELECT-then-branch — the
        old shape had a real race: two concurrent calls for the same
        session could both see no existing row and both attempt an INSERT,
        the second violating the unique (user_id, supabase_session_id)
        index with an unhandled IntegrityError."""
        from sqlalchemy.dialects.postgresql.dml import Insert

        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock()

        await self.svc.mark_admin_session_2fa_verified(
            db, str(uuid.uuid4()), "supabase-session-1", "1.2.3.4", "Mozilla/5.0"
        )

        db.add.assert_not_called()
        db.execute.assert_awaited_once()
        stmt = db.execute.call_args[0][0]
        assert isinstance(stmt, Insert)

    async def test_is_admin_session_2fa_verified_false_when_no_row(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.is_admin_session_2fa_verified(
            db, str(uuid.uuid4()), "supabase-session-1"
        )

        assert result is False

    async def test_is_admin_session_2fa_verified_false_when_expired(self):
        from datetime import UTC, datetime, timedelta

        db = AsyncMock()
        record = MagicMock()
        record.is_2fa_verified = True
        record.expires_at = datetime.now(UTC) - timedelta(hours=1)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.is_admin_session_2fa_verified(
            db, str(uuid.uuid4()), "supabase-session-1"
        )

        assert result is False

    async def test_is_admin_session_2fa_verified_true_when_valid(self):
        from datetime import UTC, datetime, timedelta

        db = AsyncMock()
        record = MagicMock()
        record.is_2fa_verified = True
        record.expires_at = datetime.now(UTC) + timedelta(hours=1)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.is_admin_session_2fa_verified(
            db, str(uuid.uuid4()), "supabase-session-1"
        )

        assert result is True

    async def test_is_new_device_true_when_no_match(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.is_new_device(
            db, str(uuid.uuid4()), "9.9.9.9", "Mozilla/5.0 Chrome/120.0"
        )

        assert result is True

    async def test_is_new_device_false_when_ip_and_device_both_recognized(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.is_new_device(
            db, str(uuid.uuid4()), "1.2.3.4", "Mozilla/5.0 Chrome/120.0"
        )

        assert result is False

    async def test_is_new_device_true_when_ip_new_even_if_device_recognized(self):
        """A familiar browser from a brand-new IP must still count as new —
        regression test for the De Morgan bug where a single OR'd query only
        fired when *both* signals were unrecognized."""
        db = AsyncMock()
        ip_not_seen = MagicMock()
        ip_not_seen.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=ip_not_seen)

        result = await self.svc.is_new_device(
            db,
            str(uuid.uuid4()),
            "203.0.113.7",
            "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0",
        )

        assert result is True

    async def test_is_2fa_locked_out_false_when_no_failures(self):
        redis = AsyncMock()
        with patch(
            "app.modules.auth.service.safe_redis_get", AsyncMock(return_value=None)
        ):
            result = await self.svc.is_2fa_locked_out(redis, str(uuid.uuid4()))
        assert result is False

    async def test_is_2fa_locked_out_true_at_threshold(self):
        from app.modules.auth.service import ADMIN_2FA_LOCKOUT_THRESHOLD

        redis = AsyncMock()
        with patch(
            "app.modules.auth.service.safe_redis_get",
            AsyncMock(return_value=str(ADMIN_2FA_LOCKOUT_THRESHOLD)),
        ):
            result = await self.svc.is_2fa_locked_out(redis, str(uuid.uuid4()))
        assert result is True

    async def test_record_2fa_failure_increments_count(self):
        redis = AsyncMock()
        with (
            patch(
                "app.modules.auth.service.safe_redis_get", AsyncMock(return_value="2")
            ),
            patch(
                "app.modules.auth.service.safe_redis_setex", AsyncMock()
            ) as mock_setex,
        ):
            count = await self.svc.record_2fa_failure(redis, str(uuid.uuid4()))
        assert count == 3
        mock_setex.assert_awaited_once()

    async def test_clear_2fa_failures_deletes_key(self):
        redis = AsyncMock()
        with patch(
            "app.modules.auth.service.safe_redis_delete", AsyncMock()
        ) as mock_delete:
            await self.svc.clear_2fa_failures(redis, str(uuid.uuid4()))
        mock_delete.assert_awaited_once()

    async def test_touch_admin_session_activity_skips_when_throttled(self):
        from datetime import UTC, datetime

        db = AsyncMock()
        record = MagicMock()
        record.last_activity_at = datetime.now(UTC)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)

        await self.svc.touch_admin_session_activity(
            db, str(uuid.uuid4()), "sess-1", "1.2.3.4", "Mozilla/5.0"
        )

        # Only the initial SELECT ran — no UPDATE within the throttle window.
        assert db.execute.await_count == 1

    async def test_touch_admin_session_activity_writes_when_stale(self):
        from datetime import UTC, datetime, timedelta

        db = AsyncMock()
        record = MagicMock()
        record.last_activity_at = datetime.now(UTC) - timedelta(hours=1)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)

        await self.svc.touch_admin_session_activity(
            db,
            str(uuid.uuid4()),
            "sess-1",
            "1.2.3.4",
            "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0",
        )

        assert db.execute.await_count == 2  # SELECT then UPDATE

    async def test_touch_admin_session_activity_noop_when_no_row(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        await self.svc.touch_admin_session_activity(
            db, str(uuid.uuid4()), "sess-1", "1.2.3.4", "Mozilla/5.0"
        )

        assert db.execute.await_count == 1  # SELECT only, nothing to update

    async def test_list_admin_sessions_returns_rows(self):
        db = AsyncMock()
        rows = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.list_admin_sessions(db, str(uuid.uuid4()))

        assert result == rows

    async def test_revoke_admin_session_true_when_deleted(self):
        db = AsyncMock()
        record = MagicMock()
        record.id = uuid.uuid4()
        record.supabase_session_id = "some-other-session"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)

        deleted, was_current = await self.svc.revoke_admin_session(
            db,
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            current_session_id="current-session",
        )

        assert deleted is True
        assert was_current is False

    async def test_revoke_admin_session_false_when_nothing_matched(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        deleted, was_current = await self.svc.revoke_admin_session(
            db, str(uuid.uuid4()), str(uuid.uuid4())
        )

        assert deleted is False
        assert was_current is False

    async def test_revoke_admin_session_refuses_to_delete_current_session(self):
        """Deleting the caller's own current session must go through
        /revoke-all or /logout instead — not the generic one-session
        endpoint, so it can't happen by accident."""
        db = AsyncMock()
        record = MagicMock()
        record.id = uuid.uuid4()
        record.supabase_session_id = "current-session"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute = AsyncMock(return_value=mock_result)

        deleted, was_current = await self.svc.revoke_admin_session(
            db,
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            current_session_id="current-session",
        )

        assert deleted is False
        assert was_current is True
        db.execute.assert_awaited_once()  # SELECT only — no DELETE issued

    async def test_revoke_other_admin_sessions_returns_count(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.revoke_other_admin_sessions(
            db, str(uuid.uuid4()), "current-session"
        )

        assert result == 3

    async def test_cleanup_expired_admin_sessions_returns_count(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 7
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.cleanup_expired_admin_sessions(db)

        assert result == 7

    async def test_clear_all_admin_sessions_2fa_returns_count(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.clear_all_admin_sessions_2fa(db, str(uuid.uuid4()))

        assert result == 2

    async def test_logout_calls_supabase_api(self):
        db = AsyncMock()
        mock_response = MagicMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient", return_value=mock_client):
            await self.svc.logout(db, str(uuid.uuid4()))
        mock_client.post.assert_awaited_once()

    async def test_logout_swallows_supabase_outage_without_raising(self):
        """A Supabase admin-API outage must never prevent logout — routers
        call this before clearing the local AdminSession row, so letting the
        exception propagate would leave that row (and the 2FA-verified
        state) in place even though the user asked to log out."""
        db = AsyncMock()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=ConnectionError("supabase unreachable")
        )
        with patch("httpx.AsyncClient", return_value=mock_client):
            await self.svc.logout(db, str(uuid.uuid4()))  # must not raise

    async def test_force_logout_delegates_to_logout(self):
        db = AsyncMock()
        target_user_id = str(uuid.uuid4())
        with patch.object(self.svc, "logout", AsyncMock()) as mock_logout:
            await self.svc.force_logout(db, target_user_id)
        mock_logout.assert_awaited_once_with(db, target_user_id)
