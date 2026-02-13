"""Tests for format_return_estimate in portfolio_formatter.py (KIK-359)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.output.portfolio_formatter import format_return_estimate


class TestFormatReturnEstimate:
    def test_empty_positions(self):
        """Empty portfolio shows appropriate message."""
        result = format_return_estimate({
            "positions": [],
            "portfolio": {"optimistic": None, "base": None, "pessimistic": None},
            "total_value_jpy": 0,
        })
        assert "推定利回り" in result
        assert "保有銘柄がありません" in result

    def test_full_estimate(self):
        """Full estimate with portfolio summary and per-stock details."""
        estimate = {
            "positions": [
                {
                    "symbol": "AAPL",
                    "name": "Apple",
                    "price": 200.0,
                    "currency": "USD",
                    "optimistic": 0.25,
                    "base": 0.12,
                    "pessimistic": -0.05,
                    "method": "analyst",
                    "analyst_count": 40,
                    "target_high": 250.0,
                    "target_mean": 220.0,
                    "target_low": 190.0,
                    "recommendation_mean": 2.0,
                    "forward_per": 28.0,
                    "dividend_yield": 0.005,
                    "news": [
                        {"title": "Apple AI Growth", "publisher": "Reuters"},
                        {"title": "iPhone Sales Up", "publisher": "Bloomberg"},
                    ],
                    "x_sentiment": {
                        "positive": ["Strong product lineup"],
                        "negative": ["China risk"],
                        "sentiment_score": 0.5,
                    },
                },
            ],
            "portfolio": {
                "optimistic": 0.25,
                "base": 0.12,
                "pessimistic": -0.05,
            },
            "total_value_jpy": 3000000,
            "fx_rates": {"JPY": 1.0, "USD": 150.0},
        }
        result = format_return_estimate(estimate)

        # Portfolio summary table
        assert "推定利回り（12ヶ月）" in result
        assert "楽観" in result
        assert "ベース" in result
        assert "悲観" in result

        # Per-stock section
        assert "AAPL" in result
        assert "期待リターン" in result
        assert "アナリスト目標" in result
        assert "40名" in result
        assert "Forward PER" in result

        # News
        assert "ニュース" in result
        assert "Apple AI Growth" in result

        # X Sentiment
        assert "センチメント" in result
        assert "Strong product lineup" in result
        assert "China risk" in result

        # 3-scenario line
        assert "悲観" in result
        assert "楽観" in result

    def test_etf_historical_method(self):
        """ETF shows historical method label."""
        estimate = {
            "positions": [
                {
                    "symbol": "GLDM",
                    "name": "SPDR Gold MiniShares",
                    "price": 50.0,
                    "currency": "USD",
                    "optimistic": 0.15,
                    "base": 0.08,
                    "pessimistic": -0.02,
                    "method": "historical",
                    "analyst_count": None,
                    "target_high": None,
                    "target_mean": None,
                    "target_low": None,
                    "recommendation_mean": None,
                    "forward_per": None,
                    "data_months": 5,
                    "dividend_yield": 0.0,
                    "news": [],
                    "x_sentiment": None,
                },
            ],
            "portfolio": {
                "optimistic": 0.15,
                "base": 0.08,
                "pessimistic": -0.02,
            },
            "total_value_jpy": 750000,
        }
        result = format_return_estimate(estimate)
        assert "過去リターン分布" in result
        assert "5ヶ月分" in result

    def test_few_analysts_warning(self):
        """Less than 5 analysts shows '参考値' warning."""
        estimate = {
            "positions": [
                {
                    "symbol": "SMALL",
                    "name": "Small Corp",
                    "price": 50.0,
                    "currency": "USD",
                    "optimistic": 0.30,
                    "base": 0.15,
                    "pessimistic": -0.10,
                    "method": "analyst",
                    "analyst_count": 3,
                    "target_high": 65.0,
                    "target_mean": 57.0,
                    "target_low": 45.0,
                    "recommendation_mean": 2.5,
                    "forward_per": 15.0,
                    "dividend_yield": 0.01,
                    "news": [],
                    "x_sentiment": None,
                },
            ],
            "portfolio": {
                "optimistic": 0.30,
                "base": 0.15,
                "pessimistic": -0.10,
            },
            "total_value_jpy": 500000,
        }
        result = format_return_estimate(estimate)
        assert "参考値" in result

    def test_no_x_sentiment(self):
        """When x_sentiment is None, section is omitted."""
        estimate = {
            "positions": [
                {
                    "symbol": "AAPL",
                    "name": "Apple",
                    "price": 200.0,
                    "currency": "USD",
                    "optimistic": 0.20,
                    "base": 0.10,
                    "pessimistic": -0.05,
                    "method": "analyst",
                    "analyst_count": 40,
                    "target_high": 240.0,
                    "target_mean": 220.0,
                    "target_low": 190.0,
                    "recommendation_mean": 2.0,
                    "forward_per": 28.0,
                    "dividend_yield": 0.005,
                    "news": [],
                    "x_sentiment": None,
                },
            ],
            "portfolio": {"optimistic": 0.20, "base": 0.10, "pessimistic": -0.05},
            "total_value_jpy": 3000000,
        }
        result = format_return_estimate(estimate)
        assert "センチメント" not in result

    def test_pnl_amount_calculation(self):
        """PnL amount = return rate * total_value_jpy."""
        estimate = {
            "positions": [
                {
                    "symbol": "TEST",
                    "name": "Test",
                    "price": 100.0,
                    "currency": "JPY",
                    "optimistic": 0.10,
                    "base": 0.05,
                    "pessimistic": -0.03,
                    "method": "analyst",
                    "analyst_count": 10,
                    "target_high": 110.0,
                    "target_mean": 105.0,
                    "target_low": 97.0,
                    "recommendation_mean": 2.0,
                    "forward_per": 12.0,
                    "dividend_yield": 0.02,
                    "news": [],
                    "x_sentiment": None,
                },
            ],
            "portfolio": {"optimistic": 0.10, "base": 0.05, "pessimistic": -0.03},
            "total_value_jpy": 1000000,
        }
        result = format_return_estimate(estimate)
        # Check that the output contains formatted values
        assert "総評価額" in result
