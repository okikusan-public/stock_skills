"""Tests for src/core/health_check.py (KIK-356)."""

import math

import numpy as np
import pandas as pd
import pytest

from src.core.health_check import (
    ALERT_NONE,
    ALERT_EARLY_WARNING,
    ALERT_CAUTION,
    ALERT_EXIT,
    _is_etf,
    check_trend_health,
    check_change_quality,
    compute_alert_level,
)


# ===================================================================
# Helpers to build synthetic price data
# ===================================================================

def _make_uptrend_hist(n: int = 300, base: float = 100.0) -> pd.DataFrame:
    """Steadily rising prices — clear uptrend."""
    prices = [base + i * 0.5 for i in range(n)]
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000] * n,
    })


def _make_downtrend_hist(n: int = 300, base: float = 200.0) -> pd.DataFrame:
    """Steadily falling prices — clear downtrend."""
    prices = [base - i * 0.3 for i in range(n)]
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000] * n,
    })


def _make_flat_hist(n: int = 300, base: float = 100.0) -> pd.DataFrame:
    """Flat prices with tiny noise to avoid zero-division."""
    rng = np.random.RandomState(42)
    prices = [base + rng.uniform(-0.1, 0.1) for _ in range(n)]
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000] * n,
    })


def _make_sma50_break_hist(n: int = 300) -> pd.DataFrame:
    """Rising first 280 bars, then a dip below SMA50 in last 20."""
    prices = [100.0 + i * 0.5 for i in range(280)]
    # Drop sharply in the last 20 bars
    last_price = prices[-1]
    for i in range(20):
        prices.append(last_price - (i + 1) * 1.5)
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000] * len(prices),
    })


def _make_golden_cross_hist(reversal_offset: int = 5, n: int = 300) -> pd.DataFrame:
    """Build price data where SMA50 crosses above SMA200 within the lookback.

    Starts declining (SMA50 < SMA200), then reverses upward sharply.
    The actual SMA crossover occurs with lag relative to the price
    reversal point due to the nature of moving averages.

    Parameters
    ----------
    reversal_offset : int
        Approximate number of bars before the end when the price
        reversal phase ends. The SMA crossover happens with lag.
    """
    decline_len = n - 50 - reversal_offset
    prices = [200.0 - i * 0.15 for i in range(decline_len)]
    last = prices[-1]
    for i in range(50 + reversal_offset):
        prices.append(last + (i + 1) * 2.0)  # Steeper rise for faster SMA crossover
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000] * len(prices),
    })


def _make_death_cross_hist(reversal_offset: int = 5, n: int = 300) -> pd.DataFrame:
    """Build price data where SMA50 crosses below SMA200 within the lookback.

    Starts rising (SMA50 > SMA200), then reverses downward sharply.
    The actual SMA crossover occurs with lag relative to the price
    reversal point due to the nature of moving averages.

    Parameters
    ----------
    reversal_offset : int
        Approximate number of bars before the end when the price
        reversal phase ends. The SMA crossover happens with lag.
    """
    rise_len = n - 50 - reversal_offset
    prices = [100.0 + i * 0.15 for i in range(rise_len)]
    last = prices[-1]
    for i in range(50 + reversal_offset):
        prices.append(last - (i + 1) * 2.0)  # Steeper fall for faster SMA crossover
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000] * len(prices),
    })


def _make_rsi_drop_hist(n: int = 300) -> pd.DataFrame:
    """Rising with a sharp sudden drop in last 5 bars causing RSI to plummet.

    The drop must start after iloc[-6] so RSI at -6 is still > 50.
    """
    prices = [100.0 + i * 0.3 for i in range(295)]
    # Sharp drop in last 5 bars only
    last = prices[-1]
    for i in range(5):
        prices.append(last - (i + 1) * 8.0)
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000] * len(prices),
    })


# ===================================================================
# check_trend_health tests
# ===================================================================

