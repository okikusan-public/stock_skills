"""Tests for morning summary anomaly detection (KIK-717)."""

import pytest
from datetime import date, timedelta

from src.data.morning_summary import (
    detect_alerts,
    format_morning_summary,
    _calc_rsi,
    ALERT_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pos(symbol="TEST", cost_price=100.0, next_earnings=""):
    return {"symbol": symbol, "cost_price": cost_price, "next_earnings": next_earnings}


def _info(symbol="TEST", price=100.0):
    return {"symbol": symbol, "price": price}


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

class TestCalcRSI:
    def test_insufficient_data(self):
        assert _calc_rsi([1, 2, 3]) is None

    def test_all_gains(self):
        closes = list(range(1, 20))
        assert _calc_rsi(closes) == 100.0

    def test_normal_range(self):
        closes = [100 + i * 0.5 * ((-1) ** i) for i in range(20)]
        rsi = _calc_rsi(closes)
        assert rsi is not None
        assert 0 <= rsi <= 100


# ---------------------------------------------------------------------------
# detect_alerts
# ---------------------------------------------------------------------------

class TestDetectAlerts:
    def test_no_alerts_clean_pf(self):
        positions = [_pos("MSFT", 100)]
        infos = {"MSFT": _info("MSFT", 110)}
        histories = {"MSFT": [100 + i * 0.3 for i in range(20)]}
        alerts = detect_alerts(positions, infos, histories)
        # No exit-rule, RSI should be normal, no VIX, no earnings
        assert len([a for a in alerts if a["type"] in ("exit_rule", "hard_stop")]) == 0

    def test_exit_rule_triggered(self):
        positions = [_pos("CANON", 100)]
        infos = {"CANON": _info("CANON", 84)}  # -16%
        histories = {"CANON": [90] * 20}
        alerts = detect_alerts(positions, infos, histories)
        exit_alerts = [a for a in alerts if a["type"] == "exit_rule"]
        assert len(exit_alerts) == 1
        assert exit_alerts[0]["severity"] == "CRITICAL"

    def test_hard_stop_triggered(self):
        positions = [_pos("DEC", 100)]
        infos = {"DEC": _info("DEC", 79)}  # -21%
        histories = {"DEC": [80] * 20}
        alerts = detect_alerts(positions, infos, histories)
        hard = [a for a in alerts if a["type"] == "hard_stop"]
        assert len(hard) == 1

    def test_rsi_overbought(self):
        # Create ascending prices to push RSI high
        closes = [100 + i * 2 for i in range(20)]
        positions = [_pos("AMZN", 200)]
        infos = {"AMZN": _info("AMZN", 250)}
        alerts = detect_alerts(positions, infos, {"AMZN": closes})
        rsi_alerts = [a for a in alerts if a["type"] == "rsi_high"]
        assert len(rsi_alerts) >= 1

    def test_rsi_oversold(self):
        closes = [100 - i * 2 for i in range(20)]
        positions = [_pos("CANON", 100)]
        infos = {"CANON": _info("CANON", 60)}
        alerts = detect_alerts(positions, infos, {"CANON": closes})
        rsi_alerts = [a for a in alerts if a["type"] == "rsi_low"]
        assert len(rsi_alerts) >= 1

    def test_earnings_soon(self):
        earn_date = (date.today() + timedelta(days=3)).isoformat()
        positions = [_pos("MSFT", 400, next_earnings=earn_date)]
        infos = {"MSFT": _info("MSFT", 420)}
        alerts = detect_alerts(positions, infos, {})
        earn_alerts = [a for a in alerts if a["type"] == "earnings_soon"]
        assert len(earn_alerts) == 1
        assert earn_alerts[0]["value"] == 3

    def test_earnings_far_no_alert(self):
        earn_date = (date.today() + timedelta(days=30)).isoformat()
        positions = [_pos("MSFT", 400, next_earnings=earn_date)]
        infos = {"MSFT": _info("MSFT", 420)}
        alerts = detect_alerts(positions, infos, {})
        earn_alerts = [a for a in alerts if a["type"] == "earnings_soon"]
        assert len(earn_alerts) == 0

    def test_vix_elevated(self):
        alerts = detect_alerts([], {}, {}, vix_price=27.5)
        vix_alerts = [a for a in alerts if a["type"] == "vix_high"]
        assert len(vix_alerts) == 1
        assert vix_alerts[0]["severity"] == "INFO"

    def test_vix_extreme(self):
        alerts = detect_alerts([], {}, {}, vix_price=35.0)
        vix_alerts = [a for a in alerts if a["type"] == "vix_high"]
        assert len(vix_alerts) == 1
        assert vix_alerts[0]["severity"] == "CRITICAL"

    def test_vix_normal_no_alert(self):
        alerts = detect_alerts([], {}, {}, vix_price=18.0)
        assert len(alerts) == 0

    def test_state_change_filter(self):
        """Alerts that existed yesterday should be filtered out."""
        positions = [_pos("CANON", 100)]
        infos = {"CANON": _info("CANON", 84)}
        histories = {"CANON": [85] * 20}
        prev = [{"symbol": "CANON", "type": "exit_rule"}]
        alerts = detect_alerts(positions, infos, histories, prev_alerts=prev)
        exit_alerts = [a for a in alerts if a["type"] == "exit_rule"]
        assert len(exit_alerts) == 0  # filtered by state-change

    def test_hard_stop_excludes_exit_rule(self):
        """At -21%, only hard_stop fires, not exit_rule (elif)."""
        positions = [_pos("DEC", 100)]
        infos = {"DEC": _info("DEC", 78)}  # -22%
        alerts = detect_alerts(positions, infos, {"DEC": [80]*20})
        types = [a["type"] for a in alerts if a["symbol"] == "DEC"]
        assert "hard_stop" in types
        assert "exit_rule" not in types

    def test_multiple_alerts_same_stock(self):
        """A stock can have exit_rule + rsi_low simultaneously."""
        closes = [100 - i * 3 for i in range(20)]  # descending → RSI low
        positions = [_pos("CANON", 100)]
        infos = {"CANON": _info("CANON", 84)}  # -16%
        alerts = detect_alerts(positions, infos, {"CANON": closes})
        types = [a["type"] for a in alerts if a["symbol"] == "CANON"]
        assert "exit_rule" in types
        assert "rsi_low" in types

    def test_malformed_earnings_date(self):
        """Malformed next_earnings should not crash."""
        positions = [_pos("TEST", 100, next_earnings="not-a-date")]
        infos = {"TEST": _info("TEST", 105)}
        alerts = detect_alerts(positions, infos, {})
        earn = [a for a in alerts if a["type"] == "earnings_soon"]
        assert len(earn) == 0  # graceful skip

    def test_format_truncates_critical(self):
        """More than 3 CRITICAL alerts: only first 3 shown."""
        alerts = [
            {"symbol": f"S{i}", "type": "exit_rule", "severity": "CRITICAL",
             "message": f"test{i}", "value": -16}
            for i in range(5)
        ]
        result = format_morning_summary(alerts)
        assert result.count("🔴") == 3

    def test_severity_ordering(self):
        """CRITICAL alerts come before INFO."""
        positions = [_pos("A", 100)]
        infos = {"A": _info("A", 84)}
        alerts = detect_alerts(positions, infos, {"A": [85]*20}, vix_price=27)
        # A: exit_rule (CRITICAL) + VIX (INFO)
        assert len(alerts) >= 2
        assert alerts[0]["severity"] == "CRITICAL"


# ---------------------------------------------------------------------------
# format_morning_summary
# ---------------------------------------------------------------------------

class TestFormatMorningSummary:
    def test_no_alerts(self):
        result = format_morning_summary([])
        assert "☀️ 異常なし" in result

    def test_with_alerts(self):
        alerts = [
            {"symbol": "CANON", "type": "exit_rule", "severity": "CRITICAL",
             "message": "損益-16% → exit-rule到達", "value": -16},
            {"symbol": "^VIX", "type": "vix_high", "severity": "INFO",
             "message": "VIX 27.5", "value": 27.5},
        ]
        result = format_morning_summary(alerts)
        assert "⚠️" in result
        assert "CANON" in result
        assert "VIX" in result

    def test_deepdive_suggestion(self):
        alerts = [
            {"symbol": "7751.T", "type": "exit_rule", "severity": "CRITICAL",
             "message": "test", "value": -16},
        ]
        result = format_morning_summary(alerts)
        assert "売るべきか" in result

    def test_includes_date(self):
        result = format_morning_summary([])
        today = date.today().strftime("%m/%d")
        assert today in result
