"""Tests for src/core/screening/contrarian.py (KIK-504, KIK-519)."""

import numpy as np
import pandas as pd
import pytest

from src.core.screening.contrarian import (
    compute_technical_contrarian,
    compute_valuation_contrarian,
    compute_fundamental_divergence,
    compute_sentiment_contrarian,
    compute_contrarian_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hist(
    n_days: int = 250,
    base_price: float = 1000.0,
    trend: str = "flat",
    crash_pct: float = 0.0,
    volume_surge: bool = False,
) -> pd.DataFrame:
    """Generate synthetic price history for testing."""
    dates = pd.bdate_range(end="2026-02-27", periods=n_days)
    rng = np.random.RandomState(42)

    if trend == "flat":
        prices = base_price + rng.randn(n_days).cumsum() * 2
    elif trend == "down":
        prices = base_price + np.linspace(0, -base_price * crash_pct, n_days)
        prices += rng.randn(n_days) * 5
    elif trend == "up":
        prices = base_price + np.linspace(0, base_price * 0.3, n_days)
        prices += rng.randn(n_days) * 5
    else:
        prices = np.full(n_days, base_price)

    prices = np.maximum(prices, 1)  # avoid negative prices

    volumes = rng.randint(100_000, 500_000, size=n_days).astype(float)
    if volume_surge:
        # Last 5 days have 3x volume
        volumes[-5:] = volumes[-5:] * 3

    return pd.DataFrame(
        {"Close": prices, "Volume": volumes},
        index=dates,
    )


def _make_oversold_hist() -> pd.DataFrame:
    """Generate history where RSI is very low (sharp recent decline)."""
    n = 250
    dates = pd.bdate_range(end="2026-02-27", periods=n)
    prices = np.full(n, 1000.0)
    # Stable for 200 days, then sharp drop in last 50 days
    prices[200:] = np.linspace(1000, 600, 50)
    volumes = np.full(n, 300_000.0)
    volumes[-5:] = 900_000  # volume surge
    return pd.DataFrame({"Close": prices, "Volume": volumes}, index=dates)


# ---------------------------------------------------------------------------
# Technical contrarian tests
# ---------------------------------------------------------------------------

class TestTechnicalContrarian:
    def test_oversold_high_score(self):
        hist = _make_oversold_hist()
        result = compute_technical_contrarian(hist)
        assert result["score"] > 15  # RSI low + SMA deviation + maybe BB
        assert result["rsi"] is not None
        assert result["rsi"] < 40  # should be oversold after sharp drop
        assert result["sma200_deviation"] < 0

    def test_neutral_zero_score(self):
        hist = _make_hist(trend="flat", base_price=1000)
        result = compute_technical_contrarian(hist)
        # Flat trend → RSI ~50, no SMA deviation → low score
        assert result["score"] <= 10
        assert result["rsi"] is not None

    def test_uptrend_zero_tech(self):
        hist = _make_hist(trend="up", base_price=1000)
        result = compute_technical_contrarian(hist)
        # RSI should be high, no deviation → low score
        assert result["score"] <= 5

    def test_insufficient_data(self):
        hist = pd.DataFrame({"Close": [100, 101, 102], "Volume": [1000, 1000, 1000]})
        result = compute_technical_contrarian(hist)
        assert result["score"] == 0
        assert result["rsi"] is None

    def test_none_hist(self):
        result = compute_technical_contrarian(None)
        assert result["score"] == 0

    def test_volume_surge_bonus(self):
        hist = _make_oversold_hist()
        result = compute_technical_contrarian(hist)
        assert result["volume_surge"] is not None
        assert result["volume_surge"] > 1.0

    def test_sma200_deviation_reported(self):
        hist = _make_oversold_hist()
        result = compute_technical_contrarian(hist)
        assert result["sma200_deviation"] is not None
        assert result["sma200_deviation"] < 0

    def test_details_present(self):
        hist = _make_oversold_hist()
        result = compute_technical_contrarian(hist)
        details = result["details"]
        assert "rsi_score" in details
        assert "sma_score" in details
        assert "bb_score" in details
        assert "vol_score" in details


# ---------------------------------------------------------------------------
# Valuation contrarian tests
# ---------------------------------------------------------------------------

class TestValuationContrarian:
    def test_cheap_healthy_high_score(self):
        """Low PER + positive EPS growth → high PER score."""
        data = {"per": 7, "pbr": 0.4, "roe": 0.12, "eps_growth": 0.05}
        result = compute_valuation_contrarian(data)
        assert result["per_signal"] == 15.0  # PER<8 & eps>=0
        assert result["pbr_signal"] == 15.0  # PBR<0.5 & ROE>5%
        assert result["score"] == 30.0

    def test_value_trap_low_score(self):
        """Low PER + negative EPS growth → no PER bonus (value trap)."""
        data = {"per": 7, "pbr": 0.4, "roe": 0.03, "eps_growth": -0.10}
        result = compute_valuation_contrarian(data)
        assert result["per_signal"] == 4.0  # Falls through to PER<15 base
        assert result["pbr_signal"] == 4.0  # ROE<5% → falls to PBR<1.5 base

    def test_moderate_per_with_growth(self):
        """PER 11 + positive EPS growth → mid score."""
        data = {"per": 11, "pbr": 0.9, "roe": 0.10, "eps_growth": 0.05}
        result = compute_valuation_contrarian(data)
        assert result["per_signal"] == 8.0  # PER<12 & eps>0
        assert result["pbr_signal"] == 8.0  # PBR<1.0 & ROE>8%

    def test_high_per_zero_score(self):
        """High PER → no contrarian signal."""
        data = {"per": 25, "pbr": 2.5, "roe": 0.15, "eps_growth": 0.10}
        result = compute_valuation_contrarian(data)
        assert result["per_signal"] == 0.0
        assert result["pbr_signal"] == 0.0

    def test_none_values(self):
        data = {"per": None, "pbr": None, "roe": None, "eps_growth": None}
        result = compute_valuation_contrarian(data)
        assert result["score"] == 0.0

    def test_per_boundary_15(self):
        """PER = 14.5 (< 15) → base 4pt."""
        data = {"per": 14.5, "pbr": 2.0, "roe": 0.03, "eps_growth": -0.05}
        result = compute_valuation_contrarian(data)
        assert result["per_signal"] == 4.0

    def test_per_boundary_8(self):
        """PER = 8 (not < 8) with eps_growth=0 → 12pt (PER<10)."""
        data = {"per": 8, "pbr": 1.0, "roe": 0.10, "eps_growth": 0.0}
        result = compute_valuation_contrarian(data)
        assert result["per_signal"] == 12.0

    def test_pbr_boundary_08(self):
        """PBR = 0.6 (< 0.8) with ROE > 5% → 12pt."""
        data = {"per": 20, "pbr": 0.6, "roe": 0.06, "eps_growth": 0.0}
        result = compute_valuation_contrarian(data)
        assert result["pbr_signal"] == 12.0

    def test_negative_per_ignored(self):
        """Negative PER → 0pt."""
        data = {"per": -5, "pbr": 0.5, "roe": 0.10, "eps_growth": 0.05}
        result = compute_valuation_contrarian(data)
        assert result["per_signal"] == 0.0


# ---------------------------------------------------------------------------
# Fundamental divergence tests
# ---------------------------------------------------------------------------

class TestFundamentalDivergence:
    def test_high_fcf_yield(self):
        data = {"fcf": 200, "market_cap": 1000, "roe": 0.05, "dividend_yield": 0.01}
        result = compute_fundamental_divergence(data)
        assert result["fcf_signal"] == 10.0  # 20% yield
        assert result["details"]["fcf_yield"] == pytest.approx(0.2)

    def test_good_roe(self):
        data = {"fcf": None, "market_cap": None, "roe": 0.16, "dividend_yield": 0.01}
        result = compute_fundamental_divergence(data)
        assert result["roe_signal"] == 10.0

    def test_medium_roe(self):
        data = {"fcf": None, "market_cap": None, "roe": 0.09, "dividend_yield": None}
        result = compute_fundamental_divergence(data)
        assert result["roe_signal"] == 5.0

    def test_good_dividend(self):
        data = {"fcf": None, "market_cap": None, "roe": None, "dividend_yield_trailing": 0.04}
        result = compute_fundamental_divergence(data)
        assert result["return_signal"] == 8.0  # 4% > 3%

    def test_high_dividend(self):
        data = {"fcf": None, "market_cap": None, "roe": None, "dividend_yield_trailing": 0.06}
        result = compute_fundamental_divergence(data)
        assert result["return_signal"] == 10.0  # 6% > 5%

    def test_all_strong(self):
        data = {
            "fcf": 120, "market_cap": 1000,
            "roe": 0.18,
            "dividend_yield_trailing": 0.06,
        }
        result = compute_fundamental_divergence(data)
        assert result["score"] == 30.0  # 10+10+10

    def test_all_none(self):
        data = {}
        result = compute_fundamental_divergence(data)
        assert result["score"] == 0.0

    def test_fcf_boundary(self):
        data = {"fcf": 35, "market_cap": 1000, "roe": None, "dividend_yield": None}
        result = compute_fundamental_divergence(data)
        assert result["fcf_signal"] == 2.0  # 3.5% > 3%


# ---------------------------------------------------------------------------
# Composite score tests
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_grade_a(self):
        """All axes strong → grade A."""
        hist = _make_oversold_hist()
        data = {
            "per": 6, "pbr": 0.4, "roe": 0.18, "eps_growth": 0.10,
            "fcf": 120, "market_cap": 1000,
            "dividend_yield_trailing": 0.06,
        }
        result = compute_contrarian_score(hist, data)
        assert result["grade"] in ("A", "B")  # technical depends on hist
        assert result["contrarian_score"] >= 50
        assert result["is_contrarian"] is True

    def test_grade_d(self):
        """All axes weak → grade D."""
        hist = _make_hist(trend="up")  # RSI high
        data = {"per": 30, "pbr": 3.0, "roe": 0.03, "eps_growth": -0.10}
        result = compute_contrarian_score(hist, data)
        assert result["grade"] == "D"
        assert result["is_contrarian"] is False

    def test_none_hist_still_scores(self):
        """hist=None → technical=0, valuation+fundamental still scored."""
        data = {
            "per": 7, "pbr": 0.4, "roe": 0.15, "eps_growth": 0.05,
            "fcf": 100, "market_cap": 1000,
            "dividend_yield_trailing": 0.04,
        }
        result = compute_contrarian_score(None, data)
        assert result["technical"]["score"] == 0.0
        assert result["valuation"]["score"] > 0
        assert result["fundamental"]["score"] > 0
        assert result["contrarian_score"] > 0

    def test_only_technical(self):
        """Strong technicals, weak fundamentals."""
        hist = _make_oversold_hist()
        data = {"per": 30, "pbr": 3.0, "roe": 0.02, "eps_growth": -0.20}
        result = compute_contrarian_score(hist, data)
        assert result["technical"]["score"] > 0
        assert result["valuation"]["score"] <= 8  # maybe base 4+4
        assert result["fundamental"]["score"] <= 5

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        hist = _make_oversold_hist()
        data = {
            "per": 5, "pbr": 0.3, "roe": 0.20, "eps_growth": 0.15,
            "fcf": 200, "market_cap": 1000,
            "dividend_yield_trailing": 0.08,
        }
        result = compute_contrarian_score(hist, data)
        assert result["contrarian_score"] <= 100.0

    def test_grade_boundaries(self):
        """Verify grade assignment boundaries."""
        hist = None
        # Score = 30 (valuation only: per 15pt + pbr 15pt)
        data = {"per": 7, "pbr": 0.4, "roe": 0.10, "eps_growth": 0.05}
        result = compute_contrarian_score(hist, data)
        val_score = result["valuation"]["score"]
        fund_score = result["fundamental"]["score"]
        total = val_score + fund_score
        if total >= 70:
            assert result["grade"] == "A"
        elif total >= 50:
            assert result["grade"] == "B"
        elif total >= 30:
            assert result["grade"] == "C"
        else:
            assert result["grade"] == "D"

    def test_result_structure(self):
        """Verify all expected keys are present."""
        result = compute_contrarian_score(None, {})
        assert "contrarian_score" in result
        assert "technical" in result
        assert "valuation" in result
        assert "fundamental" in result
        assert "grade" in result
        assert "is_contrarian" in result
        assert "score" in result["technical"]
        assert "score" in result["valuation"]
        assert "score" in result["fundamental"]


# ---------------------------------------------------------------------------
# Sentiment contrarian tests (KIK-519)
# ---------------------------------------------------------------------------

class TestSentimentContrarian:
    def test_very_negative_max_score(self):
        result = compute_sentiment_contrarian(-0.7)
        assert result["score"] == 20.0

    def test_negative_score(self):
        result = compute_sentiment_contrarian(-0.4)
        assert result["score"] == 15.0

    def test_slightly_negative_score(self):
        result = compute_sentiment_contrarian(-0.2)
        assert result["score"] == 10.0

    def test_neutral_score(self):
        result = compute_sentiment_contrarian(0.0)
        assert result["score"] == 5.0

    def test_positive_zero_score(self):
        result = compute_sentiment_contrarian(0.5)
        assert result["score"] == 0.0

    def test_none_returns_zero(self):
        result = compute_sentiment_contrarian(None)
        assert result["score"] == 0.0
        assert result["sentiment_score"] is None

    def test_boundary_minus_05(self):
        """Exactly -0.5 triggers the < -0.5 bracket → 15pt (not 20pt)."""
        result = compute_sentiment_contrarian(-0.5)
        assert result["score"] == 15.0  # -0.5 is NOT < -0.5

    def test_boundary_minus_03(self):
        """Exactly -0.3 is NOT < -0.3, so falls to 10pt bracket."""
        result = compute_sentiment_contrarian(-0.3)
        assert result["score"] == 10.0

    def test_boundary_minus_01(self):
        """Exactly -0.1 is NOT < -0.1, so falls to 5pt bracket."""
        result = compute_sentiment_contrarian(-0.1)
        assert result["score"] == 5.0

    def test_boundary_plus_01(self):
        """Exactly 0.1 is NOT < 0.1, so falls to 0pt bracket."""
        result = compute_sentiment_contrarian(0.1)
        assert result["score"] == 0.0

    def test_result_structure(self):
        result = compute_sentiment_contrarian(-0.3)
        assert "score" in result
        assert "sentiment_score" in result
        assert "details" in result
        assert result["sentiment_score"] == -0.3


# ---------------------------------------------------------------------------
# 4-axis composite score tests (KIK-519)
# ---------------------------------------------------------------------------

class TestCompositeScore4Axis:
    def test_4axis_with_negative_sentiment(self):
        """4-axis scoring includes sentiment key and boosts on negative sentiment."""
        data = {
            "per": 7, "pbr": 0.4, "roe": 0.15, "eps_growth": 0.05,
            "fcf": 100, "market_cap": 1000,
            "dividend_yield_trailing": 0.04,
        }
        result = compute_contrarian_score(None, data, sentiment_score=-0.6)
        assert "sentiment" in result
        assert result["sentiment"]["score"] == 20.0

    def test_4axis_positive_sentiment_no_boost(self):
        """Positive sentiment → sentiment score 0."""
        data = {"per": 7, "pbr": 0.4, "roe": 0.10, "eps_growth": 0.05}
        result = compute_contrarian_score(None, data, sentiment_score=0.5)
        assert "sentiment" in result
        assert result["sentiment"]["score"] == 0.0

    def test_backward_compat_no_sentiment(self):
        """Without sentiment_score, behavior is unchanged (3-axis)."""
        data = {
            "per": 7, "pbr": 0.4, "roe": 0.15, "eps_growth": 0.05,
            "fcf": 100, "market_cap": 1000,
            "dividend_yield_trailing": 0.04,
        }
        result = compute_contrarian_score(None, data)
        assert "sentiment" not in result
        # Score is simple sum of valuation + fundamental (tech=0 with None hist)
        expected = result["valuation"]["score"] + result["fundamental"]["score"]
        assert result["contrarian_score"] == pytest.approx(expected, abs=0.2)

    def test_4axis_score_capped_at_100(self):
        """4-axis score should never exceed 100."""
        hist = _make_oversold_hist()
        data = {
            "per": 5, "pbr": 0.3, "roe": 0.20, "eps_growth": 0.15,
            "fcf": 200, "market_cap": 1000,
            "dividend_yield_trailing": 0.08,
        }
        result = compute_contrarian_score(hist, data, sentiment_score=-0.8)
        assert result["contrarian_score"] <= 100.0

    def test_4axis_grade_assignment(self):
        """4-axis grade assignment follows same boundaries."""
        data = {"per": 7, "pbr": 0.4, "roe": 0.15, "eps_growth": 0.05}
        result = compute_contrarian_score(None, data, sentiment_score=-0.6)
        score = result["contrarian_score"]
        if score >= 70:
            assert result["grade"] == "A"
        elif score >= 50:
            assert result["grade"] == "B"
        elif score >= 30:
            assert result["grade"] == "C"
        else:
            assert result["grade"] == "D"

    def test_4axis_rescaling(self):
        """4-axis rescaling: sentiment adds points, 3-axis components scale down."""
        # With sentiment: tech 30 + val 25 + fund 25 + sent 20 = 100
        # Without sentiment: tech 40 + val 30 + fund 30 = 100
        data = {
            "per": 5, "pbr": 0.3, "roe": 0.20, "eps_growth": 0.15,
            "fcf": 200, "market_cap": 1000,
            "dividend_yield_trailing": 0.08,
        }
        result_3axis = compute_contrarian_score(None, data)
        result_4axis = compute_contrarian_score(None, data, sentiment_score=-0.8)
        # 4-axis should include sentiment component
        assert "sentiment" in result_4axis
        assert result_4axis["sentiment"]["score"] == 20.0  # -0.8 → max 20pt
        # 3-axis val+fund only (no hist → tech=0). 4-axis should also have val+fund
        assert result_3axis["contrarian_score"] > 0
        assert result_4axis["contrarian_score"] > result_3axis["contrarian_score"]
        # The difference should be roughly the sentiment contribution
        # 3-axis: val + fund raw scores. 4-axis: scaled val + scaled fund + sent 20
        diff = result_4axis["contrarian_score"] - result_3axis["contrarian_score"]
        # Sentiment adds ~20pt but scaling reduces other axes, so net gain is positive
        assert diff > 0