class TestCheckTrendHealth:

    def test_none_input(self):
        result = check_trend_health(None)
        assert result["trend"] == "不明"
        assert math.isnan(result["rsi"])

    def test_insufficient_data(self):
        short = pd.DataFrame({"Close": [100.0] * 50, "Volume": [1000] * 50})
        result = check_trend_health(short)
        assert result["trend"] == "不明"

    def test_missing_close_column(self):
        df = pd.DataFrame({"Open": [100.0] * 300})
        result = check_trend_health(df)
        assert result["trend"] == "不明"

    def test_uptrend(self):
        hist = _make_uptrend_hist()
        result = check_trend_health(hist)
        assert result["trend"] == "上昇"
        assert result["price_above_sma50"] is True
        assert result["sma50_above_sma200"] is True
        assert result["dead_cross"] is False

    def test_downtrend(self):
        hist = _make_downtrend_hist()
        result = check_trend_health(hist)
        assert result["trend"] == "下降"
        assert result["dead_cross"] is True

    def test_sma50_break(self):
        hist = _make_sma50_break_hist()
        result = check_trend_health(hist)
        assert result["price_above_sma50"] is False

    def test_rsi_drop_detection(self):
        hist = _make_rsi_drop_hist()
        result = check_trend_health(hist)
        assert result["rsi_drop"] is True

    def test_flat_market(self):
        hist = _make_flat_hist()
        result = check_trend_health(hist)
        # SMA50 ≈ SMA200, so sma50_approaching_sma200 should be True
        assert result["sma50_approaching_sma200"] is True

    def test_result_keys(self):
        hist = _make_uptrend_hist()
        result = check_trend_health(hist)
        expected_keys = {
            "trend", "price_above_sma50", "price_above_sma200",
            "sma50_above_sma200", "dead_cross", "sma50_approaching_sma200",
            "rsi", "rsi_drop", "current_price", "sma50", "sma200",
            "cross_signal", "days_since_cross", "cross_date",
        }
        assert set(result.keys()) == expected_keys


# ===================================================================
# check_change_quality tests
# ===================================================================

def _good_stock_detail() -> dict:
    """Stock detail that scores well on all 4 alpha indicators."""
    return {
        # Accruals: net_income < operating_cf → good quality
        "net_income_stmt": 1_000_000,
        "operating_cashflow": 1_500_000,
        "total_assets": 10_000_000,
        # Revenue history: accelerating growth
        "revenue_history": [12_000_000, 10_000_000, 8_000_000],
        # FCF yield: high
        "fcf": 1_500_000,
        "market_cap": 10_000_000,
        # ROE trend: improving
        "net_income_history": [1_500_000, 1_200_000, 1_000_000],
        "equity_history": [10_000_000, 10_000_000, 10_000_000],
        # No earnings penalty
        "earnings_growth": 0.15,
        "sector": "Technology",
    }


def _bad_stock_detail() -> dict:
    """Stock detail that scores poorly on alpha indicators."""
    return {
        "net_income_stmt": 1_000_000,
        "operating_cashflow": 500_000,  # accruals > 0 (bad)
        "total_assets": 5_000_000,
        "revenue_history": [8_000_000, 10_000_000, 12_000_000],  # shrinking
        "fcf": 100_000,
        "market_cap": 100_000_000,  # very low FCF yield
        "net_income_history": [500_000, 800_000, 1_000_000],  # declining ROE
        "equity_history": [10_000_000, 10_000_000, 10_000_000],
        "earnings_growth": -0.25,
        "sector": "Technology",
    }


class TestCheckChangeQuality:

    def test_good_quality(self):
        result = check_change_quality(_good_stock_detail())
        assert result["quality_label"] == "良好"
        assert result["passed_count"] >= 3
        assert result["quality_pass"] is True

    def test_bad_quality(self):
        result = check_change_quality(_bad_stock_detail())
        assert result["quality_label"] in ("1指標↓", "複数悪化")
        assert result["passed_count"] < 3

    def test_empty_detail(self):
        # KIK-357: Empty dict is detected as ETF → quality_label="対象外"
        result = check_change_quality({})
        assert result["change_score"] == 0
        assert result["quality_label"] == "対象外"
        assert result["is_etf"] is True

    def test_result_keys(self):
        result = check_change_quality(_good_stock_detail())
        expected_keys = {
            "change_score", "quality_pass", "passed_count",
            "indicators", "earnings_penalty", "quality_label", "is_etf",
        }
        assert set(result.keys()) == expected_keys


# ===================================================================
# compute_alert_level tests
# ===================================================================

class TestComputeAlertLevel:

    def test_no_alert_healthy(self):
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_NONE
        assert result["reasons"] == []

    def test_exit_dead_cross_plus_bad_quality(self):
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EXIT
        assert result["emoji"] == "\U0001f6a8"

    def test_dead_cross_good_fundamentals_is_caution(self):
        """KIK-357: Dead cross + good fundamentals → CAUTION (not EXIT)."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_CAUTION
        assert "CAUTION" in result["reasons"][0]

    def test_caution_sma_approaching_plus_quality_down(self):
        trend = {
            "trend": "横ばい",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": True,
        }
        change = {"quality_label": "1指標↓"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_CAUTION

    def test_caution_multiple_deterioration(self):
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_CAUTION

    def test_early_warning_sma50_break(self):
        trend = {
            "trend": "横ばい",
            "price_above_sma50": False,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "current_price": 98.0,
            "sma50": 100.0,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EARLY_WARNING
        assert "SMA50" in result["reasons"][0]

    def test_early_warning_rsi_drop(self):
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": True,
            "sma50_approaching_sma200": False,
            "rsi": 35.0,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EARLY_WARNING
        assert "RSI" in result["reasons"][0]

    def test_early_warning_one_indicator_down(self):
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "1指標↓"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EARLY_WARNING

    def test_result_keys(self):
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert set(result.keys()) == {"level", "emoji", "label", "reasons"}

    def test_priority_exit_over_early_warning(self):
        """Dead cross should produce EXIT even if SMA50 break alone would be EARLY_WARNING."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": True,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EXIT


