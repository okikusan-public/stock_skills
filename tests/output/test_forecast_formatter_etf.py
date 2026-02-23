"""Tests for KIK-469 Phase 2: Forecast formatter ETF display."""

import pytest
from src.output.forecast_formatter import format_return_estimate


def _make_stock_forecast(symbol, method="analyst", base=0.08):
    """Helper for a stock forecast position."""
    return {
        "symbol": symbol,
        "name": symbol,
        "price": 2800,
        "currency": "JPY",
        "dividend_yield": 0.025,
        "buyback_yield": 0.01,
        "is_etf": False,
        "method": method,
        "base": base,
        "optimistic": base + 0.05,
        "pessimistic": base - 0.05,
        "analyst_count": 10,
        "target_high": 3500,
        "target_mean": 3000,
        "target_low": 2500,
        "recommendation_mean": 2.5,
        "forward_per": 12.0,
        "annualized_volatility": None,
        "news": [],
        "x_sentiment": None,
        "value_trap_warning": None,
        "catalyst_adjustment": 0.0,
    }


def _make_etf_forecast(symbol, base=0.06, volatility=0.15):
    """Helper for an ETF forecast position."""
    return {
        "symbol": symbol,
        "name": symbol,
        "price": 68.5,
        "currency": "USD",
        "dividend_yield": 0.031,
        "buyback_yield": 0.0,
        "is_etf": True,
        "method": "historical",
        "base": base,
        "optimistic": base + 0.1,
        "pessimistic": base - 0.1,
        "analyst_count": None,
        "target_high": None,
        "target_mean": None,
        "target_low": None,
        "recommendation_mean": None,
        "forward_per": None,
        "data_months": 36,
        "annualized_volatility": volatility,
        "news": [],
        "x_sentiment": None,
        "value_trap_warning": None,
        "catalyst_adjustment": 0.0,
    }


def _make_forecast_data(positions):
    """Build forecast data dict."""
    return {
        "positions": positions,
        "portfolio": {
            "base": 0.07,
            "optimistic": 0.12,
            "pessimistic": 0.02,
        },
        "total_value_jpy": 10000000,
        "fx_rates": {},
    }


class TestForecastFormatterETF:
    """Test forecast formatter ETF-specific display."""

    def test_etf_badge_in_header(self):
        """ETF should have [ETF] badge in header."""
        data = _make_forecast_data([_make_etf_forecast("VGK")])
        output = format_return_estimate(data)
        assert "[ETF]" in output
        assert "VGK" in output

    def test_stock_no_badge(self):
        """Regular stock should not have [ETF] badge."""
        data = _make_forecast_data([_make_stock_forecast("7203.T")])
        output = format_return_estimate(data)
        assert "[ETF]" not in output

    def test_etf_volatility_displayed(self):
        """ETF with historical method should show volatility."""
        data = _make_forecast_data([_make_etf_forecast("VGK", volatility=0.15)])
        output = format_return_estimate(data)
        assert "年率ボラティリティ" in output
        assert "15.0%" in output

    def test_stock_no_volatility(self):
        """Stock with analyst method should not show volatility."""
        data = _make_forecast_data([_make_stock_forecast("7203.T")])
        output = format_return_estimate(data)
        assert "年率ボラティリティ" not in output

    def test_etf_volatility_none_not_displayed(self):
        """ETF with None volatility should not show volatility line."""
        pos = _make_etf_forecast("VGK", volatility=None)
        pos["annualized_volatility"] = None
        data = _make_forecast_data([pos])
        output = format_return_estimate(data)
        assert "年率ボラティリティ" not in output
