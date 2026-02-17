"""Tests for src.data.graph_nl_query module (KIK-409).

All graph_query functions are mocked — no Neo4j dependency.
"""

from unittest.mock import patch

import pytest

from src.data.graph_nl_query import (
    query,
    format_result,
    _extract_symbol,
    _extract_symbol_and_type,
)


# ===================================================================
# Symbol extraction tests
# ===================================================================

class TestExtractSymbol:
    def test_jp_ticker(self):
        assert _extract_symbol("7203.Tの前回レポート") == "7203.T"

    def test_us_ticker(self):
        assert _extract_symbol("AAPLの取引履歴") == "AAPL"

    def test_sg_ticker(self):
        assert _extract_symbol("D05.SIの情報") == "D05.SI"

    def test_no_symbol(self):
        assert _extract_symbol("繰り返し候補") is None

    def test_symbol_and_type_stock(self):
        result = _extract_symbol_and_type("7203.Tのリサーチ履歴")
        assert result == {"symbol": "7203.T", "research_type": "stock"}

    def test_symbol_and_type_industry(self):
        result = _extract_symbol_and_type("半導体業界のリサーチ")
        assert result["research_type"] == "industry"

    def test_symbol_and_type_market(self):
        result = _extract_symbol_and_type("市場のリサーチ")
        assert result["research_type"] == "market"


# ===================================================================
# Template matching + dispatch tests
# ===================================================================

class TestQuery:
    @patch("src.data.graph_nl_query.graph_query")
    def test_prior_report_match(self, mock_gq):
        mock_gq.get_prior_report.return_value = {
            "date": "2026-02-17", "score": 75, "verdict": "割安",
        }
        result = query("7203.Tの前回レポートは？")
        assert result is not None
        assert result["query_type"] == "prior_report"
        assert "割安" in result["formatted"]
        mock_gq.get_prior_report.assert_called_once_with("7203.T")

    @patch("src.data.graph_nl_query.graph_query")
    def test_prior_report_not_found(self, mock_gq):
        mock_gq.get_prior_report.return_value = None
        result = query("7203.Tの以前のレポート")
        assert result is None

    @patch("src.data.graph_nl_query.graph_query")
    def test_recurring_picks_match(self, mock_gq):
        mock_gq.get_recurring_picks.return_value = [
            {"symbol": "7203.T", "count": 5, "last_date": "2026-02-15"},
            {"symbol": "AAPL", "count": 3, "last_date": "2026-02-10"},
        ]
        result = query("繰り返し候補に上がってる銘柄は？")
        assert result is not None
        assert result["query_type"] == "recurring_picks"
        assert "7203.T" in result["formatted"]
        assert "5" in result["formatted"]

    @patch("src.data.graph_nl_query.graph_query")
    def test_recurring_picks_yoku_deru(self, mock_gq):
        """「よく出る」パターンもマッチすること."""
        mock_gq.get_recurring_picks.return_value = [
            {"symbol": "AAPL", "count": 2, "last_date": "2026-02-01"},
        ]
        result = query("よく出てくるけど買ってない銘柄")
        assert result is not None
        assert result["query_type"] == "recurring_picks"

    @patch("src.data.graph_nl_query.graph_query")
    def test_research_chain_match(self, mock_gq):
        mock_gq.get_research_chain.return_value = [
            {"date": "2026-02-17", "summary": "EV market growing"},
        ]
        result = query("7203.Tのリサーチ履歴")
        assert result is not None
        assert result["query_type"] == "research_chain"
        assert "EV market growing" in result["formatted"]

    @patch("src.data.graph_nl_query.graph_query")
    def test_market_context_match(self, mock_gq):
        mock_gq.get_recent_market_context.return_value = {
            "date": "2026-02-17",
            "indices": [{"name": "Nikkei 225", "value": "39500"}],
        }
        result = query("最近の市況は？")
        assert result is not None
        assert result["query_type"] == "market_context"
        assert "Nikkei 225" in result["formatted"]

    @patch("src.data.graph_nl_query.graph_query")
    def test_trade_context_match(self, mock_gq):
        mock_gq.get_trade_context.return_value = {
            "trades": [{"date": "2026-01-15", "type": "buy", "shares": 100, "price": 2850}],
            "notes": [{"date": "2026-01-15", "type": "thesis", "content": "EV growth"}],
        }
        result = query("7203.Tの取引履歴")
        assert result is not None
        assert result["query_type"] == "trade_context"
        assert "2850" in result["formatted"]
        assert "EV growth" in result["formatted"]

    @patch("src.data.graph_nl_query.graph_query")
    def test_notes_match(self, mock_gq):
        mock_gq.get_trade_context.return_value = {
            "trades": [],
            "notes": [{"date": "2026-02-17", "type": "thesis", "content": "Strong fundamentals"}],
        }
        result = query("7203.Tの投資メモ")
        assert result is not None
        assert result["query_type"] == "notes"

    def test_no_match(self):
        result = query("今日の天気は？")
        assert result is None

    @patch("src.data.graph_nl_query.graph_query")
    def test_no_symbol_for_report(self, mock_gq):
        """銘柄なしのレポート照会は None を返すこと."""
        result = query("前回レポート")
        assert result is None


# ===================================================================
# Formatter tests
# ===================================================================

class TestFormatResult:
    def test_fmt_prior_report_empty(self):
        result = format_result("prior_report", None, {"symbol": "7203.T"})
        assert "見つかりませんでした" in result

    def test_fmt_recurring_picks_empty(self):
        result = format_result("recurring_picks", [], {})
        assert "ありません" in result

    def test_fmt_research_chain_empty(self):
        result = format_result("research_chain", [], {"symbol": "AAPL", "research_type": "stock"})
        assert "見つかりませんでした" in result

    def test_fmt_market_context_empty(self):
        result = format_result("market_context", None, {})
        assert "見つかりませんでした" in result

    def test_fmt_trade_context_empty(self):
        result = format_result("trade_context", {"trades": [], "notes": []}, {"symbol": "7203.T"})
        assert "見つかりませんでした" in result