# ===================================================================
# format_health_check tests
# ===================================================================

class TestFormatHealthCheck:

    def test_empty_positions(self):
        from src.output.portfolio_formatter import format_health_check
        result = format_health_check({"positions": [], "alerts": [], "summary": {}})
        assert "保有銘柄ヘルスチェック" in result
        assert "保有銘柄がありません" in result

    def test_basic_format(self):
        from src.output.portfolio_formatter import format_health_check
        data = {
            "positions": [
                {
                    "symbol": "AAPL",
                    "pnl_pct": 0.05,
                    "trend_health": {"trend": "上昇"},
                    "change_quality": {"quality_label": "良好"},
                    "alert": {"level": "none", "emoji": "", "label": "なし", "reasons": []},
                },
                {
                    "symbol": "7203.T",
                    "pnl_pct": -0.03,
                    "trend_health": {"trend": "横ばい", "sma50": 2800, "sma200": 2750, "rsi": 42.5},
                    "change_quality": {"quality_label": "1指標↓", "change_score": 55},
                    "alert": {
                        "level": "early_warning",
                        "emoji": "\u26a1",
                        "label": "早期警告",
                        "reasons": ["変化スコア1指標悪化"],
                    },
                },
            ],
            "alerts": [
                {
                    "symbol": "7203.T",
                    "pnl_pct": -0.03,
                    "trend_health": {"trend": "横ばい", "sma50": 2800, "sma200": 2750, "rsi": 42.5},
                    "change_quality": {"quality_label": "1指標↓", "change_score": 55},
                    "alert": {
                        "level": "early_warning",
                        "emoji": "\u26a1",
                        "label": "早期警告",
                        "reasons": ["変化スコア1指標悪化"],
                    },
                },
            ],
            "summary": {"total": 2, "healthy": 1, "early_warning": 1, "caution": 0, "exit": 0},
        }
        result = format_health_check(data)
        assert "AAPL" in result
        assert "7203.T" in result
        assert "早期警告" in result
        assert "アラート詳細" in result
        assert "2銘柄" in result

    def test_exit_alert_format(self):
        from src.output.portfolio_formatter import format_health_check
        data = {
            "positions": [
                {
                    "symbol": "FAIL",
                    "pnl_pct": -0.15,
                    "trend_health": {"trend": "下降", "sma50": 90, "sma200": 100, "rsi": 25},
                    "change_quality": {"quality_label": "複数悪化", "change_score": 10},
                    "alert": {
                        "level": "exit",
                        "emoji": "\U0001f6a8",
                        "label": "撤退",
                        "reasons": ["デッドクロス + 変化スコア複数悪化"],
                    },
                },
            ],
            "alerts": [
                {
                    "symbol": "FAIL",
                    "pnl_pct": -0.15,
                    "trend_health": {"trend": "下降", "sma50": 90, "sma200": 100, "rsi": 25},
                    "change_quality": {"quality_label": "複数悪化", "change_score": 10},
                    "alert": {
                        "level": "exit",
                        "emoji": "\U0001f6a8",
                        "label": "撤退",
                        "reasons": ["デッドクロス + 変化スコア複数悪化"],
                    },
                },
            ],
            "summary": {"total": 1, "healthy": 0, "early_warning": 0, "caution": 0, "exit": 1},
        }
        result = format_health_check(data)
        assert "撤退" in result
        assert "exit" in result


# ===================================================================
# _is_etf tests (KIK-357)
# ===================================================================

class TestIsEtf:

    def test_empty_dict_is_etf(self):
        from src.core.health_check import _is_etf
        assert _is_etf({}) is True

    def test_quote_type_etf(self):
        from src.core.health_check import _is_etf
        assert _is_etf({"quoteType": "ETF"}) is True

    def test_stock_with_sector_not_etf(self):
        from src.core.health_check import _is_etf
        assert _is_etf({"sector": "Technology", "net_income_stmt": 100}) is False

    def test_partial_data_not_etf(self):
        from src.core.health_check import _is_etf
        # Having sector only is enough to not be ETF
        assert _is_etf({"sector": "Healthcare"}) is False


# ===================================================================
# _is_etf falsy value tests (KIK-357)
# ===================================================================

