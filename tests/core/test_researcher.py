"""Tests for src/core/researcher.py (KIK-367).

Tests for research_stock, research_industry, research_market, research_business.
All external calls (yahoo_client, grok_client) are mocked.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.research.researcher import (
    research_stock,
    research_industry,
    research_market,
    research_business,
    _grok_warned,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_warned_flags():
    """Reset the module-level warned flags before each test."""
    _grok_warned[0] = False
    yield


def _make_mock_yahoo_client(info=None, news=None):
    """Build a mock yahoo_client module with get_stock_info / get_stock_news."""
    mock = MagicMock()
    mock.get_stock_info.return_value = info
    mock.get_stock_news.return_value = news or []
    return mock


def _sample_stock_info():
    """Minimal stock info matching the stock_info.json fixture."""
    return {
        "symbol": "7203.T",
        "name": "Toyota Motor Corporation",
        "sector": "Consumer Cyclical",
        "industry": "Auto Manufacturers",
        "price": 2850.0,
        "market_cap": 42_000_000_000_000,
        "per": 10.5,
        "pbr": 1.1,
        "roe": 0.12,
        "dividend_yield": 0.028,
        "revenue_growth": 0.15,
        "eps_growth": 0.10,
        "beta": 0.65,
        "debt_to_equity": 105.0,
    }


def _sample_deep_result():
    """Sample deep research result from grok_client."""
    return {
        "recent_news": ["Strong Q3 earnings"],
        "catalysts": {"positive": ["EV push"], "negative": ["Chip shortage"]},
        "analyst_views": ["Buy rating"],
        "x_sentiment": {"score": 0.5, "summary": "Positive", "key_opinions": []},
        "competitive_notes": ["Market leader"],
        "raw_response": '{"recent_news": ["Strong Q3 earnings"]}',
    }


def _sample_sentiment():
    """Sample X sentiment result from grok_client."""
    return {
        "positive": ["Good earnings"],
        "negative": ["Yen weakness"],
        "sentiment_score": 0.3,
        "raw_response": "...",
    }


# ===================================================================
# research_stock
# ===================================================================

class TestResearchStock:

    def test_basic_research(self, monkeypatch):
        """Returns fundamentals and value score from yfinance data only (Grok off)."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        mock_yc = _make_mock_yahoo_client(
            info=_sample_stock_info(),
            news=[{"title": "Toyota Q3", "publisher": "Reuters"}],
        )

        result = research_stock("7203.T", mock_yc)

        assert result["symbol"] == "7203.T"
        assert result["name"] == "Toyota Motor Corporation"
        assert result["type"] == "stock"
        assert result["fundamentals"]["per"] == 10.5
        assert result["fundamentals"]["sector"] == "Consumer Cyclical"
        assert isinstance(result["value_score"], (int, float))
        assert result["news"] == [{"title": "Toyota Q3", "publisher": "Reuters"}]
        # Grok unavailable => empty results
        assert result["grok_research"]["recent_news"] == []
        assert result["x_sentiment"]["positive"] == []

    def test_with_grok(self, monkeypatch):
        """Integrates yfinance data with Grok API deep research + sentiment."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        # Mock grok_client functions
        from src.data import grok_client
        monkeypatch.setattr(grok_client, "is_available", lambda: True)
        monkeypatch.setattr(
            grok_client, "search_stock_deep",
            lambda symbol, name="", timeout=30: _sample_deep_result(),
        )
        monkeypatch.setattr(
            grok_client, "search_x_sentiment",
            lambda symbol, name="", timeout=30: _sample_sentiment(),
        )

        mock_yc = _make_mock_yahoo_client(info=_sample_stock_info())
        result = research_stock("7203.T", mock_yc)

        assert result["grok_research"]["recent_news"] == ["Strong Q3 earnings"]
        assert result["grok_research"]["catalysts"]["positive"] == ["EV push"]
        assert result["x_sentiment"]["positive"] == ["Good earnings"]
        assert result["x_sentiment"]["sentiment_score"] == 0.3

    def test_stock_not_found(self, monkeypatch):
        """Returns empty fundamentals when yahoo_client returns None."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        mock_yc = _make_mock_yahoo_client(info=None)
        result = research_stock("INVALID", mock_yc)

        assert result["symbol"] == "INVALID"
        assert result["name"] == ""
        assert result["fundamentals"]["price"] is None
        assert result["fundamentals"]["sector"] is None

    def test_grok_error(self, monkeypatch):
        """Graceful degradation when Grok API raises an exception."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        from src.data import grok_client
        monkeypatch.setattr(grok_client, "is_available", lambda: True)
        monkeypatch.setattr(
            grok_client, "search_stock_deep",
            MagicMock(side_effect=RuntimeError("API down")),
        )
        monkeypatch.setattr(
            grok_client, "search_x_sentiment",
            MagicMock(side_effect=RuntimeError("API down")),
        )

        mock_yc = _make_mock_yahoo_client(info=_sample_stock_info())
        result = research_stock("7203.T", mock_yc)

        # Should not raise; returns empty grok results
        assert result["grok_research"]["recent_news"] == []
        assert result["x_sentiment"]["positive"] == []
        # Fundamentals should still work
        assert result["fundamentals"]["per"] == 10.5


# ===================================================================
# research_industry
# ===================================================================

class TestResearchIndustry:

    def test_with_grok(self, monkeypatch):
        """Returns industry data when Grok API is available."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        industry_data = {
            "trends": ["AI chip demand"],
            "key_players": [{"name": "TSMC", "ticker": "TSM", "note": "Leader"}],
            "growth_drivers": ["Data center"],
            "risks": ["Geopolitics"],
            "regulatory": ["Export controls"],
            "investor_focus": ["CAPEX"],
            "raw_response": "...",
        }

        from src.data import grok_client
        monkeypatch.setattr(grok_client, "is_available", lambda: True)
        monkeypatch.setattr(
            grok_client, "search_industry",
            lambda theme, timeout=30: industry_data,
        )

        result = research_industry("半導体")

        assert result["theme"] == "半導体"
        assert result["type"] == "industry"
        assert result["api_unavailable"] is False
        assert result["grok_research"]["trends"] == ["AI chip demand"]
        assert len(result["grok_research"]["key_players"]) == 1

    def test_api_unavailable(self, monkeypatch):
        """Returns api_unavailable=True when Grok is not set."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        result = research_industry("EV")

        assert result["theme"] == "EV"
        assert result["type"] == "industry"
        assert result["api_unavailable"] is True
        assert result["grok_research"]["trends"] == []


# ===================================================================
# research_market
# ===================================================================

class TestResearchMarket:

    def test_with_grok(self, monkeypatch):
        """Returns market data when Grok API is available."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        market_data = {
            "price_action": "Nikkei up 1.5%",
            "macro_factors": ["BOJ decision"],
            "sentiment": {"score": 0.4, "summary": "Optimistic"},
            "upcoming_events": ["GDP Friday"],
            "sector_rotation": ["Defensive to cyclical"],
            "raw_response": "...",
        }

        from src.data import grok_client
        monkeypatch.setattr(grok_client, "is_available", lambda: True)
        monkeypatch.setattr(
            grok_client, "search_market",
            lambda market, timeout=30: market_data,
        )

        result = research_market("日経平均")

        assert result["market"] == "日経平均"
        assert result["type"] == "market"
        assert result["api_unavailable"] is False
        assert result["grok_research"]["price_action"] == "Nikkei up 1.5%"
        assert result["grok_research"]["sentiment"]["score"] == 0.4
        assert "macro_indicators" in result

    def test_api_unavailable(self, monkeypatch):
        """Returns api_unavailable=True when Grok is not set."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        result = research_market("S&P500")

        assert result["market"] == "S&P500"
        assert result["type"] == "market"
        assert result["api_unavailable"] is True
        assert result["grok_research"]["price_action"] == ""
        assert result["grok_research"]["macro_factors"] == []
        assert "macro_indicators" in result

    def test_with_macro_indicators(self, monkeypatch):
        """yahoo_client_module with get_macro_indicators → macro_indicators populated."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        mock_yc = MagicMock()
        mock_yc.get_macro_indicators.return_value = [
            {"name": "S&P500", "symbol": "^GSPC", "price": 5000.0,
             "daily_change": 0.01, "weekly_change": 0.03, "is_point_diff": False},
            {"name": "VIX", "symbol": "^VIX", "price": 18.5,
             "daily_change": -0.5, "weekly_change": -1.2, "is_point_diff": True},
        ]

        result = research_market("日経平均", mock_yc)

        assert len(result["macro_indicators"]) == 2
        assert result["macro_indicators"][0]["name"] == "S&P500"
        assert result["macro_indicators"][1]["price"] == 18.5
        mock_yc.get_macro_indicators.assert_called_once()

    def test_without_yahoo_client(self, monkeypatch):
        """yahoo_client_module=None → macro_indicators is empty."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        result = research_market("S&P500")

        assert result["macro_indicators"] == []

    def test_grok_unavailable_still_has_macro(self, monkeypatch):
        """Grok API unavailable but macro_indicators still returned."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        mock_yc = MagicMock()
        mock_yc.get_macro_indicators.return_value = [
            {"name": "VIX", "symbol": "^VIX", "price": 25.0,
             "daily_change": 2.0, "weekly_change": 5.0, "is_point_diff": True},
        ]

        result = research_market("日経平均", mock_yc)

        assert result["api_unavailable"] is True
        assert len(result["macro_indicators"]) == 1
        assert result["macro_indicators"][0]["name"] == "VIX"


