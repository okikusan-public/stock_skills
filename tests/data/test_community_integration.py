"""Tests for KIK-549 community skill integration.

Covers: screening context, auto_context, health check concentration,
and incremental community update.
"""

import pytest
from unittest.mock import MagicMock, patch


# ===================================================================
# 1. Screening context community grouping
# ===================================================================


class TestScreeningContextCommunity:
    """Test that screening context includes community data."""

    def test_communities_added_to_context(self):
        from src.data.context.screening_context import get_screening_graph_context

        mock_comm = {
            "name": "Tech x AI",
            "peers": ["B", "C"],
            "size": 3,
            "level": 0,
            "community_id": "community_0_0",
        }

        with patch("src.data.graph_query.community.get_stock_community", return_value=mock_comm), \
             patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]), \
             patch("src.data.graph_query.get_sector_catalysts", return_value={}), \
             patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}), \
             patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}):
            ctx = get_screening_graph_context(["A", "B"], ["Tech"])

        assert "symbol_communities" in ctx
        assert "A" in ctx["symbol_communities"]
        assert ctx["symbol_communities"]["A"]["name"] == "Tech x AI"
        assert ctx["has_data"] is True

    def test_communities_empty_when_no_graph(self):
        from src.data.context.screening_context import get_screening_graph_context

        with patch("src.data.graph_query.community.get_stock_community", return_value=None), \
             patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]), \
             patch("src.data.graph_query.get_sector_catalysts", return_value={}), \
             patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}), \
             patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}):
            ctx = get_screening_graph_context(["A"], ["Tech"])

        assert ctx.get("symbol_communities") is None or ctx.get("symbol_communities") == {}

    def test_communities_graceful_on_error(self):
        from src.data.context.screening_context import get_screening_graph_context

        with patch("src.data.graph_query.get_industry_research_for_sector", return_value=[]), \
             patch("src.data.graph_query.get_sector_catalysts", return_value={}), \
             patch("src.data.graph_query.get_notes_for_symbols_batch", return_value={}), \
             patch("src.data.graph_query.get_themes_for_symbols_batch", return_value={}), \
             patch("src.data.graph_query.community.get_stock_community", side_effect=Exception("fail")):
            ctx = get_screening_graph_context(["A"], ["Tech"])

        assert isinstance(ctx, dict)


# ===================================================================
# 2. Screening summary formatter community section
# ===================================================================


class TestScreeningSummaryFormatterCommunity:
    def test_community_section_rendered(self):
        from src.output.screening_summary_formatter import format_screening_summary

        context = {
            "has_data": True,
            "sector_research": {},
            "symbol_notes": {},
            "symbol_themes": {},
            "symbol_communities": {
                "A": {"name": "Tech x AI", "peers": ["B"]},
                "B": {"name": "Tech x AI", "peers": ["A"]},
                "C": {"name": "Healthcare", "peers": []},
            },
        }
        output = format_screening_summary(context)
        assert "コミュニティ" in output
        assert "Tech x AI" in output
        assert "2銘柄" in output
        assert "Healthcare" in output

    def test_no_community_section_when_empty(self):
        from src.output.screening_summary_formatter import format_screening_summary

        context = {
            "has_data": True,
            "sector_research": {"Tech": {"summaries": ["x"], "catalysts_pos": [], "catalysts_neg": []}},
            "symbol_notes": {},
            "symbol_themes": {},
        }
        output = format_screening_summary(context)
        assert "コミュニティ" not in output


# ===================================================================
# 3. Health check community concentration
# ===================================================================