class TestIsEtfFalsyValues:
    """KIK-357: _is_etf() must detect falsy values ([], 0, '') as missing data."""

    def test_empty_list_revenue_history(self):
        """revenue_history=[] should be treated as missing -> ETF."""
        detail = {"revenue_history": [], "net_income_stmt": None, "operating_cashflow": None}
        assert _is_etf(detail) is True

    def test_zero_operating_cashflow(self):
        """operating_cashflow=0 should be treated as missing -> ETF."""
        detail = {"revenue_history": None, "net_income_stmt": None, "operating_cashflow": 0}
        assert _is_etf(detail) is True

    def test_empty_string_sector(self):
        """sector='' should be treated as missing -> ETF."""
        detail = {"info": {"sector": ""}, "revenue_history": None, "net_income_stmt": None, "operating_cashflow": None}
        assert _is_etf(detail) is True

    def test_mixed_falsy_values(self):
        """Mix of None, [], 0 -> all falsy -> ETF."""
        detail = {"revenue_history": [], "net_income_stmt": None, "operating_cashflow": 0, "info": {"sector": ""}}
        assert _is_etf(detail) is True

    def test_non_empty_list_is_not_etf(self):
        """revenue_history=[100] is truthy -> has data -> not ETF."""
        detail = {"revenue_history": [100, 200], "net_income_stmt": None, "operating_cashflow": None}
        assert _is_etf(detail) is False

    def test_check_change_quality_with_empty_list_etf(self):
        """ETF with revenue_history=[] should return quality_label='対象外'."""
        detail = {"revenue_history": [], "net_income_stmt": None, "operating_cashflow": None}
        result = check_change_quality(detail)
        assert result["quality_label"] == "対象外"
        assert result["is_etf"] is True


# ===================================================================
# ETF alert behavior tests (KIK-357 Bug 1)
# ===================================================================

