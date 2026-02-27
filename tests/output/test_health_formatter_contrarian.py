"""Tests for KIK-519: Contrarian display in health formatter."""

import pytest
from src.output.health_formatter import format_health_check


def _make_stock_pos(symbol, pnl_pct=0.05, alert_level="none", contrarian=None):
    """Helper for a stock position with optional contrarian data."""
    return {
        "symbol": symbol,
        "pnl_pct": pnl_pct,
        "trend_health": {"trend": "上昇", "rsi": 45.0, "sma50": 120.0, "sma200": 110.0},
        "change_quality": {
            "is_etf": False,
            "quality_label": "良好",
            "change_score": 60,
        },
        "long_term": {"label": "適性あり"},
        "return_stability": {"label": "✅ 安定", "stability": "stable", "latest_rate": 0.03, "avg_rate": 0.025},
        "alert": {
            "level": alert_level,
            "label": {"none": "なし", "caution": "注意", "exit": "撤退検討", "early_warning": "早期警告"}[alert_level],
            "emoji": {"none": "", "caution": "⚠️", "exit": "🚨", "early_warning": "⏰"}[alert_level],
            "reasons": ["テスト理由"] if alert_level != "none" else [],
        },
        "contrarian": contrarian,
    }


def _make_contrarian(score=65, grade="B", tech=22, val=18, fund=25):
    """Helper for contrarian data dict."""
    return {
        "contrarian_score": score,
        "grade": grade,
        "technical": {"score": tech},
        "valuation": {"score": val},
        "fundamental": {"score": fund},
    }


def _make_health_data(stock_positions, alerts=None):
    """Build health check data dict."""
    all_alerts = alerts or [p for p in stock_positions if p["alert"]["level"] != "none"]
    return {
        "positions": stock_positions,
        "stock_positions": stock_positions,
        "etf_positions": [],
        "alerts": all_alerts,
        "summary": {
            "total": len(stock_positions),
            "healthy": sum(1 for p in stock_positions if p["alert"]["level"] == "none"),
            "early_warning": sum(1 for p in stock_positions if p["alert"]["level"] == "early_warning"),
            "caution": sum(1 for p in stock_positions if p["alert"]["level"] == "caution"),
            "exit": sum(1 for p in stock_positions if p["alert"]["level"] == "exit"),
        },
        "small_cap_allocation": None,
    }


class TestContrarianColumnInTable:
    """Test contrarian column in stock health table."""

    def test_contrarian_header_present(self):
        """Stock table should have '逆張り' column header."""
        data = _make_health_data([_make_stock_pos("7203.T")])
        output = format_health_check(data)
        assert "逆張り" in output

    def test_contrarian_grade_score_displayed(self):
        """Alerted stock with contrarian data should show grade+score."""
        ct = _make_contrarian(score=72, grade="A")
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "A72" in output

    def test_no_contrarian_shows_dash(self):
        """Healthy stock without contrarian should show '-'."""
        pos = _make_stock_pos("7203.T", contrarian=None)
        data = _make_health_data([pos])
        output = format_health_check(data)
        # Should have a "-" in the contrarian column, not a score
        lines = output.split("\n")
        table_rows = [l for l in lines if l.startswith("| 7203.T")]
        assert len(table_rows) == 1
        # Last column before closing |
        cols = table_rows[0].split("|")
        contrarian_col = cols[-2].strip()
        assert contrarian_col == "-"

    def test_zero_score_shows_dash(self):
        """Contrarian with score=0 should show '-'."""
        ct = _make_contrarian(score=0, grade="D")
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        lines = output.split("\n")
        table_rows = [l for l in lines if l.startswith("| 7203.T")]
        cols = table_rows[0].split("|")
        contrarian_col = cols[-2].strip()
        assert contrarian_col == "-"

    def test_multiple_stocks_contrarian_column(self):
        """Multiple stocks should each have correct contrarian display."""
        ct_a = _make_contrarian(score=80, grade="A")
        pos1 = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct_a)
        pos2 = _make_stock_pos("AAPL", contrarian=None)
        data = _make_health_data([pos1, pos2])
        output = format_health_check(data)
        assert "A80" in output


class TestContrarianInAlertDetail:
    """Test contrarian detail display in alert section."""

    def test_contrarian_detail_for_alerted_stock(self):
        """Alert detail should include contrarian score breakdown."""
        ct = _make_contrarian(score=65, grade="B", tech=22, val=18, fund=25)
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "逆張りスコア: 65/100" in output
        assert "グレードB" in output
        # No denominators — axis raw scores only (KIK-519 arch review fix)
        assert "テク22" in output
        assert "バリュ18" in output
        assert "ファンダ25" in output
        # Should NOT have /40 /30 denominators
        assert "/40" not in output
        assert "バリュ18/30" not in output

    def test_grade_a_buy_candidate(self):
        """Grade A should show '逆張り買い候補' message."""
        ct = _make_contrarian(score=85, grade="A")
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "逆張り買い候補" in output

    def test_grade_b_buy_candidate(self):
        """Grade B should also show '逆張り買い候補' message."""
        ct = _make_contrarian(score=65, grade="B")
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "逆張り買い候補" in output

    def test_grade_c_weak_signal(self):
        """Grade C should show '弱い逆張りシグナル' message."""
        ct = _make_contrarian(score=45, grade="C")
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "弱い逆張りシグナル" in output

    def test_grade_d_no_signal(self):
        """Grade D (score > 0 but low) should show score but no buy message."""
        ct = _make_contrarian(score=20, grade="D")
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "逆張りスコア: 20/100" in output
        assert "逆張り買い候補" not in output
        assert "弱い逆張りシグナル" not in output

    def test_no_contrarian_no_detail(self):
        """Alerted stock without contrarian data should not show contrarian detail."""
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=None)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "逆張りスコア" not in output

    def test_exit_stock_with_contrarian(self):
        """EXIT level stock should also show contrarian detail."""
        ct = _make_contrarian(score=72, grade="A")
        pos = _make_stock_pos("7203.T", alert_level="exit", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "逆張りスコア: 72/100" in output
        assert "逆張り買い候補" in output

    def test_4axis_shows_sentiment(self):
        """4-axis mode should show sentiment in breakdown."""
        ct = _make_contrarian(score=75, grade="A")
        ct["sentiment"] = {"score": 15.0, "sentiment_score": -0.6}
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        assert "センチ15" in output
        assert "テク22" in output

    def test_3axis_no_sentiment_in_breakdown(self):
        """3-axis mode (no sentiment) should not show 'センチ' in score breakdown."""
        ct = _make_contrarian(score=65, grade="B")
        pos = _make_stock_pos("7203.T", alert_level="caution", contrarian=ct)
        data = _make_health_data([pos])
        output = format_health_check(data)
        # The breakdown line should not have センチ score
        breakdown_lines = [l for l in output.split("\n") if "逆張りスコア" in l]
        assert len(breakdown_lines) == 1
        assert "センチ" not in breakdown_lines[0]

    def test_table_column_count(self):
        """Stock table should have 8 columns (symbol, pnl, trend, quality, alert, lt, rs, contrarian)."""
        pos = _make_stock_pos("7203.T")
        data = _make_health_data([pos])
        output = format_health_check(data)
        lines = output.split("\n")
        # Find the separator line (|:-----|...)
        sep_lines = [l for l in lines if l.startswith("|:-----")]
        assert len(sep_lines) >= 1
        # Count columns: number of | minus 1
        col_count = sep_lines[0].count("|") - 1
        assert col_count == 8
