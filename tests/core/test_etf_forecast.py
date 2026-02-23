"""Tests for KIK-469 Phase 2: ETF volatility and is_etf in return estimates."""

import math
import pytest


class TestHistoryEstimateVolatility:
    """Test annualized_volatility in _estimate_from_history."""

    def test_history_estimate_has_volatility(self):
        """_estimate_from_history should include annualized_volatility."""
        from src.core.return_estimate import _estimate_from_history

        # Build a stock_detail with sufficient price_history (>22 points)
        prices = [100.0 + i * 0.5 for i in range(250)]
        detail = {"price_history": prices}
        result = _estimate_from_history(detail)
        assert "annualized_volatility" in result
        assert result["annualized_volatility"] is not None

    def test_volatility_is_positive(self):
        """annualized_volatility should be non-negative."""
        from src.core.return_estimate import _estimate_from_history

        prices = [100.0 + i * 0.3 for i in range(250)]
        detail = {"price_history": prices}
        result = _estimate_from_history(detail)
        assert result["annualized_volatility"] >= 0

    def test_volatility_reasonable_range(self):
        """annualized_volatility should be in a reasonable range (0-200%)."""
        from src.core.return_estimate import _estimate_from_history

        prices = [100.0 + i * 0.5 for i in range(250)]
        detail = {"price_history": prices}
        result = _estimate_from_history(detail)
        assert 0 <= result["annualized_volatility"] <= 2.0

    def test_insufficient_data_volatility_none(self):
        """Not enough price data should return None for volatility."""
        from src.core.return_estimate import _estimate_from_history

        detail = {"price_history": [100.0, 101.0]}  # too few
        result = _estimate_from_history(detail)
        assert result["annualized_volatility"] is None


class TestAnalystEstimateVolatility:
    """Test that analyst method returns None for volatility."""

    def test_analyst_estimate_volatility_none(self):
        """_estimate_from_analyst should have annualized_volatility=None."""
        from src.core.return_estimate import _estimate_from_analyst

        detail = {
            "target_high_price": 3500,
            "target_low_price": 2500,
            "target_mean_price": 3000,
            "number_of_analyst_opinions": 10,
            "price": 2800,
            "recommendation_mean": 2.5,
            "forward_per": 12.0,
        }
        result = _estimate_from_analyst(detail)
        assert "annualized_volatility" in result
        assert result["annualized_volatility"] is None


class TestEmptyEstimateVolatility:
    """Test that _empty_estimate includes volatility key."""

    def test_empty_estimate_has_volatility_key(self):
        """_empty_estimate should include annualized_volatility=None."""
        from src.core.return_estimate import _empty_estimate

        result = _empty_estimate("historical")
        assert "annualized_volatility" in result
        assert result["annualized_volatility"] is None


class TestEstimateStockReturnETFFlag:
    """Test is_etf flag in estimate_stock_return."""

    def test_estimate_stock_return_etf_flag(self, etf_detail_data):
        """ETF should have is_etf=True in estimate result."""
        from src.core.return_estimate import estimate_stock_return

        result = estimate_stock_return("VGK", etf_detail_data)
        assert result["is_etf"] is True

    def test_estimate_stock_return_stock_flag(self, stock_detail_data):
        """Regular stock should have is_etf=False in estimate result."""
        from src.core.return_estimate import estimate_stock_return

        result = estimate_stock_return("7203.T", stock_detail_data)
        assert result["is_etf"] is False