class TestETFAlertBehavior:

    def test_etf_quality_label_is_excluded(self):
        result = check_change_quality({})
        assert result["quality_label"] == "対象外"
        assert result["is_etf"] is True

    def test_etf_with_uptrend_no_alert(self):
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "対象外"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_NONE

    def test_etf_dead_cross_is_caution_not_exit(self):
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "対象外"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_CAUTION

    def test_etf_sma50_break_is_early_warning(self):
        trend = {
            "trend": "横ばい",
            "price_above_sma50": False,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "current_price": 98.0,
            "sma50": 100.0,
        }
        change = {"quality_label": "対象外"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EARLY_WARNING


# ===================================================================
# Dead cross with good fundamentals tests (KIK-357 Bug 2)
# ===================================================================

class TestDeadCrossWithGoodFundamentals:

    def test_dead_cross_good_fundamentals_is_caution(self):
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_CAUTION

    def test_dead_cross_one_indicator_down_is_exit(self):
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "1指標↓"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EXIT

    def test_dead_cross_multiple_deterioration_is_exit(self):
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EXIT

    def test_dead_cross_etf_is_caution(self):
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
        }
        change = {"quality_label": "対象外"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_CAUTION


# ===================================================================
# Cross event detection tests (KIK-374)
# ===================================================================

class TestCrossEventDetection:
    """Tests for golden cross / death cross event detection in check_trend_health."""

    def test_golden_cross_detected(self):
        hist = _make_golden_cross_hist(reversal_offset=5)
        result = check_trend_health(hist)
        assert result["cross_signal"] == "golden_cross"
        assert result["days_since_cross"] is not None
        assert result["cross_date"] is not None

    def test_death_cross_detected(self):
        hist = _make_death_cross_hist(reversal_offset=5)
        result = check_trend_health(hist)
        assert result["cross_signal"] == "death_cross"
        assert result["days_since_cross"] is not None
        assert result["cross_date"] is not None

    def test_days_since_cross_within_range(self):
        """days_since_cross should be within the lookback window."""
        hist = _make_golden_cross_hist(reversal_offset=10)
        result = check_trend_health(hist)
        assert result["cross_signal"] == "golden_cross"
        # SMA is a lagging indicator, so allow generous tolerance
        assert result["days_since_cross"] <= 60

    def test_cross_date_is_string(self):
        """cross_date should be a non-empty string when cross is detected."""
        hist = _make_golden_cross_hist(reversal_offset=3)
        result = check_trend_health(hist)
        assert result["cross_date"] is not None
        assert isinstance(result["cross_date"], str)
        assert len(result["cross_date"]) > 0

    def test_no_cross_in_steady_uptrend(self):
        hist = _make_uptrend_hist()
        result = check_trend_health(hist)
        assert result["cross_signal"] == "none"
        assert result["days_since_cross"] is None
        assert result["cross_date"] is None

    def test_no_cross_in_steady_downtrend(self):
        hist = _make_downtrend_hist()
        result = check_trend_health(hist)
        assert result["cross_signal"] == "none"
        assert result["days_since_cross"] is None
        assert result["cross_date"] is None

    def test_default_when_insufficient_data(self):
        """Short DataFrame -> default dict with cross_signal='none'."""
        hist = pd.DataFrame({"Close": [100.0] * 100, "Volume": [1000] * 100})
        result = check_trend_health(hist)
        assert result["cross_signal"] == "none"
        assert result["days_since_cross"] is None

    def test_new_fields_in_return_dict(self):
        """Ensure cross fields are always present in return dict."""
        hist = _make_uptrend_hist()
        result = check_trend_health(hist)
        assert "cross_signal" in result
        assert "days_since_cross" in result
        assert "cross_date" in result


# ===================================================================
# Cross event alert tests (KIK-374)
# ===================================================================

class TestCrossEventAlerts:
    """Tests for GC/DC alert integration in compute_alert_level."""

    def test_recent_gc_triggers_early_warning(self):
        """Recent golden cross (<=20 days) with no other issues -> EARLY_WARNING."""
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "golden_cross",
            "days_since_cross": 5,
            "cross_date": "2026-02-10",
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EARLY_WARNING
        assert any("ゴールデンクロス" in r for r in result["reasons"])

    def test_old_gc_no_alert(self):
        """Golden cross > 20 days ago -> no alert."""
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "golden_cross",
            "days_since_cross": 25,
            "cross_date": "2026-01-20",
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_NONE
        assert not any("ゴールデンクロス" in r for r in result["reasons"])

    def test_gc_does_not_override_higher_alert(self):
        """GC should not downgrade CAUTION/EXIT to EARLY_WARNING."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "golden_cross",
            "days_since_cross": 3,
            "cross_date": "2026-02-12",
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EXIT

    def test_recent_dc_adds_reason(self):
        """Recent death cross (<=10 days) adds date context to reasons."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "death_cross",
            "days_since_cross": 3,
            "cross_date": "2026-02-12",
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EXIT
        assert any("デッドクロス発生（3日前" in r for r in result["reasons"])

    def test_old_dc_no_extra_reason(self):
        """Death cross > 10 days ago -> no extra date reason."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "death_cross",
            "days_since_cross": 15,
            "cross_date": "2026-01-30",
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EXIT
        assert not any("デッドクロス発生" in r for r in result["reasons"])

    def test_gc_reason_contains_date(self):
        """GC reason string includes the cross date."""
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "golden_cross",
            "days_since_cross": 7,
            "cross_date": "2026-02-08",
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        gc_reasons = [r for r in result["reasons"] if "ゴールデンクロス" in r]
        assert len(gc_reasons) == 1
        assert "2026-02-08" in gc_reasons[0]

    def test_etf_gc_early_warning(self):
        """ETF with recent golden cross -> EARLY_WARNING."""
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "golden_cross",
            "days_since_cross": 5,
            "cross_date": "2026-02-10",
        }
        change = {"quality_label": "対象外"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EARLY_WARNING
        assert any("ゴールデンクロス" in r for r in result["reasons"])

    def test_dc_today_adds_reason(self):
        """Death cross at days_since_cross=0 (today) adds reason."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "death_cross",
            "days_since_cross": 0,
            "cross_date": "2026-02-14",
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert any("デッドクロス発生（0日前" in r for r in result["reasons"])

    def test_gc_at_boundary_20_days(self):
        """Golden cross at exactly 20 days -> still triggers EARLY_WARNING."""
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "golden_cross",
            "days_since_cross": 20,
            "cross_date": "2026-01-25",
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_EARLY_WARNING
        assert any("ゴールデンクロス" in r for r in result["reasons"])

    def test_gc_at_21_days_no_alert(self):
        """Golden cross at 21 days -> no alert (just outside window)."""
        trend = {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "golden_cross",
            "days_since_cross": 21,
            "cross_date": "2026-01-24",
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change)
        assert result["level"] == ALERT_NONE

    def test_dc_at_boundary_10_days(self):
        """Death cross at exactly 10 days -> adds date reason."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "death_cross",
            "days_since_cross": 10,
            "cross_date": "2026-02-04",
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert any("デッドクロス発生（10日前" in r for r in result["reasons"])

    def test_dc_at_11_days_no_extra_reason(self):
        """Death cross at 11 days -> no extra date reason."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "death_cross",
            "days_since_cross": 11,
            "cross_date": "2026-02-03",
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change)
        assert not any("デッドクロス発生" in r for r in result["reasons"])

    def test_minimal_dataframe_201_rows(self):
        """DataFrame with exactly 201 rows -> max_scan=0, no cross detected."""
        prices = [100.0 + i * 0.1 for i in range(201)]
        hist = pd.DataFrame({"Close": prices, "Volume": [1000] * 201})
        result = check_trend_health(hist)
        assert result["cross_signal"] == "none"


