"""Tests for adjustment plan formatter (KIK-496)."""

import pytest

from src.core.portfolio.market_regime import MarketRegime
from src.core.portfolio.adjustment_advisor import (
    Action,
    ActionType,
    AdjustmentPlan,
    Urgency,
)
from src.output.adjust_formatter import format_adjustment_plan


def _regime(name: str = "neutral") -> MarketRegime:
    return MarketRegime(
        regime=name,
        sma50_above_200=(name == "bull"),
        rsi=45.0,
        drawdown=-0.08,
        index_symbol="^N225",
    )


class TestFormatAdjustmentPlan:
    def test_empty_plan(self):
        plan = AdjustmentPlan(
            regime=_regime(),
            actions=[],
            candidates={},
            summary="0 HIGH / 0 MEDIUM / 0 LOW actions. Regime: neutral.",
        )
        output = format_adjustment_plan(plan)
        assert "調整不要" in output
        assert "Portfolio Adjustment Plan" in output

    def test_with_actions(self):
        actions = [
            Action(ActionType.SELL, "7203.T", Urgency.HIGH, ["EXIT判定"], ["P1"]),
            Action(ActionType.FLAG, "9984.T", Urgency.MEDIUM, ["バリュートラップの疑い"], ["P2"]),
            Action(ActionType.FLAG, "AAPL", Urgency.LOW, ["短期向き銘柄"], ["P5"]),
        ]
        plan = AdjustmentPlan(
            regime=_regime("bear"),
            actions=actions,
            candidates={},
            summary="1 HIGH / 1 MEDIUM / 1 LOW actions. Regime: bear.",
        )
        output = format_adjustment_plan(plan)

        assert "HIGH Priority" in output
        assert "MEDIUM Priority" in output
        assert "LOW Priority" in output
        assert "7203.T" in output
        assert "SELL" in output
        assert "EXIT判定" in output
        assert "P1" in output
        assert "9984.T" in output
        assert "AAPL" in output

    def test_regime_display(self):
        plan = AdjustmentPlan(
            regime=_regime("crash"),
            actions=[],
            candidates={},
            summary="test",
        )
        output = format_adjustment_plan(plan)
        assert "CRASH" in output
        assert "SMA50 < SMA200" in output
        assert "RSI 45.0" in output

    def test_bull_regime_display(self):
        plan = AdjustmentPlan(
            regime=_regime("bull"),
            actions=[],
            candidates={},
            summary="test",
        )
        output = format_adjustment_plan(plan)
        assert "BULL" in output
        assert "SMA50 > SMA200" in output

    def test_multiple_reasons(self):
        actions = [
            Action(
                ActionType.SELL, "X", Urgency.HIGH,
                ["EXIT判定", "バリュートラップ"],
                ["P1", "P2"],
            ),
        ]
        plan = AdjustmentPlan(
            regime=_regime(), actions=actions, candidates={}, summary="test"
        )
        output = format_adjustment_plan(plan)
        assert "EXIT判定; バリュートラップ" in output
        assert "P1, P2" in output

    def test_summary_displayed(self):
        plan = AdjustmentPlan(
            regime=_regime(),
            actions=[Action(ActionType.FLAG, "X", Urgency.LOW, ["r"], ["P5"])],
            candidates={},
            summary="0 HIGH / 0 MEDIUM / 1 LOW actions. Regime: neutral.",
        )
        output = format_adjustment_plan(plan)
        assert "Summary" in output
        assert "1 LOW" in output
