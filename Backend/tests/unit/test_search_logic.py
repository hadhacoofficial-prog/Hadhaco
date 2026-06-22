"""Unit tests for SearchService pure logic (no DB calls)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.search.service import SearchService


class TestSearchServicePureLogic:
    """Tests for logic that doesn't reach the DB."""

    def setup_method(self):
        self.svc = SearchService()

    async def test_empty_query_returns_empty_result(self):
        db = AsyncMock()
        result = await self.svc.full_text_search(db, "")
        assert result["items"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 0

    async def test_whitespace_query_returns_empty(self):
        db = AsyncMock()
        result = await self.svc.full_text_search(db, "   ")
        assert result["items"] == []
        assert result["total"] == 0

    async def test_record_search_skips_empty_query(self):
        db = AsyncMock()
        # No DB calls should be made
        await self.svc.record_search(db, "", user_id=None, result_count=0)
        db.execute.assert_not_called()

    async def test_record_search_skips_whitespace_query(self):
        db = AsyncMock()
        await self.svc.record_search(db, "  ", user_id=None, result_count=0)
        db.execute.assert_not_called()

    async def test_autocomplete_skips_short_query(self):
        db = AsyncMock()
        result = await self.svc.autocomplete(db, "r")
        assert result == []
        db.execute.assert_not_called()

    async def test_autocomplete_skips_empty(self):
        db = AsyncMock()
        result = await self.svc.autocomplete(db, "")
        assert result == []

    async def test_full_text_search_pagination_params_in_result(self):
        """Result structure includes pagination even when no DB results."""
        db = AsyncMock()
        result = await self.svc.full_text_search(db, "")
        assert "page" in result
        assert "page_size" in result
        assert "total_pages" in result

    async def test_pagination_page_size_respected(self):
        db = AsyncMock()
        result = await self.svc.full_text_search(db, "", page=2, page_size=10)
        assert result["page"] == 2
        assert result["page_size"] == 10