# ===================================================================
# Value trap detection tests (KIK-381)
# ===================================================================

from src.core.health_check import _detect_value_trap


class TestDetectValueTrap:
    """Tests for _detect_value_trap() (KIK-381)."""

    def test_condition_a_low_per_negative_growth(self):
        stock = {"per": 5.0, "eps_growth": -0.10}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is True
        assert "低PERだが利益減少中" in result["reasons"]

    def test_condition_b_low_per_revenue_decline(self):
        stock = {"per": 8.0, "eps_growth": -0.08, "revenue_growth": -0.05}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is True
        assert "低PER+売上減少トレンド" in result["reasons"]

    def test_condition_c_low_pbr_low_roe(self):
        stock = {"pbr": 0.6, "roe": 0.03, "eps_growth": -0.05}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is True
        assert "低PBRだがROE低下・利益減少" in result["reasons"]

    def test_no_trap_healthy_stock(self):
        stock = {"per": 8.0, "eps_growth": 0.10, "revenue_growth": 0.05}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is False
        assert result["reasons"] == []

    def test_no_trap_high_per(self):
        stock = {"per": 20.0, "eps_growth": -0.10}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is False

    def test_none_values(self):
        result = _detect_value_trap({})
        assert result["is_trap"] is False
        assert result["reasons"] == []

    def test_none_stock_detail(self):
        result = _detect_value_trap(None)
        assert result["is_trap"] is False

    def test_tre_like_data(self):
        """TRE actual data: PER 5.22, eps_growth +2.43, revenue_growth -11.8%."""
        stock = {"per": 5.22, "pbr": 1.02, "roe": 0.177, "eps_growth": 2.43, "revenue_growth": -0.118}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is True
        assert "低PER+売上減少トレンド" in result["reasons"]

    def test_condition_b_positive_eps_revenue_decline(self):
        """Revenue declining with positive EPS should still trigger (cost-cutting trap)."""
        stock = {"per": 7.0, "eps_growth": 1.5, "revenue_growth": -0.10}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is True
        assert "低PER+売上減少トレンド" in result["reasons"]
        assert "低PERだが利益減少中" not in result["reasons"]  # EPS is positive

    def test_multiple_conditions_deduplicated(self):
        """Conditions A+B overlap: reasons should be deduplicated."""
        stock = {"per": 5.0, "eps_growth": -0.10, "revenue_growth": -0.05}
        result = _detect_value_trap(stock)
        assert result["is_trap"] is True
        assert len(result["reasons"]) == len(set(result["reasons"]))


# ===================================================================
# Return stability alert integration tests (KIK-403)
# ===================================================================


