"""Tests for src.core.risk.shock_sensitivity module."""

import math

import numpy as np
import pandas as pd
import pytest

from src.core.risk.shock_sensitivity import (
    _clamp,
    _safe_float,
    classify_quadrant,
    compute_fundamental_sensitivity,
    compute_integrated_shock,
    compute_technical_sensitivity,
    analyze_stock_sensitivity,
)


# ---------------------------------------------------------------------------
# Helper: generate synthetic price history DataFrame
# ---------------------------------------------------------------------------

def _make_hist(
    prices: list[float],
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    """Create a DataFrame that mimics yahoo_client.get_price_history()."""
    n = len(prices)
    dates = pd.bdate_range(end="2025-06-01", periods=n)
    if volumes is None:
        volumes = [1_000_000] * n
    return pd.DataFrame({"Close": prices, "Volume": volumes}, index=dates)


def _trending_up_then_flat(n: int = 120, base: float = 100.0) -> list[float]:
    """Generate prices that trend up steadily then flatten at the end."""
    # 100 days of gradual upward, then 20 days flat/sideways
    up = [base + i * 0.5 for i in range(n - 20)]
    flat = [up[-1]] * 20
    return up + flat


# ===================================================================
# _clamp / _safe_float helpers
# ===================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(1.0) == 1.0

    def test_below_floor(self):
        assert _clamp(0.1) == 0.5

    def test_above_ceiling(self):
        assert _clamp(3.0) == 2.0

    def test_exact_boundaries(self):
        assert _clamp(0.5) == 0.5
        assert _clamp(2.0) == 2.0


class TestSafeFloat:
    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_nan(self):
        assert _safe_float(float("nan")) == 0.0

    def test_inf(self):
        assert _safe_float(float("inf")) == 0.0

    def test_valid_float(self):
        assert _safe_float(3.14) == 3.14

    def test_string_number(self):
        assert _safe_float("2.5") == 2.5

    def test_non_numeric_string(self):
        assert _safe_float("abc", default=99.0) == 99.0


# ===================================================================
# Layer 1: compute_fundamental_sensitivity
# ===================================================================


class TestFundamentalSensitivity:
    def test_high_per_low_dividend_gives_high_score(self):
        """High PER + low dividend -> more vulnerable -> score > 1.0."""
        info = {
            "per": 50.0,       # PER > 30 -> per_score = 1.5
            "pbr": 4.0,        # PBR > 3  -> pbr_score = 1.3
            "dividend_yield": 0.005,  # < 1% -> dividend_score = 1.3
            "market_cap": 5e10,  # small cap -> size_score = 1.3
            "beta": 1.5,       # high beta
        }
        result = compute_fundamental_sensitivity(info)
        assert result["score"] > 1.0
        assert result["per_score"] == 1.5
        assert result["dividend_score"] == 1.3

    def test_low_per_high_dividend_gives_low_score(self):
        """Low PER + high dividend -> more resilient -> score < 1.0."""
        info = {
            "per": 8.0,        # PER < 15 -> per_score = 0.7
            "pbr": 0.5,        # PBR < 1  -> pbr_score = 0.7
            "dividend_yield": 0.05,   # >= 3% -> dividend_score = 0.7
            "market_cap": 2e12,  # large cap -> size_score = 0.8
            "beta": 0.5,       # low beta -> volatility_score = 0.8
        }
        result = compute_fundamental_sensitivity(info)
        assert result["score"] < 1.0
        assert result["per_score"] == 0.7
        assert result["pbr_score"] == 0.7
        assert result["dividend_score"] == 0.7

    def test_negative_per_treated_as_vulnerable(self):
        """Negative PER (loss-making) -> per_score = 1.5."""
        info = {"per": -5.0, "pbr": 1.0, "dividend_yield": 0.02, "market_cap": 1e11, "beta": 1.0}
        result = compute_fundamental_sensitivity(info)
        assert result["per_score"] == 1.5

    def test_zero_per_treated_as_vulnerable(self):
        """Zero PER -> per_score = 1.5."""
        info = {"per": 0.0, "pbr": 1.0, "dividend_yield": 0.02, "market_cap": 1e11, "beta": 1.0}
        result = compute_fundamental_sensitivity(info)
        assert result["per_score"] == 1.5

    def test_mid_range_per_neutral(self):
        """PER between 15 and 30 -> per_score = 1.0."""
        info = {"per": 20.0, "pbr": 2.0, "dividend_yield": 0.02, "market_cap": 5e11, "beta": 1.0}
        result = compute_fundamental_sensitivity(info)
        assert result["per_score"] == 1.0

    def test_score_clamped_to_range(self):
        """Score must be between 0.5 and 2.0."""
        # Even with all max-vulnerable values
        info = {
            "per": 100.0, "pbr": 10.0, "dividend_yield": 0.0,
            "market_cap": 1e9, "beta": 3.0,
        }
        result = compute_fundamental_sensitivity(info)
        assert 0.5 <= result["score"] <= 2.0

    def test_missing_fields_default_gracefully(self):
        """Missing fields default to 0.0 via _safe_float."""
        result = compute_fundamental_sensitivity({})
        assert 0.5 <= result["score"] <= 2.0

    def test_detail_string_populated(self):
        """Detail string should contain relevant info."""
        info = {"per": 50.0, "pbr": 0.5, "dividend_yield": 0.05, "market_cap": 2e12, "beta": 1.0}
        result = compute_fundamental_sensitivity(info)
        assert isinstance(result["detail"], str)
        assert len(result["detail"]) > 0

    def test_high_beta_increases_volatility_score(self):
        """Beta > 1.2 -> volatility_score > 1.0, capped at 2.0."""
        info = {"per": 20.0, "pbr": 2.0, "dividend_yield": 0.02, "market_cap": 5e11, "beta": 2.0}
        result = compute_fundamental_sensitivity(info)
        assert result["volatility_score"] > 1.0

    def test_low_beta_reduces_volatility_score(self):
        """Beta < 0.8 -> volatility_score = 0.8."""
        info = {"per": 20.0, "pbr": 2.0, "dividend_yield": 0.02, "market_cap": 5e11, "beta": 0.5}
        result = compute_fundamental_sensitivity(info)
        assert result["volatility_score"] == 0.8


# ===================================================================
# Layer 2: compute_technical_sensitivity
# ===================================================================


class TestTechnicalSensitivity:
    def test_rsi_overbought_gives_high_score(self):
        """RSI > 70 -> rsi_score = 1.5 -> overall high score."""
        # Build a price series that drives RSI above 70:
        # strong consistent upward movement
        prices = [100.0 + i * 2.0 for i in range(60)]
        hist = _make_hist(prices)
        result = compute_technical_sensitivity(hist)
        # RSI should be high with consistent gains
        assert result["rsi_score"] >= 1.0
        assert result["score"] >= 1.0

    def test_rsi_low_gives_low_score(self):
        """RSI below 30 -> rsi_score = 0.9 (or 0.8 if 30-50)."""
        # Strong consistent downward movement
        prices = [200.0 - i * 2.0 for i in range(60)]
        hist = _make_hist(prices)
        result = compute_technical_sensitivity(hist)
        assert result["rsi_score"] <= 1.0

    def test_insufficient_data_returns_neutral(self):
        """Fewer than 50 data points -> neutral score = 1.0."""
        prices = [100.0 + i for i in range(30)]  # only 30 points
        hist = _make_hist(prices)
        result = compute_technical_sensitivity(hist)
        assert result["score"] == 1.0
        assert "データ不足" in result["detail"]

    def test_empty_dataframe_returns_neutral(self):
        """Empty DataFrame -> neutral."""
        hist = pd.DataFrame(columns=["Close", "Volume"])
        result = compute_technical_sensitivity(hist)
        assert result["score"] == 1.0

    def test_none_hist_returns_neutral(self):
        """None input -> neutral."""
        result = compute_technical_sensitivity(None)
        assert result["score"] == 1.0

    def test_missing_close_column_returns_neutral(self):
        """DataFrame without Close column -> neutral."""
        hist = pd.DataFrame({"Open": [100.0] * 60})
        result = compute_technical_sensitivity(hist)
        assert result["score"] == 1.0

    def test_score_always_clamped(self):
        """Score must be between 0.5 and 2.0."""
        prices = _trending_up_then_flat(120)
        hist = _make_hist(prices)
        result = compute_technical_sensitivity(hist)
        assert 0.5 <= result["score"] <= 2.0

    def test_surge_detection(self):
        """A big 30-day price jump should increase surge_score."""
        # Flat for 60 days, then sharp rise in last 30 days
        prices = [100.0] * 60 + [100.0 + i * 5 for i in range(1, 31)]
        hist = _make_hist(prices)
        result = compute_technical_sensitivity(hist)
        # With a >100% rise in 30 days, surge_score should be elevated
        assert result["surge_score"] >= 1.0

    def test_volume_heat_detection(self):
        """High recent volume vs. 20-day average should raise volume_heat_score."""
        prices = [100.0 + i * 0.1 for i in range(60)]
        # Low volume for first 55 days, high volume for last 5
        volumes = [100_000] * 55 + [500_000] * 5
        hist = _make_hist(prices, volumes)
        result = compute_technical_sensitivity(hist)
        assert result["volume_heat_score"] >= 1.0


# ===================================================================
# classify_quadrant
# ===================================================================


class TestClassifyQuadrant:
    def test_most_dangerous(self):
        """f > 1.2 and t > 1.2 -> quadrant is '最危険'."""
        result = classify_quadrant(1.5, 1.5)
        assert result["quadrant"] == "最危険"

    def test_bottom_fall_risk(self):
        """f > 1.2 and t < 0.9 -> '底抜けリスク'."""
        result = classify_quadrant(1.5, 0.7)
        assert result["quadrant"] == "底抜けリスク"

    def test_short_term_correction_risk(self):
        """f < 1.0 and t > 1.2 -> '短期調整リスク'."""
        result = classify_quadrant(0.8, 1.5)
        assert result["quadrant"] == "短期調整リスク"

    def test_strongest_resilience(self):
        """f < 1.0 and t < 0.9 -> '耐性最強'."""
        result = classify_quadrant(0.8, 0.7)
        assert result["quadrant"] == "耐性最強"

    def test_neutral_zone(self):
        """Middle values -> '中立'."""
        result = classify_quadrant(1.1, 1.0)
        assert result["quadrant"] == "中立"

    def test_result_has_emoji_and_description(self):
        """All results should have emoji and description keys."""
        result = classify_quadrant(1.5, 1.5)
        assert "emoji" in result
        assert "description" in result
        assert len(result["description"]) > 0


# ===================================================================
# compute_integrated_shock
# ===================================================================


class TestIntegratedShock:
    def test_base_calculation(self):
        """adjusted_shock = base * f * t * c."""
        result = compute_integrated_shock(
            base_shock=-0.20,
            fundamental_score=1.5,
            technical_score=1.2,
            concentration_multiplier=1.1,
        )
        expected = -0.20 * 1.5 * 1.2 * 1.1
        assert abs(result["adjusted_shock"] - round(expected, 6)) < 1e-5

    def test_neutral_scores_preserve_base_shock(self):
        """All scores = 1.0 -> adjusted_shock = base_shock."""
        result = compute_integrated_shock(-0.20, 1.0, 1.0, 1.0)
        assert abs(result["adjusted_shock"] - (-0.20)) < 1e-5

    def test_scores_clamped(self):
        """Out-of-range scores should be clamped."""
        result = compute_integrated_shock(-0.20, 5.0, 5.0, 0.1)
        # f and t clamped to 2.0, c floored at 0.5
        expected = -0.20 * 2.0 * 2.0 * 0.5
        assert abs(result["adjusted_shock"] - round(expected, 6)) < 1e-5

    def test_result_contains_quadrant(self):
        """Result should contain quadrant classification."""
        result = compute_integrated_shock(-0.20, 1.5, 1.5, 1.0)
        assert "quadrant" in result
        assert result["quadrant"]["quadrant"] == "最危険"

    def test_contributions_recorded(self):
        """Per-layer contributions should be in the result."""
        result = compute_integrated_shock(-0.20, 1.3, 0.8, 1.2)
        assert result["fundamental_contribution"] == 1.3
        assert result["technical_contribution"] == 0.8
        assert result["concentration_contribution"] == 1.2


# ===================================================================
# analyze_stock_sensitivity (integration)
# ===================================================================


class TestAnalyzeStockSensitivity:
    def test_with_valid_data(self):
        """Full integration test with mock stock_info and price history."""
        stock_info = {
            "symbol": "7203.T",
            "name": "Toyota",
            "per": 10.0,
            "pbr": 0.8,
            "dividend_yield": 0.035,
            "market_cap": 3e13,
            "beta": 0.9,
        }
        prices = _trending_up_then_flat(120, base=2000.0)
        hist = _make_hist(prices)

        result = analyze_stock_sensitivity(stock_info, hist, base_shock=-0.20)

        assert result["symbol"] == "7203.T"
        assert "fundamental" in result
        assert "technical" in result
        assert "integrated" in result
        assert "summary" in result
        # Fundamental score should be below 1.0 (good fundamentals)
        assert result["fundamental"]["score"] < 1.0

    def test_with_none_hist(self):
        """None hist -> technical = neutral (1.0)."""
        stock_info = {
            "symbol": "TEST",
            "name": "Test Corp",
            "per": 20.0,
            "pbr": 2.0,
            "dividend_yield": 0.02,
            "market_cap": 1e11,
            "beta": 1.0,
        }
        result = analyze_stock_sensitivity(stock_info, None)

        assert result["technical"]["score"] == 1.0
        assert result["technical"]["detail"] == "価格履歴なし"

    def test_with_empty_hist(self):
        """Empty DataFrame -> technical = neutral."""
        stock_info = {"symbol": "EMPTY", "per": 15.0, "pbr": 1.0,
                      "dividend_yield": 0.02, "market_cap": 1e11, "beta": 1.0}
        hist = pd.DataFrame()

        result = analyze_stock_sensitivity(stock_info, hist)
        assert result["technical"]["score"] == 1.0

    def test_concentration_multiplier_applied(self):
        """concentration_multiplier should affect integrated shock."""
        stock_info = {
            "symbol": "CONC",
            "per": 20.0, "pbr": 2.0, "dividend_yield": 0.02,
            "market_cap": 1e11, "beta": 1.0,
        }
        result_no_conc = analyze_stock_sensitivity(stock_info, None, concentration_multiplier=1.0)
        result_high_conc = analyze_stock_sensitivity(stock_info, None, concentration_multiplier=1.5)

        # Higher concentration -> larger (more negative) adjusted shock
        assert (
            result_high_conc["integrated"]["adjusted_shock"]
            < result_no_conc["integrated"]["adjusted_shock"]
        )

    def test_summary_contains_symbol(self):
        """Summary string should mention the symbol."""
        stock_info = {"symbol": "SUMM", "per": 15.0, "pbr": 1.0,
                      "dividend_yield": 0.02, "market_cap": 1e11, "beta": 1.0}
        result = analyze_stock_sensitivity(stock_info, None)
        assert "SUMM" in result["summary"]
