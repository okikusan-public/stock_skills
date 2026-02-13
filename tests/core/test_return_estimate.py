"""Tests for src/core/return_estimate.py (KIK-359)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.return_estimate import (
    _is_etf,
    _estimate_from_analyst,
    _estimate_from_history,
    estimate_stock_return,
    estimate_portfolio_return,
)


# ---------------------------------------------------------------------------
# _is_etf
# ---------------------------------------------------------------------------

class TestIsEtf:
    def test_stock_with_analyst_target(self):
        """Stocks with analyst target prices are not ETFs."""
        detail = {"target_mean_price": 250.0, "sector": "Technology"}
        assert _is_etf(detail) is False

    def test_etf_no_target_no_sector(self):
        """ETFs have no target price and no sector."""
        detail = {"target_mean_price": None, "sector": None}
        assert _is_etf(detail) is True

    def test_etf_by_quote_type(self):
        """ETFs identified by quoteType."""
        detail = {"target_mean_price": None, "quoteType": "ETF", "sector": "Financial Services"}
        assert _is_etf(detail) is True

    def test_stock_with_target_but_no_sector(self):
        """Stock with analyst target but no sector is not an ETF."""
        detail = {"target_mean_price": 100.0, "sector": None}
        assert _is_etf(detail) is False


# ---------------------------------------------------------------------------
# _estimate_from_analyst
# ---------------------------------------------------------------------------

class TestEstimateFromAnalyst:
    def test_full_analyst_coverage(self):
        """All 3 target prices available."""
        detail = {
            "price": 100.0,
            "target_high_price": 150.0,
            "target_mean_price": 120.0,
            "target_low_price": 80.0,
            "dividend_yield": 0.02,
            "number_of_analyst_opinions": 25,
            "recommendation_mean": 2.5,
            "forward_per": 18.0,
        }
        result = _estimate_from_analyst(detail)
        assert result["method"] == "analyst"
        assert result["analyst_count"] == 25
        # optimistic: (150-100)/100 + 0.02 = 0.52
        assert abs(result["optimistic"] - 0.52) < 0.001
        # base: (120-100)/100 + 0.02 = 0.22
        assert abs(result["base"] - 0.22) < 0.001
        # pessimistic: (80-100)/100 + 0.02 = -0.18
        assert abs(result["pessimistic"] - (-0.18)) < 0.001

    def test_no_dividend(self):
        """No dividend yield means 0 dividend component."""
        detail = {
            "price": 200.0,
            "target_high_price": 250.0,
            "target_mean_price": 220.0,
            "target_low_price": 180.0,
            "dividend_yield": None,
            "number_of_analyst_opinions": 10,
        }
        result = _estimate_from_analyst(detail)
        # base: (220-200)/200 = 0.10
        assert abs(result["base"] - 0.10) < 0.001

    def test_zero_price(self):
        """Zero price returns empty estimate."""
        detail = {"price": 0, "target_mean_price": 100.0}
        result = _estimate_from_analyst(detail)
        assert result["optimistic"] is None
        assert result["base"] is None
        assert result["pessimistic"] is None

    def test_missing_high_low(self):
        """Only mean target available — fallback calculation."""
        detail = {
            "price": 100.0,
            "target_high_price": None,
            "target_mean_price": 120.0,
            "target_low_price": None,
            "dividend_yield": 0.0,
        }
        result = _estimate_from_analyst(detail)
        assert result["base"] is not None
        # Optimistic/pessimistic should be derived from base
        assert result["optimistic"] is not None
        assert result["pessimistic"] is not None

    def test_few_analysts_count(self):
        """Analyst count is preserved (for confidence display)."""
        detail = {
            "price": 100.0,
            "target_mean_price": 110.0,
            "number_of_analyst_opinions": 3,
        }
        result = _estimate_from_analyst(detail)
        assert result["analyst_count"] == 3


# ---------------------------------------------------------------------------
# _estimate_from_history
# ---------------------------------------------------------------------------

class TestEstimateFromHistory:
    def test_normal_price_history(self):
        """Normal case: ~6 months of daily prices."""
        # 130 days of prices: slight uptrend
        prices = [100.0 + i * 0.1 for i in range(130)]
        detail = {
            "price_history": prices,
            "dividend_yield": 0.03,
        }
        result = _estimate_from_history(detail)
        assert result["method"] == "historical"
        assert result["optimistic"] is not None
        assert result["base"] is not None
        assert result["pessimistic"] is not None
        # Optimistic >= base >= pessimistic
        assert result["optimistic"] >= result["base"]
        assert result["base"] >= result["pessimistic"]

    def test_insufficient_data(self):
        """Less than 22 data points returns empty."""
        detail = {"price_history": [100.0] * 10, "dividend_yield": 0.01}
        result = _estimate_from_history(detail)
        assert result["optimistic"] is None
        assert result["base"] is None

    def test_no_price_history(self):
        """No price history returns empty."""
        detail = {"price_history": None}
        result = _estimate_from_history(detail)
        assert result["optimistic"] is None

    def test_includes_dividend_yield(self):
        """Dividend yield is added to percentile returns."""
        # Flat prices → monthly return = 0
        prices = [100.0] * 130
        detail = {"price_history": prices, "dividend_yield": 0.05}
        result = _estimate_from_history(detail)
        # All percentiles should be 0 + 0.05 = 0.05
        if result["base"] is not None:
            assert abs(result["base"] - 0.05) < 0.01


# ---------------------------------------------------------------------------
# estimate_stock_return
# ---------------------------------------------------------------------------

class TestEstimateStockReturn:
    def test_stock_with_analyst(self):
        """Stock with analyst data uses analyst method."""
        detail = {
            "price": 100.0,
            "name": "Test Corp",
            "currency": "USD",
            "sector": "Technology",
            "target_high_price": 130.0,
            "target_mean_price": 115.0,
            "target_low_price": 90.0,
            "dividend_yield": 0.01,
            "number_of_analyst_opinions": 20,
            "recommendation_mean": 2.0,
            "forward_per": 22.0,
        }
        result = estimate_stock_return("AAPL", detail, news=[], x_sentiment=None)
        assert result["symbol"] == "AAPL"
        assert result["method"] == "analyst"
        assert result["base"] is not None

    def test_etf_uses_historical(self):
        """ETF with no analyst target uses historical method."""
        prices = [100.0 + i * 0.05 for i in range(130)]
        detail = {
            "price": 105.0,
            "name": "Gold ETF",
            "currency": "USD",
            "sector": None,
            "target_mean_price": None,
            "price_history": prices,
            "dividend_yield": 0.02,
        }
        result = estimate_stock_return("GLDM", detail, news=[], x_sentiment=None)
        assert result["method"] == "historical"

    def test_news_and_sentiment_passthrough(self):
        """News and sentiment data are passed through."""
        detail = {
            "price": 100.0,
            "name": "Test",
            "currency": "USD",
            "sector": "Tech",
            "target_mean_price": 120.0,
        }
        news = [{"title": "Good news", "publisher": "Reuters"}]
        sentiment = {"positive": ["Strong growth"], "negative": [], "sentiment_score": 0.8}
        result = estimate_stock_return("TEST", detail, news=news, x_sentiment=sentiment)
        assert len(result["news"]) == 1
        assert result["x_sentiment"]["sentiment_score"] == 0.8


# ---------------------------------------------------------------------------
# estimate_portfolio_return
# ---------------------------------------------------------------------------

class TestEstimatePortfolioReturn:
    @patch("src.core.portfolio_manager._infer_currency")
    @patch("src.core.portfolio_manager.get_fx_rates")
    @patch("src.core.portfolio_manager.load_portfolio")
    def test_portfolio_weighted_average(
        self, mock_load, mock_fx, mock_infer
    ):
        """Portfolio return is value-weighted average of stock returns."""
        mock_load.return_value = [
            {"symbol": "AAPL", "shares": 10, "cost_price": 150.0, "cost_currency": "USD"},
            {"symbol": "7203.T", "shares": 100, "cost_price": 2800.0, "cost_currency": "JPY"},
        ]
        mock_fx.return_value = {"JPY": 1.0, "USD": 150.0}
        mock_infer.return_value = "USD"

        # Mock yahoo_client
        mock_client = MagicMock()

        # AAPL detail
        aapl_detail = {
            "price": 200.0,
            "name": "Apple",
            "currency": "USD",
            "sector": "Technology",
            "target_high_price": 250.0,
            "target_mean_price": 220.0,
            "target_low_price": 180.0,
            "dividend_yield": 0.005,
            "number_of_analyst_opinions": 40,
            "recommendation_mean": 2.0,
            "forward_per": 28.0,
        }
        # 7203.T detail
        toyota_detail = {
            "price": 3000.0,
            "name": "Toyota",
            "currency": "JPY",
            "sector": "Consumer Cyclical",
            "target_high_price": 3500.0,
            "target_mean_price": 3200.0,
            "target_low_price": 2700.0,
            "dividend_yield": 0.025,
            "number_of_analyst_opinions": 20,
            "recommendation_mean": 2.5,
            "forward_per": 10.0,
        }

        def mock_get_detail(symbol):
            if symbol == "AAPL":
                return aapl_detail
            return toyota_detail

        mock_client.get_stock_detail.side_effect = mock_get_detail
        mock_client.get_stock_news.return_value = []

        # Patch grok_client import inside estimate_portfolio_return
        with patch.dict("sys.modules", {"src.data.grok_client": MagicMock(is_available=lambda: False)}):
            result = estimate_portfolio_return("/fake/path.csv", mock_client)

        assert len(result["positions"]) == 2
        assert result["portfolio"]["base"] is not None
        assert result["total_value_jpy"] > 0

    @patch("src.core.portfolio_manager.load_portfolio")
    def test_empty_portfolio(self, mock_load):
        """Empty portfolio returns empty result."""
        mock_load.return_value = []
        mock_client = MagicMock()

        result = estimate_portfolio_return("/fake/path.csv", mock_client)
        assert result["positions"] == []
        assert result["portfolio"]["base"] is None