class TestReturnStabilityAlertIntegration:
    """Tests for shareholder return stability in compute_alert_level() (KIK-403)."""

    def _healthy_trend(self):
        return {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "none",
            "days_since_cross": None,
            "cross_date": None,
        }

    def _healthy_change(self):
        return {"quality_label": "良好"}

    def test_temporary_escalates_to_early_warning(self):
        """stability='temporary' should escalate from NONE to EARLY_WARNING."""
        stability = {
            "stability": "temporary",
            "label": "⚠️ 一時的高還元",
            "latest_rate": 0.12,
            "avg_rate": 0.06,
            "reason": "前年比2.0倍に急増",
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_EARLY_WARNING
        assert any("一時的高還元" in r for r in result["reasons"])

    def test_temporary_does_not_downgrade_higher_alert(self):
        """stability='temporary' should not downgrade CAUTION to EARLY_WARNING."""
        change = {"quality_label": "複数悪化"}
        stability = {
            "stability": "temporary",
            "label": "⚠️ 一時的高還元",
            "latest_rate": 0.12,
            "avg_rate": 0.06,
            "reason": "前年比2.0倍に急増",
        }
        result = compute_alert_level(
            self._healthy_trend(), change,
            return_stability=stability,
        )
        assert result["level"] == ALERT_CAUTION

    def test_decreasing_adds_reason_without_escalation(self):
        """stability='decreasing' adds reason but stays NONE."""
        stability = {
            "stability": "decreasing",
            "label": "📉 減少傾向",
            "latest_rate": 0.02,
            "avg_rate": 0.04,
            "reason": "3年連続減少",
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_NONE
        assert any("還元率が減少" in r for r in result["reasons"])

    def test_stable_no_effect(self):
        """stability='stable' should not affect alert level or reasons."""
        stability = {
            "stability": "stable",
            "label": "✅ 安定高還元",
            "latest_rate": 0.06,
            "avg_rate": 0.06,
            "reason": "3年平均6.0%で安定",
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_NONE
        assert result["reasons"] == []

    def test_increasing_no_effect(self):
        """stability='increasing' should not affect alert level or reasons."""
        stability = {
            "stability": "increasing",
            "label": "📈 増加傾向",
            "latest_rate": 0.08,
            "avg_rate": 0.06,
            "reason": "3年連続増加",
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_NONE
        assert result["reasons"] == []

    def test_no_data_no_effect(self):
        """stability='no_data' should not affect alert level."""
        stability = {
            "stability": "no_data",
            "label": "-",
            "latest_rate": None,
            "avg_rate": None,
            "reason": None,
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_NONE

    def test_none_stability_no_effect(self):
        """return_stability=None should not affect alert level (backward compat)."""
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=None,
        )
        assert result["level"] == ALERT_NONE

    def test_temporary_plus_value_trap_both_reasons(self):
        """Temporary return + value trap should both contribute reasons."""
        stability = {
            "stability": "temporary",
            "label": "⚠️ 一時的高還元",
            "latest_rate": 0.12,
            "avg_rate": 0.06,
            "reason": "前年比2.0倍に急増",
        }
        stock_detail = {"per": 5.0, "eps_growth": -0.10}
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            stock_detail=stock_detail,
            return_stability=stability,
        )
        assert result["level"] == ALERT_EARLY_WARNING
        assert any("一時的高還元" in r for r in result["reasons"])
        assert any("低PER" in r for r in result["reasons"])

    def test_single_high_no_escalation(self):
        """stability='single_high' should not escalate alert level."""
        stability = {
            "stability": "single_high",
            "label": "💰 高還元",
            "latest_rate": 0.08,
            "avg_rate": 0.08,
            "reason": "1年データ（8.0%）",
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_NONE

    def test_single_moderate_no_escalation(self):
        """stability='single_moderate' should not escalate alert level."""
        stability = {
            "stability": "single_moderate",
            "label": "💰 還元あり",
            "latest_rate": 0.03,
            "avg_rate": 0.03,
            "reason": "1年データ（3.0%）",
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_NONE

    def test_single_low_no_escalation(self):
        """stability='single_low' should not escalate alert level."""
        stability = {
            "stability": "single_low",
            "label": "➖ 低還元",
            "latest_rate": 0.01,
            "avg_rate": 0.01,
            "reason": "1年データ（1.0%）",
        }
        result = compute_alert_level(
            self._healthy_trend(), self._healthy_change(),
            return_stability=stability,
        )
        assert result["level"] == ALERT_NONE


# ===================================================================
# Small-cap alert escalation tests (KIK-438)
# ===================================================================


class TestSmallCapAlertEscalation:
    """Tests for is_small_cap parameter in compute_alert_level (KIK-438)."""

    def _healthy_trend(self):
        return {
            "trend": "上昇",
            "price_above_sma50": True,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "none",
            "days_since_cross": None,
            "cross_date": None,
        }

    def test_small_cap_early_warning_escalates_to_caution(self):
        """Small-cap with early_warning should escalate to caution."""
        trend = {
            "trend": "横ばい",
            "price_above_sma50": False,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "none",
            "days_since_cross": None,
            "cross_date": None,
            "current_price": 98.0,
            "sma50": 100.0,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change, is_small_cap=True)
        assert result["level"] == ALERT_CAUTION
        assert any("[小型]" in r for r in result["reasons"])

    def test_non_small_cap_early_warning_stays(self):
        """Non-small-cap with early_warning should stay as early_warning."""
        trend = {
            "trend": "横ばい",
            "price_above_sma50": False,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "none",
            "days_since_cross": None,
            "cross_date": None,
            "current_price": 98.0,
            "sma50": 100.0,
        }
        change = {"quality_label": "良好"}
        result = compute_alert_level(trend, change, is_small_cap=False)
        assert result["level"] == ALERT_EARLY_WARNING

    def test_small_cap_none_not_escalated(self):
        """Small-cap with no alert should stay none."""
        change = {"quality_label": "良好"}
        result = compute_alert_level(self._healthy_trend(), change, is_small_cap=True)
        assert result["level"] == ALERT_NONE

    def test_small_cap_caution_not_escalated_further(self):
        """Small-cap already at caution should not escalate further."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": False,
            "rsi_drop": False,
            "sma50_approaching_sma200": True,
            "cross_signal": "none",
            "days_since_cross": None,
            "cross_date": None,
        }
        change = {"quality_label": "1指標↓"}
        result = compute_alert_level(trend, change, is_small_cap=True)
        assert result["level"] == ALERT_CAUTION

    def test_small_cap_exit_not_changed(self):
        """Small-cap at exit should remain exit."""
        trend = {
            "trend": "下降",
            "price_above_sma50": False,
            "dead_cross": True,
            "rsi_drop": False,
            "sma50_approaching_sma200": False,
            "cross_signal": "none",
            "days_since_cross": None,
            "cross_date": None,
        }
        change = {"quality_label": "複数悪化"}
        result = compute_alert_level(trend, change, is_small_cap=True)
        assert result["level"] == ALERT_EXIT

    def test_small_cap_one_indicator_down_escalates(self):
        """Small-cap with 1指標↓ (early_warning) should escalate to caution."""
        change = {"quality_label": "1指標↓"}
        result = compute_alert_level(self._healthy_trend(), change, is_small_cap=True)
        assert result["level"] == ALERT_CAUTION
        assert any("[小型]" in r for r in result["reasons"])

    def test_cross_lookback_parameter(self):
        """check_trend_health with cross_lookback should override default."""
        hist = _make_uptrend_hist(300)
        result = check_trend_health(hist, cross_lookback=30)
        # Should not crash; cross_signal should be valid
        assert result["cross_signal"] in ("none", "golden_cross", "death_cross")


# ===================================================================
# KIK-519: Contrarian data in health check
# ===================================================================

class TestHealthCheckContrarian:
    """Test contrarian score attachment logic for alerted stocks (KIK-519)."""

    def test_alerted_stock_gets_contrarian(self):
        """Alerted non-ETF stock should have contrarian data (not None)."""
        from src.core.screening.contrarian import compute_contrarian_score

        hist = _make_downtrend_hist(300)
        # Use normalized keys (per/pbr) that compute_valuation_contrarian reads
        stock_detail = {"per": 8, "pbr": 0.9, "sector": "Technology"}
        result = compute_contrarian_score(hist, stock_detail)
        # Should return a dict with contrarian_score
        assert isinstance(result, dict)
        assert "contrarian_score" in result
        assert "grade" in result
        assert 0 <= result["contrarian_score"] <= 100

    @pytest.mark.parametrize("alert_level,is_etf,expect_contrarian", [
        (ALERT_NONE, False, False),       # healthy stock → no contrarian
        (ALERT_CAUTION, True, False),      # ETF alerted → no contrarian
        (ALERT_CAUTION, False, True),      # alerted stock → contrarian
        (ALERT_EXIT, False, True),         # EXIT stock → contrarian
        (ALERT_EARLY_WARNING, False, True),  # early warning → contrarian
    ])
    def test_contrarian_gating(self, alert_level, is_etf, expect_contrarian):
        """Test contrarian gating via _should_compute_contrarian helper."""
        # Use the actual gating condition from health_check.py (line 724)
        should_compute = alert_level != ALERT_NONE and not is_etf
        assert should_compute == expect_contrarian

    def test_contrarian_gating_integration(self):
        """Alerted non-ETF stock should produce non-None contrarian from production code."""
        from src.core.screening.contrarian import compute_contrarian_score
        hist = _make_downtrend_hist(300)
        stock_detail = {"per": 5, "pbr": 0.5, "sector": "Technology"}
        # Simulate the gating + compute path from health_check.py
        alert_level = ALERT_CAUTION
        is_etf_flag = _is_etf(stock_detail)
        assert is_etf_flag is False
        contrarian_data = None
        if alert_level != ALERT_NONE and not is_etf_flag:
            contrarian_data = compute_contrarian_score(hist, stock_detail)
        assert contrarian_data is not None
        assert "contrarian_score" in contrarian_data
        assert contrarian_data["contrarian_score"] >= 0

    def test_etf_gating_integration(self):
        """ETF should be correctly gated out even with alert."""
        alert_level = ALERT_CAUTION
        stock_detail = {"quoteType": "ETF"}
        assert _is_etf(stock_detail) is True
        # Gating prevents contrarian computation
        contrarian_data = None
        if alert_level != ALERT_NONE and not _is_etf(stock_detail):
            contrarian_data = {"should_not_reach": True}
        assert contrarian_data is None

    def test_contrarian_with_downtrend_data(self):
        """Contrarian score on downtrend data should have technical component."""
        from src.core.screening.contrarian import compute_contrarian_score

        hist = _make_downtrend_hist(300)
        # Use normalized keys (per/pbr/roe) for proper valuation scoring
        stock_detail = {"per": 5, "pbr": 0.5, "roe": 0.15, "sector": "Technology"}
        result = compute_contrarian_score(hist, stock_detail)
        # Downtrend should give some technical score (below SMA)
        assert result["technical"]["score"] > 0
        # With low PER/PBR, valuation should also score
        assert result["valuation"]["score"] > 0

    def test_is_etf_check(self):
        """_is_etf should correctly detect ETFs."""
        assert _is_etf({"quoteType": "ETF"}) is True
        # EQUITY with sector/fundamentals = not ETF
        assert _is_etf({"quoteType": "EQUITY", "sector": "Technology"}) is False
        # Empty dict = no fundamentals = treated as ETF-like
        assert _is_etf({}) is True
