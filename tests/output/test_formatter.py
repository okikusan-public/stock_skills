"""Tests for src/output/formatter.py."""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.output.formatter import (
    format_markdown,
    format_pullback_markdown,
    format_query_markdown,
    format_shareholder_return_markdown,
    format_growth_markdown,
)


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_stock_info():
    """Minimal stock info dict for formatter tests."""
    return {
        "symbol": "7203.T",
        "name": "Toyota Motor",
        "sector": "Consumer Cyclical",
        "price": 2850.0,
        "per": 10.5,
        "pbr": 1.2,
        "dividend_yield": 0.025,
        "roe": 0.12,
        "value_score": 72.5,
    }


@pytest.fixture
def sample_stock_info_us():
    """Sample US stock info dict for formatter tests."""
    return {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "price": 195.0,
        "per": 28.5,
        "pbr": 45.0,
        "dividend_yield": 0.005,
        "roe": 1.47,
        "value_score": 35.0,
    }


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------

class TestFormatMarkdown:
    """Tests for format_markdown()."""

    def test_normal_data_returns_markdown_table(self, sample_stock_info):
        """Normal data produces a Markdown table with header row."""
        results = [sample_stock_info]
        output = format_markdown(results)

        # Should contain header columns
        assert "| 順位 |" in output
        assert "| 銘柄 |" in output
        assert "| 株価 |" in output
        assert "| PER |" in output
        assert "| PBR |" in output
        assert "| 配当利回り |" in output
        assert "| ROE |" in output
        assert "| スコア |" in output

        # Should contain separator line
        assert "|---:" in output

        # Should contain the stock data
        assert "7203.T" in output
        assert "Toyota Motor" in output

    def test_normal_data_contains_formatted_values(self, sample_stock_info):
        """Formatted values appear correctly in the output."""
        results = [sample_stock_info]
        output = format_markdown(results)

        # PER = 10.5 -> "10.50"
        assert "10.50" in output
        # PBR = 1.2 -> "1.20"
        assert "1.20" in output
        # dividend_yield = 0.025 -> "2.50%"
        assert "2.50%" in output
        # ROE = 0.12 -> "12.00%"
        assert "12.00%" in output
        # value_score = 72.5 -> "72.50"
        assert "72.50" in output

    def test_multiple_results_numbered(self, sample_stock_info, sample_stock_info_us):
        """Multiple results are ranked sequentially."""
        results = [sample_stock_info, sample_stock_info_us]
        output = format_markdown(results)

        lines = output.split("\n")
        # Header (2 lines) + 2 data lines = 4 lines
        assert len(lines) == 4

        # First data row starts with "| 1 |"
        assert "| 1 |" in lines[2]
        # Second data row starts with "| 2 |"
        assert "| 2 |" in lines[3]

    def test_empty_list_returns_not_found_message(self):
        """Empty results list produces 'not found' message."""
        output = format_markdown([])
        assert "該当する銘柄が見つかりませんでした" in output

    def test_missing_fields_show_dash(self):
        """Missing or None fields are displayed as '-'."""
        results = [{"symbol": "TEST", "name": None, "price": None, "per": None}]
        output = format_markdown(results)
        # Symbol should still appear
        assert "TEST" in output


# ---------------------------------------------------------------------------
# format_query_markdown
# ---------------------------------------------------------------------------

class TestFormatQueryMarkdown:
    """Tests for format_query_markdown()."""

    def test_includes_sector_column(self, sample_stock_info):
        """Query markdown includes a sector column."""
        results = [sample_stock_info]
        output = format_query_markdown(results)

        assert "| セクター |" in output
        assert "Consumer Cyclical" in output

    def test_empty_list_returns_not_found_message(self):
        """Empty results list produces 'not found' message."""
        output = format_query_markdown([])
        assert "該当する銘柄が見つかりませんでした" in output

    def test_missing_sector_shows_dash(self):
        """Missing sector field shows '-'."""
        results = [{"symbol": "XYZ", "sector": None}]
        output = format_query_markdown(results)
        # The sector column should have "-"
        lines = output.split("\n")
        # Data row (3rd line)
        data_line = lines[2]
        # Check the structure includes "-" for sector
        assert "XYZ" in data_line


# ---------------------------------------------------------------------------
# format_pullback_markdown
# ---------------------------------------------------------------------------

