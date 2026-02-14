"""Tests for format_trending_markdown (KIK-370)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.output.formatter import format_trending_markdown


class TestFormatTrendingMarkdown:
    def test_empty_results(self):
        output = format_trending_markdown([])
        assert "見つかりませんでした" in output

    def test_basic_output(self):
        results = [{
            "symbol": "7203.T",
            "name": "Toyota",
            "trending_reason": "EV push",
            "price": 2850.0,
            "per": 10.5,
            "pbr": 0.95,
            "dividend_yield": 0.035,
            "roe": 0.12,
            "value_score": 65.0,
            "classification": "話題×割安",
        }]
        output = format_trending_markdown(results)
        assert "7203.T" in output
        assert "Toyota" in output
        assert "EV push" in output
        assert "割安" in output
        assert "🟢" in output

    def test_market_context_header(self):
        results = [{
            "symbol": "TEST",
            "trending_reason": "x",
            "classification": "話題×割高",
        }]
        output = format_trending_markdown(results, market_context="Bullish mood")
        assert "Bullish mood" in output
        assert "X市場センチメント" in output

    def test_no_market_context(self):
        results = [{
            "symbol": "TEST",
            "trending_reason": "x",
            "classification": "話題×割高",
        }]
        output = format_trending_markdown(results, market_context="")
        assert "X市場センチメント" not in output

    def test_long_reason_truncated(self):
        results = [{
            "symbol": "TEST",
            "trending_reason": "A" * 50,
            "classification": "話題×割高",
        }]
        output = format_trending_markdown(results)
        assert "..." in output

    def test_short_reason_not_truncated(self):
        results = [{
            "symbol": "TEST",
            "trending_reason": "Short reason",
            "classification": "話題×割高",
        }]
        output = format_trending_markdown(results)
        assert "Short reason" in output
        assert "..." not in output

    def test_none_values_handled(self):
        results = [{
            "symbol": "TEST",
            "trending_reason": "test",
            "price": None,
            "per": None,
            "pbr": None,
            "dividend_yield": None,
            "roe": None,
            "value_score": 0.0,
            "classification": "話題×割高",
        }]
        output = format_trending_markdown(results)
        assert "TEST" in output
        assert "🔴" in output

    def test_all_classifications(self):
        results = [
            {"symbol": "A", "trending_reason": "a", "classification": "話題×割安", "value_score": 70.0},
            {"symbol": "B", "trending_reason": "b", "classification": "話題×適正", "value_score": 40.0},
            {"symbol": "C", "trending_reason": "c", "classification": "話題×割高", "value_score": 10.0},
        ]
        output = format_trending_markdown(results)
        assert "🟢割安" in output
        assert "🟡適正" in output
        assert "🔴割高" in output

    def test_legend_present(self):
        results = [{
            "symbol": "TEST",
            "trending_reason": "test",
            "classification": "話題×割高",
        }]
        output = format_trending_markdown(results)
        assert "判定基準" in output
        assert "データソース" in output

    def test_multiple_results_ranking(self):
        results = [
            {"symbol": "A", "trending_reason": "a", "classification": "話題×割安"},
            {"symbol": "B", "trending_reason": "b", "classification": "話題×適正"},
        ]
        output = format_trending_markdown(results)
        assert "| 1 |" in output
        assert "| 2 |" in output
