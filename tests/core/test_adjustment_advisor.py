"""Tests for portfolio adjustment advisor (KIK-496)."""

import pytest

from src.core.portfolio.market_regime import MarketRegime
from src.core.portfolio.adjustment_advisor import (
    Action,
    ActionType,
    AdjustmentPlan,
    Urgency,
    adjust_urgency_for_regime,
    evaluate_portfolio_rules,
    evaluate_position_rules,
    generate_adjustment_plan,
    merge_actions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _regime(name: str = "neutral") -> MarketRegime:
    return MarketRegime(
        regime=name,
        sma50_above_200=(name == "bull"),
        rsi=50.0,
        drawdown=-0.05,
        index_symbol="^N225",
    )


def _pos(
    symbol: str = "7203.T",
    alert_level: str = "none",
    is_trap: bool = False,
    is_small_cap: bool = False,
    trend: str = "上昇",
    cross_signal: str = "none",
    long_term_label: str = "要検討",
    stability: str = "stable",
    quality_label: str = "良好",
    eps_growth_status: str = "growing",
) -> dict:
    return {
        "symbol": symbol,
        "alert": {"level": alert_level},
        "value_trap": {"is_trap": is_trap},
        "is_small_cap": is_small_cap,
        "trend_health": {"trend": trend, "cross_signal": cross_signal},
        "long_term": {"label": long_term_label, "eps_growth_status": eps_growth_status},
        "return_stability": {"stability": stability},
        "change_quality": {"quality_label": quality_label},
    }


# ---------------------------------------------------------------------------
# Position rule tests (P1-P10)
# ---------------------------------------------------------------------------

class TestP1Exit:
    def test_exit_produces_sell_high(self):
        actions = evaluate_position_rules([_pos(alert_level="exit")], _regime())
        sells = [a for a in actions if "P1" in a.rule_ids]
        assert len(sells) == 1
        assert sells[0].type == ActionType.SELL
        assert sells[0].urgency == Urgency.HIGH

    def test_non_exit_no_p1(self):
        actions = evaluate_position_rules([_pos(alert_level="caution")], _regime())
        p1s = [a for a in actions if "P1" in a.rule_ids]
        assert len(p1s) == 0


class TestP2ValueTrap:
    def test_trap_plus_exit_is_swap(self):
        actions = evaluate_position_rules(
            [_pos(is_trap=True, alert_level="exit")], _regime()
        )
        p2s = [a for a in actions if "P2" in a.rule_ids]
        assert len(p2s) == 1
        assert p2s[0].type == ActionType.SWAP
        assert p2s[0].urgency == Urgency.HIGH
        assert p2s[0].screening_hint != ""

    def test_trap_only_is_flag(self):
        actions = evaluate_position_rules([_pos(is_trap=True)], _regime())
        p2s = [a for a in actions if "P2" in a.rule_ids]
        assert len(p2s) == 1
        assert p2s[0].type == ActionType.FLAG
        assert p2s[0].urgency == Urgency.MEDIUM


class TestP3SmallCap:
    def test_small_cap_caution_sells(self):
        actions = evaluate_position_rules(
            [_pos(is_small_cap=True, alert_level="caution")], _regime()
        )
        p3s = [a for a in actions if "P3" in a.rule_ids]
        assert len(p3s) == 1
        assert p3s[0].type == ActionType.SELL

    def test_small_cap_no_alert_no_action(self):
        actions = evaluate_position_rules(
            [_pos(is_small_cap=True, alert_level="none")], _regime()
        )
        p3s = [a for a in actions if "P3" in a.rule_ids]
        assert len(p3s) == 0


class TestP4DeathCross:
    def test_death_cross_plus_eps_decline(self):
        actions = evaluate_position_rules(
            [_pos(cross_signal="death_cross", eps_growth_status="declining")],
            _regime(),
        )
        p4s = [a for a in actions if "P4" in a.rule_ids]
        assert len(p4s) == 1
        assert p4s[0].type == ActionType.SELL

    def test_death_cross_without_decline(self):
        actions = evaluate_position_rules(
            [_pos(cross_signal="death_cross", eps_growth_status="growing")],
            _regime(),
        )
        p4s = [a for a in actions if "P4" in a.rule_ids]
        assert len(p4s) == 0


class TestP5ShortTerm:
    def test_short_term_label(self):
        actions = evaluate_position_rules(
            [_pos(long_term_label="短期向き")], _regime()
        )
        p5s = [a for a in actions if "P5" in a.rule_ids]
        assert len(p5s) == 1
        assert p5s[0].type == ActionType.FLAG
        assert p5s[0].urgency == Urgency.LOW

    def test_long_term_no_p5(self):
        actions = evaluate_position_rules(
            [_pos(long_term_label="長期向き")], _regime()
        )
        p5s = [a for a in actions if "P5" in a.rule_ids]
        assert len(p5s) == 0


class TestP6ReturnStability:
    def test_decreasing_stability_with_exit(self):
        actions = evaluate_position_rules(
            [_pos(stability="decreasing", alert_level="exit")], _regime()
        )
        p6s = [a for a in actions if "P6" in a.rule_ids]
        assert len(p6s) == 1
        assert p6s[0].type == ActionType.SWAP

    def test_temporary_stability_flag(self):
        actions = evaluate_position_rules(
            [_pos(stability="temporary")], _regime()
        )
        p6s = [a for a in actions if "P6" in a.rule_ids]
        assert len(p6s) == 1
        assert p6s[0].type == ActionType.FLAG
        assert p6s[0].urgency == Urgency.LOW

    def test_stable_no_action(self):
        actions = evaluate_position_rules([_pos(stability="stable")], _regime())
        p6s = [a for a in actions if "P6" in a.rule_ids]
        assert len(p6s) == 0


class TestP7Quality:
    def test_quality_multiple_decline_with_caution(self):
        actions = evaluate_position_rules(
            [_pos(quality_label="複数悪化", alert_level="caution")], _regime()
        )
        p7s = [a for a in actions if "P7" in a.rule_ids]
        assert len(p7s) == 1
        assert p7s[0].type == ActionType.SELL

    def test_quality_multiple_decline_alone(self):
        actions = evaluate_position_rules(
            [_pos(quality_label="複数悪化")], _regime()
        )
        p7s = [a for a in actions if "P7" in a.rule_ids]
        assert len(p7s) == 1
        assert p7s[0].type == ActionType.FLAG
        assert p7s[0].urgency == Urgency.MEDIUM


class TestP8Trend:
    def test_downtrend_plus_warning(self):
        actions = evaluate_position_rules(
            [_pos(trend="下降", alert_level="early_warning")], _regime()
        )
        p8s = [a for a in actions if "P8" in a.rule_ids]
        assert len(p8s) == 1
        assert p8s[0].type == ActionType.FLAG

    def test_uptrend_no_p8(self):
        actions = evaluate_position_rules(
            [_pos(trend="上昇", alert_level="early_warning")], _regime()
        )
        p8s = [a for a in actions if "P8" in a.rule_ids]
        assert len(p8s) == 0


class TestP9Correlation:
    def test_high_correlation(self):
        pos_a = _pos(symbol="AAPL", alert_level="caution")
        pos_b = _pos(symbol="MSFT", alert_level="none")
        pairs = [{"symbol_a": "AAPL", "symbol_b": "MSFT", "correlation": 0.90}]
        actions = evaluate_position_rules([pos_a, pos_b], _regime(), correlation_pairs=pairs)
        p9s = [a for a in actions if "P9" in a.rule_ids]
        assert len(p9s) == 1
        assert p9s[0].target == "AAPL"  # weaker (higher alert)

    def test_low_correlation_no_action(self):
        pairs = [{"symbol_a": "AAPL", "symbol_b": "MSFT", "correlation": 0.60}]
        actions = evaluate_position_rules(
            [_pos(symbol="AAPL"), _pos(symbol="MSFT")],
            _regime(),
            correlation_pairs=pairs,
        )
        p9s = [a for a in actions if "P9" in a.rule_ids]
        assert len(p9s) == 0


class TestP10VaR:
    def test_high_var_contribution(self):
        var_result = {
            "var_95": -0.18,
            "contributions": [{"symbol": "NVDA", "weight": 0.40}],
        }
        actions = evaluate_position_rules(
            [_pos(symbol="NVDA")], _regime(), var_result=var_result
        )
        p10s = [a for a in actions if "P10" in a.rule_ids]
        assert len(p10s) == 1

    def test_low_var_no_action(self):
        var_result = {"var_95": -0.08, "contributions": []}
        actions = evaluate_position_rules(
            [_pos()], _regime(), var_result=var_result
        )
        p10s = [a for a in actions if "P10" in a.rule_ids]
        assert len(p10s) == 0


# ---------------------------------------------------------------------------
# Portfolio rule tests (F1-F7)
# ---------------------------------------------------------------------------

class TestF1F2Concentration:
    def test_hhi_danger(self):
        actions = evaluate_portfolio_rules(
            [], concentration={"sector_hhi": 0.55}
        )
        f1s = [a for a in actions if "F1" in a.rule_ids]
        assert len(f1s) == 1
        assert f1s[0].type == ActionType.TRIM_CLASS
        assert f1s[0].urgency == Urgency.HIGH

    def test_hhi_moderate(self):
        actions = evaluate_portfolio_rules(
            [], concentration={"sector_hhi": 0.30}
        )
        f2s = [a for a in actions if "F2" in a.rule_ids]
        assert len(f2s) == 1
        assert f2s[0].type == ActionType.FLAG

    def test_hhi_ok(self):
        actions = evaluate_portfolio_rules(
            [], concentration={"sector_hhi": 0.15}
        )
        hhi_actions = [a for a in actions if "F1" in a.rule_ids or "F2" in a.rule_ids]
        assert len(hhi_actions) == 0


class TestF3F4SmallCap:
    def test_critical(self):
        actions = evaluate_portfolio_rules(
            [], small_cap_allocation={"level": "critical", "weight": 0.40}
        )
        f3s = [a for a in actions if "F3" in a.rule_ids]
        assert len(f3s) == 1
        assert f3s[0].type == ActionType.TRIM_CLASS

    def test_warning(self):
        actions = evaluate_portfolio_rules(
            [], small_cap_allocation={"level": "warning", "weight": 0.28}
        )
        f4s = [a for a in actions if "F4" in a.rule_ids]
        assert len(f4s) == 1
        assert f4s[0].type == ActionType.FLAG

    def test_ok(self):
        actions = evaluate_portfolio_rules(
            [], small_cap_allocation={"level": "ok", "weight": 0.10}
        )
        sc_actions = [a for a in actions if "F3" in a.rule_ids or "F4" in a.rule_ids]
        assert len(sc_actions) == 0


class TestF5Correlation:
    def test_high_correlation_pair(self):
        pairs = [{"symbol_a": "A", "symbol_b": "B", "correlation": 0.90}]
        actions = evaluate_portfolio_rules([], correlation_pairs=pairs)
        f5s = [a for a in actions if "F5" in a.rule_ids]
        assert len(f5s) == 1

    def test_no_high_pairs(self):
        pairs = [{"symbol_a": "A", "symbol_b": "B", "correlation": 0.60}]
        actions = evaluate_portfolio_rules([], correlation_pairs=pairs)
        f5s = [a for a in actions if "F5" in a.rule_ids]
        assert len(f5s) == 0


class TestF6VaR:
    def test_severe_var(self):
        actions = evaluate_portfolio_rules([], var_result={"var_95": -0.20})
        f6s = [a for a in actions if "F6" in a.rule_ids]
        assert len(f6s) == 1
        assert f6s[0].urgency == Urgency.HIGH

    def test_acceptable_var(self):
        actions = evaluate_portfolio_rules([], var_result={"var_95": -0.08})
        f6s = [a for a in actions if "F6" in a.rule_ids]
        assert len(f6s) == 0


class TestF7Stress:
    def test_severe_stress(self):
        actions = evaluate_portfolio_rules(
            [], stress_result={"max_portfolio_loss": -0.35}
        )
        f7s = [a for a in actions if "F7" in a.rule_ids]
        assert len(f7s) == 1

    def test_acceptable_stress(self):
        actions = evaluate_portfolio_rules(
            [], stress_result={"max_portfolio_loss": -0.15}
        )
        f7s = [a for a in actions if "F7" in a.rule_ids]
        assert len(f7s) == 0


# ---------------------------------------------------------------------------
# Urgency regime adjustment
# ---------------------------------------------------------------------------

class TestUrgencyAdjustment:
    def test_crash_escalates_low_to_medium(self):
        actions = [Action(ActionType.FLAG, "X", Urgency.LOW, ["r"], ["P5"])]
        adjust_urgency_for_regime(actions, _regime("crash"))
        assert actions[0].urgency == Urgency.MEDIUM

    def test_crash_escalates_medium_to_high(self):
        actions = [Action(ActionType.FLAG, "X", Urgency.MEDIUM, ["r"], ["P7"])]
        adjust_urgency_for_regime(actions, _regime("crash"))
        assert actions[0].urgency == Urgency.HIGH

    def test_bear_escalates_p3_low(self):
        actions = [Action(ActionType.FLAG, "X", Urgency.LOW, ["r"], ["P3"])]
        adjust_urgency_for_regime(actions, _regime("bear"))
        assert actions[0].urgency == Urgency.MEDIUM

    def test_bear_no_escalation_p5(self):
        actions = [Action(ActionType.FLAG, "X", Urgency.LOW, ["r"], ["P5"])]
        adjust_urgency_for_regime(actions, _regime("bear"))
        assert actions[0].urgency == Urgency.LOW

    def test_bull_no_change(self):
        actions = [Action(ActionType.FLAG, "X", Urgency.LOW, ["r"], ["P5"])]
        adjust_urgency_for_regime(actions, _regime("bull"))
        assert actions[0].urgency == Urgency.LOW


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

class TestMergeActions:
    def test_merge_same_target(self):
        a1 = Action(ActionType.FLAG, "X", Urgency.MEDIUM, ["reason1"], ["P2"])
        a2 = Action(ActionType.SELL, "X", Urgency.HIGH, ["reason2"], ["P1"])
        merged = merge_actions([a1, a2])
        assert len(merged) == 1
        assert merged[0].type == ActionType.SELL  # highest priority
        assert merged[0].urgency == Urgency.HIGH
        assert "reason1" in merged[0].reasons
        assert "reason2" in merged[0].reasons
        assert "P1" in merged[0].rule_ids
        assert "P2" in merged[0].rule_ids

    def test_merge_preserves_screening_from_swap(self):
        a1 = Action(ActionType.FLAG, "X", Urgency.LOW, ["r1"], ["P5"])
        a2 = Action(
            ActionType.SWAP, "X", Urgency.MEDIUM, ["r2"], ["P6"],
            screening_hint="高還元株",
        )
        merged = merge_actions([a1, a2])
        assert merged[0].screening_hint == "高還元株"

    def test_no_merge_different_targets(self):
        a1 = Action(ActionType.SELL, "A", Urgency.HIGH, ["r"], ["P1"])
        a2 = Action(ActionType.FLAG, "B", Urgency.LOW, ["r"], ["P5"])
        merged = merge_actions([a1, a2])
        assert len(merged) == 2

    def test_single_action_passthrough(self):
        a = Action(ActionType.FLAG, "X", Urgency.LOW, ["r"], ["P5"])
        merged = merge_actions([a])
        assert len(merged) == 1
        assert merged[0] is a


# ---------------------------------------------------------------------------
# generate_adjustment_plan
# ---------------------------------------------------------------------------

class TestGenerateAdjustmentPlan:
    def test_empty_positions_no_actions(self):
        health = {"positions": [], "small_cap_allocation": None}
        plan = generate_adjustment_plan(health, _regime())
        assert isinstance(plan, AdjustmentPlan)
        assert len(plan.actions) == 0
        assert "0 HIGH" in plan.summary

    def test_exit_position_produces_sell(self):
        health = {
            "positions": [_pos(alert_level="exit")],
            "small_cap_allocation": None,
        }
        plan = generate_adjustment_plan(health, _regime())
        sells = [a for a in plan.actions if a.type == ActionType.SELL]
        assert len(sells) >= 1

    def test_multiple_rules_fire_and_merge(self):
        # Position with EXIT + value trap → P1 (SELL) + P2 (SWAP) → merged to SELL
        health = {
            "positions": [_pos(alert_level="exit", is_trap=True)],
            "small_cap_allocation": None,
        }
        plan = generate_adjustment_plan(health, _regime())
        target_actions = [a for a in plan.actions if a.target == "7203.T"]
        assert len(target_actions) == 1  # merged
        assert target_actions[0].type == ActionType.SELL
        assert "P1" in target_actions[0].rule_ids
        assert "P2" in target_actions[0].rule_ids

    def test_sorted_by_urgency(self):
        health = {
            "positions": [
                _pos(symbol="A", alert_level="exit"),
                _pos(symbol="B", long_term_label="短期向き"),
            ],
            "small_cap_allocation": None,
        }
        plan = generate_adjustment_plan(health, _regime())
        if len(plan.actions) >= 2:
            urgency_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            first_urg = urgency_order[plan.actions[0].urgency.value]
            last_urg = urgency_order[plan.actions[-1].urgency.value]
            assert first_urg >= last_urg

    def test_regime_in_plan(self):
        health = {"positions": [], "small_cap_allocation": None}
        regime = _regime("bear")
        plan = generate_adjustment_plan(health, regime)
        assert plan.regime.regime == "bear"
        assert "bear" in plan.summary

    def test_optional_inputs_none(self):
        health = {
            "positions": [_pos()],
            "small_cap_allocation": None,
        }
        plan = generate_adjustment_plan(
            health, _regime(),
            concentration=None,
            stress_result=None,
            correlation_pairs=None,
            var_result=None,
        )
        # No crash — P9/P10 and F5-F7 should not fire
        optional_rules = {"P9", "P10", "F5", "F6", "F7"}
        for a in plan.actions:
            assert not (set(a.rule_ids) & optional_rules)

    def test_with_portfolio_rules(self):
        health = {
            "positions": [_pos()],
            "small_cap_allocation": {"level": "critical", "weight": 0.40},
        }
        plan = generate_adjustment_plan(
            health, _regime(),
            concentration={"sector_hhi": 0.55},
        )
        rule_ids = set()
        for a in plan.actions:
            rule_ids.update(a.rule_ids)
        assert "F1" in rule_ids
        assert "F3" in rule_ids

    def test_crash_regime_escalation(self):
        health = {
            "positions": [_pos(quality_label="複数悪化")],
            "small_cap_allocation": None,
        }
        plan = generate_adjustment_plan(health, _regime("crash"))
        p7s = [a for a in plan.actions if "P7" in a.rule_ids]
        # P7 without alert is FLAG MEDIUM → crash escalates to HIGH
        assert len(p7s) >= 1
        assert p7s[0].urgency == Urgency.HIGH
