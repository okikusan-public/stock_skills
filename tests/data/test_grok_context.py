"""Tests for grok_context.py — compact knowledge context extraction (KIK-488).

Tests cover:
- get_stock_context: held/non-held, full history, empty history, graceful degradation
- get_industry_context: held stocks in sector, prior research
- get_market_context: held sectors, recent market context
- get_business_context: held status, prior research, thesis
- _truncate_context: truncation at line boundaries
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.grok_context import (
    _truncate_context,
    get_stock_context,
    get_industry_context,
    get_market_context,
    get_business_context,
)


# ---------------------------------------------------------------------------
# _truncate_context
# ---------------------------------------------------------------------------


class TestTruncateContext:

    def test_empty_string(self):
        assert _truncate_context("") == ""

    def test_short_text_unchanged(self):
        text = "Short text"
        assert _truncate_context(text) == text

    def test_truncates_long_text(self):
        # max_tokens=10 → max_chars=30
        lines = ["Line 1 - 15 chars", "Line 2 - 15 chars", "Line 3 - 15 chars"]
        text = "\n".join(lines)
        result = _truncate_context(text, max_tokens=10)
        # Only first line should fit within 30 chars
        assert "Line 1" in result
        assert "Line 3" not in result

    def test_truncates_at_line_boundary(self):
        # max_tokens=20 → max_chars=60
        lines = ["AAAA " * 10, "BBBB " * 10]  # Each ~50 chars
        text = "\n".join(lines)
        result = _truncate_context(text, max_tokens=20)
        # First line is 50 chars, fits in 60
        assert "AAAA" in result
        # Second line would push over, should be excluded
        assert "BBBB" not in result


# ---------------------------------------------------------------------------
# get_stock_context
# ---------------------------------------------------------------------------

def _make_stock_history(
    trades=None, reports=None, notes=None,
    screens=None, researches=None, health_checks=None, themes=None,
):
    """Build a history dict for testing."""
    return {
        "trades": trades or [],
        "reports": reports or [],
        "notes": notes or [],
        "screens": screens or [],
        "researches": researches or [],
        "health_checks": health_checks or [],
        "themes": themes or [],
    }


class TestGetStockContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_neo4j_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_no_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = None
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_empty_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history()
        mock_gs.is_held.return_value = False
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_held_stock_with_full_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history(
            trades=[{"type": "buy", "date": "2026-02-14", "shares": 400, "price": 166.31}],
            reports=[{"date": "2026-02-21", "score": 52.65, "verdict": "やや割安"}],
            notes=[
                {"type": "thesis", "content": "ASEAN自動車部品の本命。成長性と割安度を兼備。"},
                {"type": "concern", "content": "チャート上でH&S完成の可能性"},
            ],
            screens=[
                {"preset": "alpha"}, {"preset": "value"}, {"preset": "long-term"},
                {"preset": "alpha"}, {"preset": "value"},
            ],
            researches=[{"date": "2026-02-20", "summary": "ASEAN需要堅調、業績拡大中"}],
            health_checks=[{"date": "2026-02-24"}],
            themes=["Automotive", "ASEAN"],
        )

        result = get_stock_context("AUTO.JK")
        assert "[INVESTOR CONTEXT]" in result
        assert "Currently held" in result
        assert "400 shares" in result
        assert "52.65" in result
        assert "Thesis:" in result
        assert "Concern:" in result
        assert "Appeared 5 times" in result
        assert "ASEAN需要堅調" in result
        assert "Last health check: 2026-02-24" in result
        assert "Themes:" in result
        assert "Focus your research" in result

    @patch("src.data.graph_store", create=True)
    def test_non_held_stock_with_sell(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = False
        mock_gs.get_stock_history.return_value = _make_stock_history(
            trades=[{"type": "sell", "date": "2026-02-25"}],
            reports=[{"date": "2026-02-20", "score": 45.0, "verdict": "割安"}],
        )

        result = get_stock_context("BBL.BK")
        assert "Previously held" in result
        assert "sold 2026-02-25" in result

    @patch("src.data.graph_store", create=True)
    def test_notes_limited_to_two(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history(
            trades=[{"type": "buy", "date": "2026-01-01", "shares": 10, "price": 100}],
            notes=[
                {"type": "thesis", "content": "Thesis 1"},
                {"type": "concern", "content": "Concern 1"},
                {"type": "thesis", "content": "Thesis 2 should be excluded"},
            ],
        )

        result = get_stock_context("TEST")
        assert "Thesis 1" in result
        assert "Concern 1" in result
        assert "Thesis 2" not in result

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation_on_import_error(self, mock_gs):
        """Returns "" when graph_store.is_available raises any exception.

        Verifies the outermost try/except catches all errors (including
        ImportError when graph_store is unavailable).
        """
        mock_gs.is_available.side_effect = ImportError("no graph_store")
        assert get_stock_context("NVDA") == ""

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation_on_exception(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("Connection failed")
        assert get_stock_context("NVDA") == ""


# ---------------------------------------------------------------------------
# get_industry_context
# ---------------------------------------------------------------------------


class TestGetIndustryContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_industry_context("semiconductor") == ""

    @patch("src.data.graph_store", create=True)
    def test_with_held_stocks_in_sector(self, mock_gs):
        mock_gs.is_available.return_value = True

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = [{"symbol": "NVDA"}, {"symbol": "AVGO"}]
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = get_industry_context("semiconductor")
        assert "NVDA" in result
        assert "AVGO" in result
        assert "Focus on developments" in result

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_no_data(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.run.return_value = []
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = get_industry_context("semiconductor")
        assert result == ""

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("fail")
        assert get_industry_context("semiconductor") == ""


# ---------------------------------------------------------------------------
# get_market_context
# ---------------------------------------------------------------------------


class TestGetMarketContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_market_context() == ""

    @patch("src.data.graph_store", create=True)
    def test_with_held_sectors(self, mock_gs):
        mock_gs.is_available.return_value = True

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = [
            {"sector": "Technology", "cnt": 3},
            {"sector": "Financial", "cnt": 2},
        ]
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gs._get_driver.return_value = mock_driver

        result = get_market_context()
        assert "Technology(3)" in result
        assert "Financial(2)" in result
        assert "Focus on how current market" in result

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("fail")
        assert get_market_context() == ""


# ---------------------------------------------------------------------------
# get_business_context
# ---------------------------------------------------------------------------


class TestGetBusinessContext:

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_unavailable(self, mock_gs):
        mock_gs.is_available.return_value = False
        assert get_business_context("AAPL") == ""

    @patch("src.data.graph_store", create=True)
    def test_returns_empty_when_no_history(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.get_stock_history.return_value = None
        assert get_business_context("AAPL") == ""

    @patch("src.data.graph_store", create=True)
    def test_held_stock_with_research_and_thesis(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = True
        mock_gs.get_stock_history.return_value = _make_stock_history(
            researches=[
                {"date": "2026-02-20", "summary": "Strong platform business", "research_type": "business"},
            ],
            themes=["Tech", "Cloud"],
            notes=[{"type": "thesis", "content": "Cloud growth accelerating"}],
        )

        result = get_business_context("AAPL")
        assert "[INVESTOR CONTEXT]" in result
        assert "Currently held" in result
        assert "Strong platform business" in result
        assert "Tech" in result
        assert "Cloud growth accelerating" in result
        assert "Focus on how the business model" in result

    @patch("src.data.graph_store", create=True)
    def test_empty_history_returns_empty(self, mock_gs):
        mock_gs.is_available.return_value = True
        mock_gs.is_held.return_value = False
        mock_gs.get_stock_history.return_value = _make_stock_history()

        assert get_business_context("AAPL") == ""

    @patch("src.data.graph_store", create=True)
    def test_graceful_degradation(self, mock_gs):
        mock_gs.is_available.side_effect = RuntimeError("fail")
        assert get_business_context("AAPL") == ""
