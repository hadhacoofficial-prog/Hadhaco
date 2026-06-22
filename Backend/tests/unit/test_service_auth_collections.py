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
        with (
            patch(
                "app.modules.collections.service._repo.get_by_slug",
                AsyncMock(return_value=mock_col),
            ),
            patch(
                "app.modules.collections.service.CollectionResponse.model_validate",
                return_value=MagicMock(),
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
                return_value=MagicMock(),
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
        with (
            patch(
                "app.modules.collections.service._repo.list_active",
                AsyncMock(return_value=[mock_col]),
            ),
            patch(
                "app.modules.collections.service.CollectionResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.list_active(db)
        assert len(result) == 1


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
        mock_record.backup_codes = "[]"
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

    async def test_record_admin_session_adds_to_db(self):
        db = AsyncMock()
        db.add = MagicMock()
        await self.svc.record_admin_session(
            db, str(uuid.uuid4()), "1.2.3.4", "Mozilla/5.0"
        )
        db.add.assert_called_once()

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

    async def test_force_logout_delegates_to_logout(self):
        db = AsyncMock()
        target_user_id = str(uuid.uuid4())
        with patch.object(self.svc, "logout", AsyncMock()) as mock_logout:
            await self.svc.force_logout(db, target_user_id)
        mock_logout.assert_awaited_once_with(db, target_user_id)
