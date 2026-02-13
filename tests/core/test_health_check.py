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
