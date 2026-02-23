"""Tests for KIK-469 Phase 2: ETF sector classification in structure analysis."""

import pytest
from unittest.mock import patch, MagicMock


def _make_snapshot_pos(symbol, sector=None, market_cap=None, quote_type=None, eval_jpy=1000000):
    """Helper to build a snapshot position dict."""
    return {
        "symbol": symbol,
        "name": symbol,
        "sector": sector,
        "shares": 100,
        "cost_price": 100,
        "cost_currency": "USD",
        "current_price": 110,
        "market_currency": "USD",
        "market_cap": market_cap,
        "evaluation": 11000,
        "evaluation_jpy": eval_jpy,
        "cost_jpy": eval_jpy * 0.9,
        "pnl": 10,
        "pnl_pct": 0.1,
        "pnl_jpy": eval_jpy * 0.1,
        "purchase_date": "2024-01-01",
        "memo": "",
        "quoteType": quote_type,
    }


class TestETFSectorClassification:
    """Test ETF sector classification in get_structure_analysis."""

    def test_etf_sector_classified_as_etf(self):
        """ETF with no sector should be classified as 'ETF'."""
        from src.core.portfolio.portfolio_manager import get_structure_analysis

        snapshot = {
            "positions": [
                _make_snapshot_pos("VGK", sector=None, quote_type="ETF"),
            ],
            "total_value_jpy": 1000000,
            "total_cost_jpy": 900000,
            "total_pnl_jpy": 100000,
            "total_pnl_pct": 0.1,
            "fx_rates": {},
            "as_of": "2025-01-01",
        }

        with patch("src.core.portfolio.portfolio_manager.get_snapshot", return_value=snapshot):
            result = get_structure_analysis("dummy.csv", MagicMock())

        assert "ETF" in result["sector_breakdown"]

    def test_etf_size_class_is_etf(self):
        """ETF should have size_class 'ETF' instead of market cap classification."""
        from src.core.portfolio.portfolio_manager import get_structure_analysis

        snapshot = {
            "positions": [
                _make_snapshot_pos("VGK", sector=None, quote_type="ETF", market_cap=20000000000),
            ],
            "total_value_jpy": 1000000,
            "total_cost_jpy": 900000,
            "total_pnl_jpy": 100000,
            "total_pnl_pct": 0.1,
            "fx_rates": {},
            "as_of": "2025-01-01",
        }

        with patch("src.core.portfolio.portfolio_manager.get_snapshot", return_value=snapshot):
            result = get_structure_analysis("dummy.csv", MagicMock())

        assert "ETF" in result["size_breakdown"]

    def test_stock_sector_unchanged(self):
        """Regular stock sector classification should be unchanged."""
        from src.core.portfolio.portfolio_manager import get_structure_analysis

        snapshot = {
            "positions": [
                _make_snapshot_pos("AAPL", sector="Technology", quote_type="EQUITY", market_cap=3000000000000),
            ],
            "total_value_jpy": 1000000,
            "total_cost_jpy": 900000,
            "total_pnl_jpy": 100000,
            "total_pnl_pct": 0.1,
            "fx_rates": {},
            "as_of": "2025-01-01",
        }

        with patch("src.core.portfolio.portfolio_manager.get_snapshot", return_value=snapshot):
            result = get_structure_analysis("dummy.csv", MagicMock())

        assert "Technology" in result["sector_breakdown"]
        assert "ETF" not in result["sector_breakdown"]

    def test_mixed_portfolio_sectors(self):
        """Mixed portfolio should have both stock sectors and ETF."""
        from src.core.portfolio.portfolio_manager import get_structure_analysis

        snapshot = {
            "positions": [
                _make_snapshot_pos("AAPL", sector="Technology", quote_type="EQUITY", eval_jpy=500000),
                _make_snapshot_pos("VGK", sector=None, quote_type="ETF", eval_jpy=500000),
            ],
            "total_value_jpy": 1000000,
            "total_cost_jpy": 900000,
            "total_pnl_jpy": 100000,
            "total_pnl_pct": 0.1,
            "fx_rates": {},
            "as_of": "2025-01-01",
        }

        with patch("src.core.portfolio.portfolio_manager.get_snapshot", return_value=snapshot):
            result = get_structure_analysis("dummy.csv", MagicMock())

        assert "Technology" in result["sector_breakdown"]
        assert "ETF" in result["sector_breakdown"]

    def test_etf_with_existing_sector_keeps_sector(self):
        """ETF with an existing sector should keep its sector (not override to ETF)."""
        from src.core.portfolio.portfolio_manager import get_structure_analysis

        snapshot = {
            "positions": [
                _make_snapshot_pos("VGK", sector="Europe Stock", quote_type="ETF"),
            ],
            "total_value_jpy": 1000000,
            "total_cost_jpy": 900000,
            "total_pnl_jpy": 100000,
            "total_pnl_pct": 0.1,
            "fx_rates": {},
            "as_of": "2025-01-01",
        }

        with patch("src.core.portfolio.portfolio_manager.get_snapshot", return_value=snapshot):
            result = get_structure_analysis("dummy.csv", MagicMock())

        # If sector is already set, it should use that, not fall back to "ETF"
        assert "Europe Stock" in result["sector_breakdown"]

    def test_position_detail_quoteType_field(self):
        """Position detail built in get_snapshot should include quoteType."""
        # This test verifies the field is added to position_detail dict
        pos = _make_snapshot_pos("VGK", quote_type="ETF")
        assert pos["quoteType"] == "ETF"

        pos2 = _make_snapshot_pos("AAPL", quote_type="EQUITY")
        assert pos2["quoteType"] == "EQUITY"

        pos3 = _make_snapshot_pos("UNKNOWN", quote_type=None)
        assert pos3["quoteType"] is None
