"""Tests for KIK-469 Phase 2: Health formatter stock/ETF split display."""

import pytest
from src.output.health_formatter import format_health_check


def _make_stock_pos(symbol, pnl_pct=0.05, alert_level="none"):
    """Helper for a stock position."""
    return {
        "symbol": symbol,
        "pnl_pct": pnl_pct,
        "trend_health": {"trend": "上昇"},
        "change_quality": {
            "is_etf": False,
            "label": "良好",
        },
        "long_term": {"label": "適性あり"},
        "shareholder_return_stability": {"label": "✅ 安定"},
        "alert": {"level": alert_level, "label": "なし", "emoji": ""},
    }


def _make_etf_pos(symbol, pnl_pct=0.03, alert_level="none", score=80):
    """Helper for an ETF position."""
    return {
        "symbol": symbol,
        "pnl_pct": pnl_pct,
        "trend_health": {"trend": "上昇"},
        "change_quality": {
            "is_etf": True,
            "etf_health": {
                "expense_label": "低コスト",
                "aum_label": "大型",
                "score": score,
                "alerts": [],
            },
        },
        "long_term": {},
        "alert": {"level": alert_level, "label": "なし", "emoji": ""},
    }


def _make_health_data(stock_positions=None, etf_positions=None, positions=None):
    """Build health check data dict."""
    all_positions = positions or ((stock_positions or []) + (etf_positions or []))
    data = {
        "positions": all_positions,
        "alerts": [],
        "summary": {"total": len(all_positions)},
        "small_cap_allocation": None,
    }
    if stock_positions is not None:
        data["stock_positions"] = stock_positions
    if etf_positions is not None:
        data["etf_positions"] = etf_positions
    return data


class TestHealthFormatterETFSplit:
    """Test health formatter stock/ETF table separation."""

    def test_both_sections_appear(self):
        """Mixed PF should show both section headers."""
        data = _make_health_data(
            stock_positions=[_make_stock_pos("7203.T")],
            etf_positions=[_make_etf_pos("VGK")],
        )
        output = format_health_check(data)
        assert "個別株ヘルスチェック" in output
        assert "ETFヘルスチェック" in output

    def test_etf_table_columns(self):
        """ETF table should have ETF-specific columns."""
        data = _make_health_data(
            stock_positions=[],
            etf_positions=[_make_etf_pos("VGK")],
        )
        output = format_health_check(data)
        assert "経費率" in output
        assert "AUM" in output
        assert "ETFスコア" in output

    def test_stock_table_columns(self):
        """Stock table should have stock-specific columns."""
        data = _make_health_data(
            stock_positions=[_make_stock_pos("7203.T")],
            etf_positions=[],
        )
        output = format_health_check(data)
        assert "変化の質" in output
        assert "長期適性" in output

    def test_stock_only_no_etf_header(self):
        """Stock-only PF should not show 'ETFヘルスチェック' header."""
        data = _make_health_data(
            stock_positions=[_make_stock_pos("7203.T")],
            etf_positions=[],
        )
        output = format_health_check(data)
        assert "ETFヘルスチェック" not in output

    def test_etf_only_no_stock_header(self):
        """ETF-only PF should not show '個別株ヘルスチェック' header."""
        data = _make_health_data(
            stock_positions=[],
            etf_positions=[_make_etf_pos("VGK")],
        )
        output = format_health_check(data)
        assert "個別株ヘルスチェック" not in output

    def test_backward_compat_no_partition_keys(self):
        """Old format without partition keys should render single table."""
        data = _make_health_data(
            positions=[_make_stock_pos("7203.T"), _make_stock_pos("AAPL")],
        )
        # No stock_positions/etf_positions keys
        output = format_health_check(data)
        assert "保有銘柄ヘルスチェック" in output
        assert "7203.T" in output
        assert "AAPL" in output

    def test_etf_score_display(self):
        """ETF score should be displayed in format X/100."""
        data = _make_health_data(
            stock_positions=[],
            etf_positions=[_make_etf_pos("VGK", score=85)],
        )
        output = format_health_check(data)
        assert "85/100" in output

    def test_etf_expense_label_display(self):
        """ETF expense label should appear in table."""
        data = _make_health_data(
            stock_positions=[],
            etf_positions=[_make_etf_pos("VGK")],
        )
        output = format_health_check(data)
        assert "低コスト" in output
