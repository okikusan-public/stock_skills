"""Tests for TrendingScreener (KIK-370)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.screening.screener import TrendingScreener


# ===================================================================
# TrendingScreener.classify
# ===================================================================

class TestTrendingClassify:
    def test_undervalued(self):
        assert TrendingScreener.classify(65.0) == "話題×割安"

    def test_fair_value(self):
        assert TrendingScreener.classify(45.0) == "話題×適正"

    def test_overvalued(self):
        assert TrendingScreener.classify(20.0) == "話題×割高"

    def test_boundary_60(self):
        assert TrendingScreener.classify(60.0) == "話題×割安"

    def test_boundary_30(self):
        assert TrendingScreener.classify(30.0) == "話題×適正"

    def test_boundary_29_9(self):
        assert TrendingScreener.classify(29.9) == "話題×割高"

    def test_zero(self):
        assert TrendingScreener.classify(0.0) == "話題×割高"

    def test_100(self):
        assert TrendingScreener.classify(100.0) == "話題×割安"


# ===================================================================
# TrendingScreener.screen
# ===================================================================

def _make_grok_result(stocks, context=""):
    return {"stocks": stocks, "market_context": context, "raw_response": "..."}


class TestTrendingScreen:
    def test_basic_pipeline(self, stock_info_data):
        mock_yahoo = MagicMock()
        mock_yahoo.get_stock_info.return_value = stock_info_data

        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result(
            [{"ticker": "7203.T", "name": "Toyota", "reason": "EV push"}],
            context="Bullish mood",
        )

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, context = screener.screen(region="japan", top_n=10)

        assert len(results) == 1
        assert results[0]["symbol"] == stock_info_data["symbol"]
        assert results[0]["trending_reason"] == "EV push"
        assert results[0]["classification"] in ("話題×割安", "話題×適正", "話題×割高", "話題×データ不足")
        assert isinstance(results[0]["value_score"], (int, float))
        assert context == "Bullish mood"

    def test_empty_grok_response(self):
        mock_yahoo = MagicMock()
        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result([])

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, context = screener.screen()

        assert results == []
        assert context == ""

    def test_yahoo_returns_none_classified_as_no_data(self):
        """Yahoo failure -> 話題×データ不足 (not 割高)."""
        mock_yahoo = MagicMock()
        mock_yahoo.get_stock_info.return_value = None

        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result(
            [{"ticker": "UNKNOWN", "name": "Unknown Corp", "reason": "Hyped"}]
        )

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, _ = screener.screen()

        assert len(results) == 1
        assert results[0]["symbol"] == "UNKNOWN"
        assert results[0]["name"] == "Unknown Corp"
        assert results[0]["value_score"] == 0.0
        assert results[0]["classification"] == "話題×データ不足"

    def test_sorting_by_classification_then_score(self):
        mock_yahoo = MagicMock()

        def get_info(symbol):
            if symbol == "A":
                return {"symbol": "A", "name": "A", "per": 50.0, "pbr": 5.0}
            elif symbol == "B":
                return {
                    "symbol": "B", "name": "B", "per": 5.0, "pbr": 0.3,
                    "dividend_yield": 0.05, "roe": 0.2, "revenue_growth": 0.15,
                }
            else:
                return {"symbol": "C", "name": "C", "per": 12.0, "pbr": 1.0}

        mock_yahoo.get_stock_info.side_effect = get_info

        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result([
            {"ticker": "A", "name": "", "reason": ""},
            {"ticker": "B", "name": "", "reason": ""},
            {"ticker": "C", "name": "", "reason": ""},
        ])

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, _ = screener.screen()

        # B (high value score) should be first
        assert results[0]["symbol"] == "B"

    def test_top_n_limit(self):
        mock_yahoo = MagicMock()
        mock_yahoo.get_stock_info.return_value = None

        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result(
            [{"ticker": f"T{i}", "name": "", "reason": ""} for i in range(10)]
        )

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, _ = screener.screen(top_n=3)

        assert len(results) == 3

    def test_empty_ticker_skipped(self):
        mock_yahoo = MagicMock()
        mock_yahoo.get_stock_info.return_value = {"symbol": "7203.T", "name": "Toyota"}

        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result([
            {"ticker": "", "name": "No Ticker", "reason": "test"},
            {"ticker": "7203.T", "name": "Toyota", "reason": "test"},
        ])

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, _ = screener.screen()

        assert len(results) == 1
        assert results[0]["symbol"] == "7203.T"

    def test_theme_passed_to_grok(self):
        mock_yahoo = MagicMock()
        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result([])

        screener = TrendingScreener(mock_yahoo, mock_grok)
        screener.screen(region="us", theme="AI")

        mock_grok.search_trending_stocks.assert_called_once_with(
            region="us", theme="AI",
        )

    def test_no_data_sorted_last(self):
        """Stocks with 話題×データ不足 should sort after 割高."""
        mock_yahoo = MagicMock()

        def get_info(symbol):
            if symbol == "GOOD":
                return {
                    "symbol": "GOOD", "name": "Good", "per": 5.0, "pbr": 0.3,
                    "dividend_yield": 0.05, "roe": 0.2, "revenue_growth": 0.15,
                }
            return None  # NODATA -> データ不足

        mock_yahoo.get_stock_info.side_effect = get_info

        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result([
            {"ticker": "NODATA", "name": "No Data", "reason": "hype"},
            {"ticker": "GOOD", "name": "Good Corp", "reason": "solid"},
        ])

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, _ = screener.screen()

        assert results[0]["symbol"] == "GOOD"
        assert results[1]["symbol"] == "NODATA"
        assert results[1]["classification"] == "話題×データ不足"

    def test_classification_no_data_constant(self):
        """CLASSIFICATION_NO_DATA class attribute should be accessible."""
        assert TrendingScreener.CLASSIFICATION_NO_DATA == "話題×データ不足"

    def test_result_fields(self, stock_info_data):
        mock_yahoo = MagicMock()
        mock_yahoo.get_stock_info.return_value = stock_info_data

        mock_grok = MagicMock()
        mock_grok.search_trending_stocks.return_value = _make_grok_result(
            [{"ticker": "7203.T", "name": "Toyota", "reason": "Hot"}]
        )

        screener = TrendingScreener(mock_yahoo, mock_grok)
        results, _ = screener.screen()

        r = results[0]
        expected_keys = {
            "symbol", "name", "trending_reason", "price", "per", "pbr",
            "dividend_yield", "roe", "value_score", "classification", "sector",
        }
        assert expected_keys.issubset(set(r.keys()))
