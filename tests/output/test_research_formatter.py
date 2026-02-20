"""Tests for src/output/research_formatter.py (KIK-367).

Tests for format_stock_research, format_industry_research,
format_market_research, format_business_research, and helpers.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.output.research_formatter import (
    format_stock_research,
    format_industry_research,
    format_market_research,
    format_business_research,
    _sentiment_label,
    _vix_label,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_stock_data():
    """Complete stock research data for formatter tests."""
    return {
        "symbol": "7203.T",
        "name": "Toyota Motor Corporation",
        "type": "stock",
        "fundamentals": {
            "price": 2850.0,
            "market_cap": 42_000_000_000_000,
            "sector": "Consumer Cyclical",
            "industry": "Auto Manufacturers",
            "per": 10.5,
            "pbr": 1.1,
            "roe": 0.12,
            "dividend_yield": 0.028,
            "revenue_growth": 0.15,
            "eps_growth": 0.10,
            "beta": 0.65,
            "debt_to_equity": 105.0,
        },
        "value_score": 72.5,
        "grok_research": {
            "recent_news": ["Strong Q3 earnings", "New EV model launch"],
            "catalysts": {
                "positive": ["EV expansion", "Cost reduction"],
                "negative": ["Chip shortage", "Yen volatility"],
            },
            "analyst_views": ["Goldman: Buy", "Morgan Stanley: Overweight"],
            "x_sentiment": {
                "score": 0.5,
                "summary": "Bullish consensus",
                "key_opinions": ["Strong buy signals"],
            },
            "competitive_notes": ["Market leader in hybrid"],
            "raw_response": "...",
        },
        "x_sentiment": {
            "positive": ["Strong earnings beat", "AI investment"],
            "negative": ["China market risk"],
            "sentiment_score": 0.6,
            "raw_response": "...",
        },
        "news": [
            {"title": "Toyota Q3 Earnings Beat", "publisher": "Reuters", "date": "2025-02-01"},
            {"title": "New EV Model Announced", "publisher": "Bloomberg"},
        ],
    }


def _full_industry_data():
    """Complete industry research data."""
    return {
        "theme": "半導体",
        "type": "industry",
        "grok_research": {
            "trends": ["AI chip demand surging", "Advanced packaging growth"],
            "key_players": [
                {"name": "TSMC", "ticker": "TSM", "note": "Foundry leader"},
                {"name": "Samsung", "ticker": "005930.KS", "note": "Memory + foundry"},
            ],
            "growth_drivers": ["Data center expansion", "Edge AI"],
            "risks": ["Geopolitical tension", "Overcapacity risk"],
            "regulatory": ["US export controls", "CHIPS Act funding"],
            "investor_focus": ["CAPEX cycle", "EUV adoption"],
            "raw_response": "...",
        },
        "api_unavailable": False,
    }


def _full_market_data():
    """Complete market research data."""
    return {
        "market": "日経平均",
        "type": "market",
        "grok_research": {
            "price_action": "Nikkei rose 1.5% on strong corporate earnings",
            "macro_factors": ["BOJ rate decision", "Yen weakness vs USD"],
            "sentiment": {"score": 0.4, "summary": "Cautiously optimistic"},
            "upcoming_events": ["GDP release Friday", "BOJ meeting next week"],
            "sector_rotation": ["Rotation from defensive to cyclical"],
            "raw_response": "...",
        },
        "api_unavailable": False,
    }


# ===================================================================
# format_stock_research
# ===================================================================

class TestFormatStockResearch:

    def test_full_data(self):
        """Full data produces a complete Markdown report."""
        output = format_stock_research(_full_stock_data())

        # Title
        assert "Toyota Motor Corporation (7203.T)" in output
        assert "深掘りリサーチ" in output

        # Basic info table
        assert "基本情報" in output
        assert "Consumer Cyclical" in output
        assert "Auto Manufacturers" in output

        # Valuation table
        assert "バリュエーション" in output
        assert "PER" in output
        assert "10.50" in output
        assert "PBR" in output
        assert "1.10" in output
        assert "配当利回り" in output
        assert "2.80%" in output
        assert "ROE" in output
        assert "12.00%" in output
        assert "72.50" in output

        # News section
        assert "最新ニュース" in output
        assert "Toyota Q3 Earnings Beat" in output
        assert "Reuters" in output

        # X Sentiment section
        assert "センチメント" in output
        assert "強気" in output

        # Grok deep research section
        assert "Strong Q3 earnings" in output
        assert "EV expansion" in output
        assert "Chip shortage" in output
        assert "Goldman: Buy" in output
        assert "Market leader in hybrid" in output

    def test_empty_grok(self):
        """Without Grok data, shows fallback message."""
        data = _full_stock_data()
        data["grok_research"] = {
            "recent_news": [],
            "catalysts": {"positive": [], "negative": []},
            "analyst_views": [],
            "x_sentiment": {"score": 0.0, "summary": "", "key_opinions": []},
            "competitive_notes": [],
            "raw_response": "",
        }
        data["x_sentiment"] = {
            "positive": [],
            "negative": [],
            "sentiment_score": 0.0,
            "raw_response": "",
        }

        output = format_stock_research(data)

        assert "XAI_API_KEY" in output
        assert "未設定" in output

    def test_none_data(self):
        """None or empty data returns a message."""
        assert "リサーチデータがありません" in format_stock_research(None)
        assert "リサーチデータがありません" in format_stock_research({})

    def test_no_news(self):
        """No news section shows appropriate message."""
        data = _full_stock_data()
        data["news"] = []

        output = format_stock_research(data)
        assert "最新ニュースはありません" in output

    def test_no_perplexity_section(self):
        """No Perplexity section in output."""
        data = _full_stock_data()
        output = format_stock_research(data)
        assert "Perplexity" not in output


# ===================================================================
# format_industry_research
# ===================================================================

class TestFormatIndustryResearch:

    def test_full_data(self):
        """Full data produces a complete industry report."""
        output = format_industry_research(_full_industry_data())

        assert "半導体 - 業界リサーチ" in output
        assert "トレンド" in output
        assert "AI chip demand surging" in output
        assert "主要プレイヤー" in output
        assert "TSMC" in output
        assert "TSM" in output
        assert "成長ドライバー" in output
        assert "Data center expansion" in output
        assert "リスク要因" in output
        assert "Geopolitical tension" in output
        assert "規制・政策動向" in output
        assert "US export controls" in output
        assert "投資家の注目ポイント" in output
        assert "CAPEX cycle" in output

    def test_api_unavailable(self):
        """API unavailable shows setup message with XAI_API_KEY."""
        data = {
            "theme": "EV",
            "type": "industry",
            "grok_research": {
                "trends": [],
                "key_players": [],
                "growth_drivers": [],
                "risks": [],
                "regulatory": [],
                "investor_focus": [],
                "raw_response": "",
            },
            "api_unavailable": True,
        }

        output = format_industry_research(data)
        assert "EV - 業界リサーチ" in output
        assert "XAI_API_KEY" in output
        assert "Perplexity" not in output

    def test_empty_data(self):
        """Empty/None data returns a message."""
        assert "リサーチデータがありません" in format_industry_research(None)
        assert "リサーチデータがありません" in format_industry_research({})


# ===================================================================
# format_market_research
# ===================================================================

class TestFormatMarketResearch:

    def test_full_data(self):
        """Full data produces a complete market report."""
        output = format_market_research(_full_market_data())

        assert "日経平均 - マーケット概況" in output
        assert "直近の値動き" in output
        assert "Nikkei rose 1.5%" in output
        assert "マクロ経済要因" in output
        assert "BOJ rate decision" in output
        assert "センチメント" in output
        assert "強気" in output  # score 0.4 >= 0.3 -> 強気
        assert "注目イベント" in output
        assert "GDP release Friday" in output
        assert "セクターローテーション" in output
        assert "Rotation from defensive to cyclical" in output

    def test_api_unavailable(self):
        """API unavailable shows Grok skip message."""
        data = {
            "market": "S&P500",
            "type": "market",
            "macro_indicators": [],
            "grok_research": {
                "price_action": "",
                "macro_factors": [],
                "sentiment": {"score": 0.0, "summary": ""},
                "upcoming_events": [],
                "sector_rotation": [],
                "raw_response": "",
            },
            "api_unavailable": True,
        }

        output = format_market_research(data)
        assert "S&P500 - マーケット概況" in output
        assert "定性分析はスキップ" in output

    def test_empty_data(self):
        """Empty/None data returns a message."""
        assert "リサーチデータがありません" in format_market_research(None)
        assert "リサーチデータがありません" in format_market_research({})

    def test_macro_table_displayed(self):
        """Macro indicators are shown as a table."""
        data = {
            "market": "日経平均",
            "type": "market",
            "macro_indicators": [
                {"name": "S&P500", "symbol": "^GSPC", "price": 5100.50,
                 "daily_change": 0.005, "weekly_change": 0.02, "is_point_diff": False},
                {"name": "VIX", "symbol": "^VIX", "price": 18.30,
                 "daily_change": -0.5, "weekly_change": -1.2, "is_point_diff": True},
            ],
            "grok_research": {
                "price_action": "",
                "macro_factors": [],
                "sentiment": {"score": 0.0, "summary": ""},
                "upcoming_events": [],
                "sector_rotation": [],
                "raw_response": "",
            },
            "api_unavailable": True,
        }

        output = format_market_research(data)
        assert "主要指標" in output
        assert "S&P500" in output
        assert "5100.50" in output
        assert "+0.50%" in output  # daily 0.5%
        assert "+2.00%" in output  # weekly 2%
        assert "VIX" in output
        assert "18.30" in output
        assert "-0.50" in output  # point diff
        assert "-1.20" in output  # point diff

    def test_vix_fear_greed(self):
        """VIX-based Fear & Greed label is displayed."""
        data = {
            "market": "S&P500",
            "type": "market",
            "macro_indicators": [
                {"name": "VIX", "symbol": "^VIX", "price": 30.0,
                 "daily_change": 2.0, "weekly_change": 5.0, "is_point_diff": True},
            ],
            "grok_research": {
                "price_action": "",
                "macro_factors": [],
                "sentiment": {"score": 0.0, "summary": ""},
                "upcoming_events": [],
                "sector_rotation": [],
                "raw_response": "",
            },
            "api_unavailable": True,
        }

        output = format_market_research(data)
        assert "Fear & Greed" in output
        assert "不安拡大" in output

    def test_no_macro_indicators(self):
        """No macro_indicators → no table section."""
        data = _full_market_data()
        data["macro_indicators"] = []

        output = format_market_research(data)
        assert "主要指標" not in output
        # Grok sections still present
        assert "直近の値動き" in output


# ===================================================================
# _sentiment_label
# ===================================================================

class TestSentimentLabel:

    def test_bullish(self):
        """Score >= 0.3 is strong bull."""
        assert _sentiment_label(0.5) == "強気"
        assert _sentiment_label(0.3) == "強気"

    def test_slightly_bullish(self):
        """Score >= 0.1 and < 0.3 is slightly bull."""
        assert _sentiment_label(0.2) == "やや強気"
        assert _sentiment_label(0.1) == "やや強気"

    def test_neutral(self):
        """Score >= -0.1 and < 0.1 is neutral."""
        assert _sentiment_label(0.0) == "中立"
        assert _sentiment_label(0.05) == "中立"
        assert _sentiment_label(-0.1) == "中立"

    def test_slightly_bearish(self):
        """Score >= -0.3 and < -0.1 is slightly bear."""
        assert _sentiment_label(-0.2) == "やや弱気"
        assert _sentiment_label(-0.15) == "やや弱気"

    def test_bearish(self):
        """Score < -0.3 is strong bear."""
        assert _sentiment_label(-0.5) == "弱気"
        assert _sentiment_label(-1.0) == "弱気"


# ===================================================================
# _vix_label (KIK-396)
# ===================================================================

class TestVixLabel:

    def test_low_vol(self):
        assert _vix_label(12.0) == "低ボラティリティ（楽観相場）"

    def test_normal(self):
        assert _vix_label(20.0) == "通常レンジ"

    def test_anxiety(self):
        assert _vix_label(30.0) == "不安拡大"

    def test_panic(self):
        assert _vix_label(40.0) == "パニック水準"

    def test_boundaries(self):
        assert _vix_label(14.99) == "低ボラティリティ（楽観相場）"
        assert _vix_label(15.0) == "通常レンジ"
        assert _vix_label(24.99) == "通常レンジ"
        assert _vix_label(25.0) == "不安拡大"
        assert _vix_label(34.99) == "不安拡大"
        assert _vix_label(35.0) == "パニック水準"


# ===================================================================
# format_business_research
# ===================================================================

def _full_business_data():
    """Complete business model research data."""
    return {
        "symbol": "7751.T",
        "name": "Canon Inc.",
        "type": "business",
        "grok_research": {
            "overview": "Canon is a diversified imaging and optical company",
            "segments": [
                {"name": "Printing", "revenue_share": "55%", "description": "Inkjet and laser printers"},
                {"name": "Imaging", "revenue_share": "20%", "description": "Cameras and lenses"},
                {"name": "Medical", "revenue_share": "15%", "description": "CT/MRI equipment"},
                {"name": "Industrial", "revenue_share": "10%", "description": "Semiconductor lithography"},
            ],
            "revenue_model": "Hardware sales + consumables recurring revenue model",
            "competitive_advantages": ["Strong patent portfolio", "Brand recognition", "Vertical integration"],
            "key_metrics": ["Consumables attach rate", "B2B vs B2C revenue mix"],
            "growth_strategy": ["Medical imaging expansion", "Industrial equipment growth"],
            "risks": ["Declining print market", "Smartphone camera competition"],
            "raw_response": "...",
        },
        "api_unavailable": False,
    }


class TestFormatBusinessResearch:

    def test_full_data(self):
        """Full data produces a complete business model report."""
        output = format_business_research(_full_business_data())

        assert "Canon Inc. (7751.T)" in output
        assert "ビジネスモデル分析" in output
        assert "事業概要" in output
        assert "Canon is a diversified" in output
        assert "事業セグメント" in output
        assert "Printing" in output
        assert "55%" in output
        assert "Imaging" in output
        assert "収益モデル" in output
        assert "Hardware sales" in output
        assert "競争優位性" in output
        assert "Strong patent portfolio" in output
        assert "重要KPI" in output
        assert "Consumables attach rate" in output
        assert "成長戦略" in output
        assert "Medical imaging expansion" in output
        assert "ビジネスリスク" in output
        assert "Declining print market" in output

    def test_api_unavailable(self):
        """API unavailable shows setup message with XAI_API_KEY."""
        data = {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "type": "business",
            "grok_research": {
                "overview": "",
                "segments": [],
                "revenue_model": "",
                "competitive_advantages": [],
                "key_metrics": [],
                "growth_strategy": [],
                "risks": [],
                "raw_response": "",
            },
            "api_unavailable": True,
        }

        output = format_business_research(data)
        assert "Apple Inc. (AAPL)" in output
        assert "ビジネスモデル分析" in output
        assert "XAI_API_KEY" in output
        assert "Perplexity" not in output

    def test_empty_data(self):
        """Empty/None data returns a message."""
        assert "リサーチデータがありません" in format_business_research(None)
        assert "リサーチデータがありません" in format_business_research({})

    def test_empty_grok_sections(self):
        """Empty grok data shows '情報なし' for each section."""
        data = {
            "symbol": "TEST",
            "name": "",
            "type": "business",
            "grok_research": {
                "overview": "",
                "segments": [],
                "revenue_model": "",
                "competitive_advantages": [],
                "key_metrics": [],
                "growth_strategy": [],
                "risks": [],
                "raw_response": "...",
            },
            "api_unavailable": False,
        }

        output = format_business_research(data)
        assert output.count("情報なし") == 7  # All 7 sections show 情報なし

    def test_no_name(self):
        """Symbol only (no name) still formats correctly."""
        data = _full_business_data()
        data["name"] = ""
        output = format_business_research(data)
        assert "7751.T - ビジネスモデル分析" in output

    def test_non_dict_segment(self):
        """Non-dict segment items render as fallback row."""
        data = _full_business_data()
        data["grok_research"]["segments"] = ["Division A", {"name": "Division B", "revenue_share": "60%", "description": "Main"}]
        output = format_business_research(data)
        assert "| Division A | - | - |" in output
        assert "| Division B | 60% | Main |" in output

    def test_no_perplexity_section(self):
        """No Perplexity section in output."""
        output = format_business_research(_full_business_data())
        assert "Perplexity" not in output
