"""Tests for _build_research_summary() in history_store.py (KIK-416)."""

import pytest
from unittest.mock import patch, MagicMock

from src.data.history_store import _build_research_summary


# ===================================================================
# stock type
# ===================================================================

class TestBuildResearchSummaryStock:

    def test_stock_with_all_fields(self):
        result = {
            "name": "CANON INC",
            "grok_research": {
                "recent_news": [
                    "Canon reports record Q4 earnings.<grok:render>citation</grok:render>",
                ],
                "x_sentiment": {"score": 0.7, "summary": "positive"},
            },
            "value_score": 65,
        }
        summary = _build_research_summary("stock", result)
        assert "CANON INC" in summary
        assert "Canon reports record Q4 earnings" in summary
        assert "Xセンチメント0.7" in summary
        assert "スコア65" in summary
        # grok citation tags should be stripped
        assert "<grok" not in summary

    def test_stock_news_from_result_news_field(self):
        """When grok_research has no recent_news, fall back to result['news']."""
        result = {
            "name": "TEST",
            "grok_research": {},
            "news": [{"title": "Breaking news headline"}],
            "x_sentiment": {"score": 0.5},
        }
        summary = _build_research_summary("stock", result)
        assert "TEST" in summary

    def test_stock_minimal_data(self):
        result = {
            "name": "TEST CORP",
            "grok_research": {},
        }
        summary = _build_research_summary("stock", result)
        assert "TEST CORP" in summary

    def test_stock_x_sentiment_from_result(self):
        """x_sentiment in result (not in grok_research) should be picked up."""
        result = {
            "name": "ABC",
            "grok_research": {},
            "x_sentiment": {"score": 0.9},
        }
        summary = _build_research_summary("stock", result)
        assert "Xセンチメント0.9" in summary


# ===================================================================
# market type
# ===================================================================

class TestBuildResearchSummaryMarket:

    def test_market_with_price_action_and_sentiment(self):
        result = {
            "grok_research": {
                "price_action": "Gold at $4,896, down 2.5% amid profit-taking.<grok:citation>1</grok:citation>",
                "sentiment": {"score": 0.6, "summary": "bullish"},
            },
        }
        summary = _build_research_summary("market", result)
        assert "Gold at $4,896" in summary
        assert "センチメント0.6" in summary
        assert "<grok" not in summary

    def test_market_no_sentiment(self):
        result = {
            "grok_research": {
                "price_action": "S&P 500 hits all-time high at 6,800.",
            },
        }
        summary = _build_research_summary("market", result)
        assert "S&P 500 hits all-time high" in summary


# ===================================================================
# industry type
# ===================================================================

class TestBuildResearchSummaryIndustry:

    def test_industry_with_trends(self):
        result = {
            "grok_research": {
                "trends": "Semiconductor demand surging driven by AI chip orders.<grok:tag>x</grok:tag>",
            },
        }
        summary = _build_research_summary("industry", result)
        assert "Semiconductor demand surging" in summary
        assert "<grok" not in summary

    def test_industry_empty_trends(self):
        result = {
            "grok_research": {"trends": ""},
        }
        summary = _build_research_summary("industry", result)
        assert summary == ""


# ===================================================================
# business type
# ===================================================================

class TestBuildResearchSummaryBusiness:

    def test_business_with_name_and_overview(self):
        result = {
            "name": "TOYOTA MOTOR",
            "grok_research": {
                "overview": "Toyota earns from auto manufacturing and financial services.<grok:r>1</grok:r>",
            },
        }
        summary = _build_research_summary("business", result)
        assert "TOYOTA MOTOR" in summary
        assert "Toyota earns from auto manufacturing" in summary
        assert "<grok" not in summary

    def test_business_no_overview(self):
        result = {
            "name": "TEST",
            "grok_research": {},
        }
        summary = _build_research_summary("business", result)
        assert "TEST" in summary


# ===================================================================
# Edge cases
# ===================================================================

class TestBuildResearchSummaryEdgeCases:

    def test_none_grok_research(self):
        result = {"grok_research": None}
        assert _build_research_summary("stock", result) == ""

    def test_missing_grok_research(self):
        result = {}
        assert _build_research_summary("stock", result) == ""

    def test_empty_grok_research(self):
        result = {"grok_research": {}}
        assert _build_research_summary("stock", result) == ""

    def test_grok_research_not_dict(self):
        result = {"grok_research": "invalid"}
        assert _build_research_summary("stock", result) == ""

    def test_truncation_at_200_chars(self):
        result = {
            "name": "COMPANY",
            "grok_research": {
                "recent_news": ["A" * 300],
                "x_sentiment": {"score": 0.5},
            },
            "value_score": 99,
        }
        summary = _build_research_summary("stock", result)
        assert len(summary) <= 200

    def test_unknown_research_type(self):
        result = {"grok_research": {"data": "test"}}
        summary = _build_research_summary("unknown_type", result)
        assert summary == ""


# ===================================================================
# Integration: save_research passes summary to Neo4j
# ===================================================================

class TestSaveResearchSummaryIntegration:

    @patch("src.data.history_store.Path.mkdir")
    @patch("builtins.open", new_callable=MagicMock)
    def test_save_research_generates_summary(self, mock_open, mock_mkdir):
        """save_research should pass auto-generated summary to merge_research_full."""
        with patch("src.data.graph_store.merge_research_full") as mock_merge, \
             patch("src.data.graph_store.merge_stock"), \
             patch("src.data.graph_store.link_research_supersedes"):

            from src.data.history_store import save_research

            result = {
                "name": "TEST CORP",
                "type": "stock",
                "grok_research": {
                    "recent_news": ["Big news headline"],
                    "x_sentiment": {"score": 0.8},
                },
                "value_score": 75,
            }

            save_research("stock", "TEST.T", result, base_dir="/tmp/test_history")

            # Verify merge_research_full was called with non-empty summary
            mock_merge.assert_called_once()
            call_kwargs = mock_merge.call_args
            summary_arg = call_kwargs.kwargs.get("summary") or call_kwargs[1].get("summary", "")
            # Check via positional or keyword
            if not summary_arg and call_kwargs.args:
                # summary is the 4th positional arg
                summary_arg = call_kwargs.args[3] if len(call_kwargs.args) > 3 else ""
            assert summary_arg != "", "summary should not be empty"
            assert "TEST CORP" in summary_arg