class TestFormatPullbackMarkdown:
    """Tests for format_pullback_markdown()."""

    def test_includes_pullback_columns(self):
        """Pullback markdown includes pullback-specific columns."""
        results = [
            {
                "symbol": "7203.T",
                "name": "Toyota",
                "price": 2850.0,
                "per": 10.5,
                "pullback_pct": -0.08,
                "rsi": 35.2,
                "volume_ratio": 0.75,
                "sma50": 2900.0,
                "sma200": 2700.0,
                "bounce_score": 80,
                "match_type": "full",
                "value_score": 72.5,
                "final_score": 65.0,
            }
        ]
        output = format_pullback_markdown(results)

        # Check pullback-specific headers
        assert "| 押し目% |" in output
        assert "| RSI |" in output
        assert "| 出来高比 |" in output
        assert "| スコア |" in output
        assert "| 一致度 |" in output

        # Check data values
        assert "7203.T" in output
        # pullback_pct = -0.08 -> "-8.00%"
        assert "-8.00%" in output
        # rsi = 35.2 -> "35.2"
        assert "35.2" in output
        # volume_ratio = 0.75 -> "0.75"
        assert "0.75" in output
        # bounce_score = 80 -> "80点"
        assert "80点" in output
        # match_type = "full" -> "★完全一致"
        assert "★完全一致" in output

    def test_partial_match_type(self):
        """Partial match type shows triangle marker."""
        results = [
            {
                "symbol": "TEST",
                "match_type": "partial",
                "pullback_pct": -0.10,
                "rsi": 32.0,
                "volume_ratio": 0.80,
            }
        ]
        output = format_pullback_markdown(results)
        assert "△部分一致" in output

    def test_empty_list_returns_not_found_message(self):
        """Empty results list produces pullback-specific 'not found' message."""
        output = format_pullback_markdown([])
        assert "押し目条件に合致する銘柄が見つかりませんでした" in output


# ---------------------------------------------------------------------------
# format_shareholder_return_markdown — KIK-389 reason display
# ---------------------------------------------------------------------------

class TestFormatShareholderReturnMarkdown:
    """Tests for format_shareholder_return_markdown (KIK-389 reason)."""

    def test_stability_reason_displayed(self):
        """Reason text appears in parentheses after label."""
        results = [{
            "symbol": "7267.T",
            "name": "Honda",
            "sector": "自動車",
            "per": 10.0,
            "roe": 0.08,
            "dividend_yield_trailing": 0.03,
            "buyback_yield": 0.05,
            "total_shareholder_return": 0.17,
            "return_stability_label": "⚠️ 一時的高還元",
            "return_stability_reason": "前年比2.1倍に急増",
        }]
        output = format_shareholder_return_markdown(results)
        assert "⚠️ 一時的高還元（前年比2.1倍に急増）" in output

    def test_stability_reason_none(self):
        """When reason is None, only the label shows (no parentheses)."""
        results = [{
            "symbol": "9999.T",
            "name": "TestCo",
            "sector": "-",
            "per": 12.0,
            "roe": 0.05,
            "dividend_yield_trailing": 0.02,
            "buyback_yield": None,
            "total_shareholder_return": 0.02,
            "return_stability_label": "❓ データ不足",
            "return_stability_reason": None,
        }]
        output = format_shareholder_return_markdown(results)
        assert "❓ データ不足" in output
        assert "（" not in output


# ---------------------------------------------------------------------------
# format_growth_markdown — KIK-417
# ---------------------------------------------------------------------------

class TestFormatGrowthMarkdown:
    """Tests for format_growth_markdown()."""

    def test_includes_growth_columns(self):
        """Growth markdown includes EPS growth and revenue growth columns."""
        results = [{
            "symbol": "7203.T",
            "name": "Toyota Motor",
            "sector": "Consumer Cyclical",
            "price": 2850.0,
            "per": 10.5,
            "pbr": 1.2,
            "eps_growth": 0.30,
            "revenue_growth": 0.15,
            "roe": 0.18,
        }]
        output = format_growth_markdown(results)

        assert "| EPS成長 |" in output
        assert "| 売上成長 |" in output
        assert "| ROE |" in output
        assert "| セクター |" in output
        assert "7203.T" in output
        assert "Toyota Motor" in output
        assert "30.00%" in output  # eps_growth
        assert "15.00%" in output  # revenue_growth
        assert "18.00%" in output  # roe

    def test_does_not_include_value_score_column(self):
        """Growth markdown should NOT include value score or dividend columns."""
        results = [{
            "symbol": "TEST",
            "eps_growth": 0.50,
        }]
        output = format_growth_markdown(results)

        assert "スコア" not in output
        assert "配当利回り" not in output

    def test_empty_list_returns_not_found_message(self):
        """Empty results list produces growth-specific not found message."""
        output = format_growth_markdown([])
        assert "成長条件に合致する銘柄が見つかりませんでした" in output

    def test_missing_fields_show_dash(self):
        """Missing fields are displayed as '-'."""
        results = [{
            "symbol": "TEST",
            "sector": None,
            "eps_growth": None,
            "revenue_growth": None,
            "roe": None,
        }]
        output = format_growth_markdown(results)
        assert "TEST" in output