# ===================================================================
# research_business
# ===================================================================

class TestResearchBusiness:

    def test_with_grok(self, monkeypatch):
        """Returns business model data when Grok API is available."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        business_data = {
            "overview": "Canon is a diversified imaging company",
            "segments": [{"name": "Printing", "revenue_share": "55%", "description": "Printers"}],
            "revenue_model": "Hardware + consumables",
            "competitive_advantages": ["Patent portfolio"],
            "key_metrics": ["Attach rate"],
            "growth_strategy": ["Medical expansion"],
            "risks": ["Print market decline"],
            "raw_response": "...",
        }

        from src.data import grok_client
        monkeypatch.setattr(grok_client, "is_available", lambda: True)
        monkeypatch.setattr(
            grok_client, "search_business",
            lambda symbol, name="", timeout=30: business_data,
        )

        mock_yc = _make_mock_yahoo_client(info={"name": "Canon Inc."})
        result = research_business("7751.T", mock_yc)

        assert result["symbol"] == "7751.T"
        assert result["name"] == "Canon Inc."
        assert result["type"] == "business"
        assert result["api_unavailable"] is False
        assert result["grok_research"]["overview"] == "Canon is a diversified imaging company"
        assert len(result["grok_research"]["segments"]) == 1

    def test_api_unavailable(self, monkeypatch):
        """Returns api_unavailable=True when Grok is not set."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        mock_yc = _make_mock_yahoo_client(info={"name": "Canon Inc."})
        result = research_business("7751.T", mock_yc)

        assert result["symbol"] == "7751.T"
        assert result["name"] == "Canon Inc."
        assert result["type"] == "business"
        assert result["api_unavailable"] is True
        assert result["grok_research"]["overview"] == ""
        assert result["grok_research"]["segments"] == []

    def test_grok_error(self, monkeypatch):
        """Graceful degradation when Grok API raises an exception."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

        from src.data import grok_client
        monkeypatch.setattr(grok_client, "is_available", lambda: True)
        monkeypatch.setattr(
            grok_client, "search_business",
            MagicMock(side_effect=RuntimeError("API down")),
        )

        mock_yc = _make_mock_yahoo_client(info={"name": "Canon Inc."})
        result = research_business("7751.T", mock_yc)

        assert result["api_unavailable"] is False
        assert result["grok_research"]["overview"] == ""

    def test_stock_not_found(self, monkeypatch):
        """Returns empty name when yahoo_client returns None."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        mock_yc = _make_mock_yahoo_client(info=None)
        result = research_business("INVALID", mock_yc)

        assert result["symbol"] == "INVALID"
        assert result["name"] == ""
        assert result["api_unavailable"] is True
