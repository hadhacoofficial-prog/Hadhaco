"""CompanyConfigRepository unit tests — mocked AsyncSession, no real DB required."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.modules.company.models  # noqa: F401  — ensure mapper is configured


# ─── Mock helpers ─────────────────────────────────────────────────────────────


def _scalar_one_or_none(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _db(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = MagicMock()
    return db


# ─── CompanyConfigRepository ──────────────────────────────────────────────────


class TestCompanyConfigRepositoryGet:
    def setup_method(self):
        from app.modules.company.repository import CompanyConfigRepository

        self.repo = CompanyConfigRepository()

    async def test_get_returns_existing_company(self):
        from app.modules.company.models import CompanyConfig

        mock_company = MagicMock(spec=CompanyConfig)
        mock_company.id = 1
        mock_company.name = "Hadha"
        mock_company.country = "India"

        db = _db(_scalar_one_or_none(mock_company))
        result = await self.repo.get(db)

        assert result is mock_company

    async def test_get_returns_none_when_not_found(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.get(db)

        assert result is None

    async def test_get_calls_db_execute_once(self):
        db = _db(_scalar_one_or_none(None))
        await self.repo.get(db)

        assert db.execute.call_count == 1


class TestCompanyConfigRepositoryUpdate:
    def setup_method(self):
        from app.modules.company.repository import CompanyConfigRepository

        self.repo = CompanyConfigRepository()

    async def test_update_modifies_existing_row_attributes(self):
        from app.modules.company.models import CompanyConfig

        existing = MagicMock(spec=CompanyConfig)
        existing.name = "OldName"

        db = _db(_scalar_one_or_none(existing))
        result = await self.repo.update(db, {"name": "NewName"})

        assert result.name == "NewName"

    async def test_update_creates_new_company_config_when_none_exists(self):
        db = _db(_scalar_one_or_none(None))
        result = await self.repo.update(db, {"name": "Hadha"})

        # db.add must have been called with a CompanyConfig(id=1)
        assert db.add.called
        added = db.add.call_args[0][0]
        assert added.id == 1

    async def test_update_calls_db_add_when_creating_new(self):
        db = _db(_scalar_one_or_none(None))
        await self.repo.update(db, {})

        assert db.add.call_count == 1

    async def test_update_does_not_call_db_add_when_row_exists(self):
        from app.modules.company.models import CompanyConfig

        existing = MagicMock(spec=CompanyConfig)
        db = _db(_scalar_one_or_none(existing))
        await self.repo.update(db, {"name": "X"})

        db.add.assert_not_called()

    async def test_update_calls_db_flush(self):
        from app.modules.company.models import CompanyConfig

        existing = MagicMock(spec=CompanyConfig)
        db = _db(_scalar_one_or_none(existing))
        await self.repo.update(db, {"name": "Hadha"})

        db.flush.assert_awaited_once()

    async def test_update_ignores_keys_not_present_as_model_attributes(self):
        """hasattr guard: unknown keys must be silently skipped."""
        from app.modules.company.models import CompanyConfig

        existing = MagicMock(spec=CompanyConfig)
        # MagicMock(spec=...) raises AttributeError for unknown attrs,
        # which means hasattr returns False → the guard works.
        db = _db(_scalar_one_or_none(existing))

        # Should not raise even though "nonexistent_field" is not on the model.
        await self.repo.update(db, {"nonexistent_field": "value"})

    async def test_update_with_empty_dict_returns_row_unchanged(self):
        from app.modules.company.models import CompanyConfig

        existing = MagicMock(spec=CompanyConfig)
        existing.name = "Unchanged"

        db = _db(_scalar_one_or_none(existing))
        result = await self.repo.update(db, {})

        assert result is existing

    @pytest.mark.parametrize(
        "field",
        ["name", "tagline", "city", "phone", "support_email", "website", "country"],
    )
    async def test_update_sets_individual_field(self, field):
        from app.modules.company.models import CompanyConfig

        existing = MagicMock(spec=CompanyConfig)

        db = _db(_scalar_one_or_none(existing))
        await self.repo.update(db, {field: "test_value"})

        assert getattr(existing, field) == "test_value"