class TestHealthCheckCommunityConcentration:
    def test_compute_community_concentration(self):
        from src.core.health_check import _compute_community_concentration

        results = [
            {"symbol": "A"},
            {"symbol": "B"},
            {"symbol": "C"},
        ]
        eval_by_symbol = {"A": 5000, "B": 3000, "C": 2000}
        total_value = 10000

        mock_comms = {
            "A": {"name": "Tech", "peers": ["B"], "size": 2, "level": 0, "community_id": "c0"},
            "B": {"name": "Tech", "peers": ["A"], "size": 2, "level": 0, "community_id": "c0"},
            "C": {"name": "Health", "peers": [], "size": 1, "level": 0, "community_id": "c1"},
        }

        with patch("src.data.graph_query.community.get_stock_community", side_effect=lambda s: mock_comms.get(s)):
            result = _compute_community_concentration(results, eval_by_symbol, total_value)

        assert result is not None
        assert result["hhi"] > 0
        assert result["community_weights"]["Tech"] == 0.8
        # Tech has 2 members and >50% → warning
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["community"] == "Tech"

    def test_returns_none_when_no_communities(self):
        from src.core.health_check import _compute_community_concentration

        with patch("src.data.graph_query.community.get_stock_community", return_value=None):
            result = _compute_community_concentration(
                [{"symbol": "A"}], {"A": 1000}, 1000
            )
        assert result is None

    def test_no_warning_when_diversified(self):
        from src.core.health_check import _compute_community_concentration

        results = [{"symbol": f"S{i}"} for i in range(5)]
        eval_by_symbol = {f"S{i}": 2000 for i in range(5)}
        total_value = 10000

        comms = {
            f"S{i}": {"name": f"C{i}", "peers": [], "size": 1, "level": 0, "community_id": f"c{i}"}
            for i in range(5)
        }

        with patch("src.data.graph_query.community.get_stock_community", side_effect=lambda s: comms.get(s)):
            result = _compute_community_concentration(results, eval_by_symbol, total_value)

        assert result is not None
        assert len(result["warnings"]) == 0

    def test_moderate_warning_at_30_percent(self):
        from src.core.health_check import _compute_community_concentration

        results = [{"symbol": "A"}, {"symbol": "B"}, {"symbol": "C"}]
        eval_by_symbol = {"A": 2000, "B": 2000, "C": 6000}

        comms = {
            "A": {"name": "Tech", "peers": ["B"], "size": 2},
            "B": {"name": "Tech", "peers": ["A"], "size": 2},
            "C": {"name": "Health", "peers": [], "size": 1},
        }

        with patch("src.data.graph_query.community.get_stock_community", side_effect=lambda s: comms.get(s)):
            result = _compute_community_concentration(results, eval_by_symbol, 10000)

        # Tech = 40% (>30%), 2 members → moderate warning
        assert len(result["warnings"]) == 1
        assert "やや高め" in result["warnings"][0]["message"]


# ===================================================================
# 4. Health formatter community section
# ===================================================================


class TestHealthFormatterCommunity:
    def test_community_warning_displayed(self):
        from src.output.health_formatter import format_health_check

        pos_a = {"symbol": "A", "name": "StockA", "pnl_pct": 5, "trend_health": {"trend": "up", "rsi": 55},
                 "change_quality": {"quality": "good", "score": 70, "quality_label": "良好"},
                 "alert": {"level": "none", "emoji": "", "label": "なし", "reasons": []},
                 "long_term": {"label": "適格", "emoji": "✅"}, "value_trap": {}, "shareholder_return": {},
                 "return_stability": {}, "contrarian": None, "is_small_cap": False, "size_class": "大型"}
        health_data = {
            "positions": [pos_a],
            "stock_positions": [pos_a],
            "etf_positions": [],
            "alerts": [],
            "summary": {"total": 1, "healthy": 1, "early_warning": 0, "caution": 0, "exit": 0},
            "small_cap_allocation": None,
            "community_concentration": {
                "hhi": 0.68,
                "community_weights": {"Tech x AI": 0.8, "Health": 0.2},
                "community_members": {"Tech x AI": ["A", "B"], "Health": ["C"]},
                "warnings": [{
                    "community": "Tech x AI",
                    "weight": 0.8,
                    "count": 2,
                    "members": ["A", "B"],
                    "message": "実質的に分散できていない可能性",
                }],
            },
        }
        output = format_health_check(health_data)
        assert "コミュニティ集中" in output
        assert "Tech x AI" in output
        assert "80%" in output

    def test_no_community_section_when_none(self):
        from src.output.health_formatter import format_health_check

        health_data = {
            "positions": [],
            "stock_positions": [],
            "etf_positions": [],
            "alerts": [],
            "summary": {"total": 0, "healthy": 0, "early_warning": 0, "caution": 0, "exit": 0},
            "small_cap_allocation": None,
            "community_concentration": None,
        }
        output = format_health_check(health_data)
        assert "コミュニティ集中" not in output


# ===================================================================
# 5. Auto-context community info
# ===================================================================


class TestAutoContextCommunity:
    def test_community_in_context_output(self):
        from src.data.context.auto_context import _format_context

        history = {
            "screens": [],
            "reports": [],
            "trades": [],
            "health_checks": [],
            "notes": [],
            "themes": ["AI"],
            "researches": [],
        }

        mock_comm = {
            "name": "Tech x AI",
            "peers": ["B", "C"],
            "size": 5,
        }

        with patch("src.data.graph_query.community.get_stock_community", return_value=mock_comm):
            output = _format_context("A", history, "stock-report", "分析", "未知")

        assert "コミュニティ: Tech x AI" in output
        assert "同一クラスタ: B, C" in output

    def test_no_community_when_none(self):
        from src.data.context.auto_context import _format_context

        history = {
            "screens": [],
            "reports": [],
            "trades": [],
            "health_checks": [],
            "notes": [],
            "themes": [],
            "researches": [],
        }

        with patch("src.data.graph_query.community.get_stock_community", return_value=None):
            output = _format_context("A", history, "stock-report", "分析", "未知")

        assert "コミュニティ" not in output


# ===================================================================
# 6. Incremental community update
# ===================================================================


class TestUpdateStockCommunity:
    def test_returns_none_no_driver(self):
        from src.data.graph_query.community import update_stock_community

        with patch("src.data.graph_store._get_driver", return_value=None):
            assert update_stock_community("X") is None
