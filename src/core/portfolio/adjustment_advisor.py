"""Portfolio adjustment advisor — rule-based action engine (KIK-496).

Bridges diagnosis (health_check) with prescription (concrete actions).
17 rules:
  P1-P10: Position-level rules
  F1-F7:  Portfolio-level rules

Actions are typed (SELL/SWAP/ADD/TRIM_CLASS/FLAG), urgency-classified
(HIGH/MEDIUM/LOW), and optionally carry screening hints for candidate
selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.core.portfolio.market_regime import MarketRegime


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------

class ActionType(Enum):
    SELL = "SELL"
    SWAP = "SWAP"
    ADD = "ADD"
    TRIM_CLASS = "TRIM_CLASS"
    FLAG = "FLAG"


# Priority order: higher index = higher priority
_ACTION_PRIORITY = {
    ActionType.FLAG: 0,
    ActionType.ADD: 1,
    ActionType.TRIM_CLASS: 2,
    ActionType.SWAP: 3,
    ActionType.SELL: 4,
}


class Urgency(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


_URGENCY_ORDER = {Urgency.LOW: 0, Urgency.MEDIUM: 1, Urgency.HIGH: 2}


@dataclass
class Action:
    type: ActionType
    target: str  # symbol or class name (e.g. "small_cap")
    urgency: Urgency
    reasons: list[str]
    rule_ids: list[str]
    screening_hint: str = ""
    screening_filter: dict = field(default_factory=dict)


@dataclass
class AdjustmentPlan:
    regime: MarketRegime
    actions: list[Action]
    candidates: dict  # target -> screening results (populated externally)
    summary: str


# ---------------------------------------------------------------------------
# Position rules (P1 – P10)
# ---------------------------------------------------------------------------

def evaluate_position_rules(
    positions: list[dict],
    regime: MarketRegime,
    correlation_pairs: list | None = None,
    var_result: dict | None = None,
) -> list[Action]:
    """Apply P1-P10 rules to each position.

    Parameters
    ----------
    positions : list[dict]
        ``health_check.run_health_check()["positions"]``.
    regime : MarketRegime
        Current market regime.
    correlation_pairs : list, optional
        High-correlation pairs from recommender (for P9).
    var_result : dict, optional
        VaR analysis result (for P10).
    """
    actions: list[Action] = []

    for pos in positions:
        symbol = pos.get("symbol", "")
        alert_level = pos.get("alert", {}).get("level", "none")
        is_trap = pos.get("value_trap", {}).get("is_trap", False)
        is_small_cap = pos.get("is_small_cap", False)
        trend = pos.get("trend_health", {}).get("trend", "不明")
        cross_signal = pos.get("trend_health", {}).get("cross_signal", "none")
        long_term_label = pos.get("long_term", {}).get("label", "要検討")
        stability = pos.get("return_stability", {}).get("stability", "")
        quality_label = pos.get("change_quality", {}).get("quality_label", "良好")

        # P1: EXIT → SELL (HIGH)
        if alert_level == "exit":
            actions.append(Action(
                type=ActionType.SELL,
                urgency=Urgency.HIGH,
                target=symbol,
                reasons=["EXIT判定"],
                rule_ids=["P1"],
            ))

        # P2: Value trap
        if is_trap:
            if alert_level == "exit":
                actions.append(Action(
                    type=ActionType.SWAP,
                    urgency=Urgency.HIGH,
                    target=symbol,
                    reasons=["バリュートラップ + EXIT判定"],
                    rule_ids=["P2"],
                    screening_hint="同セクター割安株",
                ))
            else:
                actions.append(Action(
                    type=ActionType.FLAG,
                    urgency=Urgency.MEDIUM,
                    target=symbol,
                    reasons=["バリュートラップの疑い"],
                    rule_ids=["P2"],
                ))

        # P3: Small-cap + CAUTION or higher
        if is_small_cap and alert_level in ("caution", "exit"):
            actions.append(Action(
                type=ActionType.SELL,
                urgency=Urgency.MEDIUM,
                target=symbol,
                reasons=[f"小型株 + {alert_level.upper()}判定"],
                rule_ids=["P3"],
            ))

        # P4: Death cross + earnings decline
        eps_status = pos.get("long_term", {}).get("eps_growth_status", "")
        if cross_signal == "death_cross" and eps_status == "declining":
            actions.append(Action(
                type=ActionType.SELL,
                urgency=Urgency.MEDIUM,
                target=symbol,
                reasons=["デッドクロス + EPS減少"],
                rule_ids=["P4"],
            ))

        # P5: Short-term suitability held > 90 days
        if long_term_label == "短期向き":
            actions.append(Action(
                type=ActionType.FLAG,
                urgency=Urgency.LOW,
                target=symbol,
                reasons=["短期向き銘柄（長期保有に不向き）"],
                rule_ids=["P5"],
            ))

        # P6: Return stability declining/temporary
        if stability in ("decreasing", "temporary"):
            if alert_level == "exit":
                actions.append(Action(
                    type=ActionType.SWAP,
                    urgency=Urgency.MEDIUM,
                    target=symbol,
                    reasons=[f"還元安定度「{stability}」+ EXIT判定"],
                    rule_ids=["P6"],
                    screening_hint="高還元安定株",
                ))
            else:
                actions.append(Action(
                    type=ActionType.FLAG,
                    urgency=Urgency.LOW,
                    target=symbol,
                    reasons=[f"還元安定度「{stability}」"],
                    rule_ids=["P6"],
                ))

        # P7: Quality "複数悪化"
        if quality_label == "複数悪化":
            if alert_level in ("caution", "exit"):
                actions.append(Action(
                    type=ActionType.SELL,
                    urgency=Urgency.MEDIUM,
                    target=symbol,
                    reasons=[f"変化の質「複数悪化」+ {alert_level.upper()}"],
                    rule_ids=["P7"],
                ))
            else:
                actions.append(Action(
                    type=ActionType.FLAG,
                    urgency=Urgency.MEDIUM,
                    target=symbol,
                    reasons=["変化の質「複数悪化」"],
                    rule_ids=["P7"],
                ))

        # P8: Downtrend + EARLY_WARNING or higher
        if trend == "下降" and alert_level in ("early_warning", "caution", "exit"):
            actions.append(Action(
                type=ActionType.FLAG,
                urgency=Urgency.MEDIUM,
                target=symbol,
                reasons=[f"下降トレンド + {alert_level.upper()}"],
                rule_ids=["P8"],
            ))

    # P9: High correlation pairs (optional)
    if correlation_pairs:
        for pair in correlation_pairs:
            corr = pair.get("correlation", 0)
            if corr > 0.85:
                sym_a = pair.get("symbol_a", "")
                sym_b = pair.get("symbol_b", "")
                # Identify weaker stock by alert level
                pos_a = _find_position(positions, sym_a)
                pos_b = _find_position(positions, sym_b)
                weaker = _pick_weaker(pos_a, pos_b)
                if weaker:
                    actions.append(Action(
                        type=ActionType.FLAG,
                        urgency=Urgency.LOW,
                        target=weaker,
                        reasons=[f"高相関ペア（{sym_a}/{sym_b} r={corr:.2f}）"],
                        rule_ids=["P9"],
                    ))

    # P10: VaR contribution (optional)
    if var_result and var_result.get("var_95") is not None:
        var_95 = var_result.get("var_95", 0)
        if var_95 < -0.15:
            # Flag top contributors if available
            contributions = var_result.get("contributions", [])
            for contrib in contributions[:3]:
                sym = contrib.get("symbol", "")
                weight = contrib.get("weight", 0)
                if weight > 0.3:
                    actions.append(Action(
                        type=ActionType.FLAG,
                        urgency=Urgency.MEDIUM,
                        target=sym,
                        reasons=[f"VaR寄与大（ウェイト{weight*100:.0f}%、VaR95={var_95*100:.1f}%）"],
                        rule_ids=["P10"],
                    ))

    return actions


def _find_position(positions: list[dict], symbol: str) -> dict | None:
    for pos in positions:
        if pos.get("symbol") == symbol:
            return pos
    return None


_ALERT_SEVERITY = {"none": 0, "early_warning": 1, "caution": 2, "exit": 3}


def _pick_weaker(pos_a: dict | None, pos_b: dict | None) -> str | None:
    """Return the symbol of the weaker position (higher alert)."""
    if pos_a is None and pos_b is None:
        return None
    if pos_a is None:
        return pos_b.get("symbol")
    if pos_b is None:
        return pos_a.get("symbol")
    sev_a = _ALERT_SEVERITY.get(pos_a.get("alert", {}).get("level", "none"), 0)
    sev_b = _ALERT_SEVERITY.get(pos_b.get("alert", {}).get("level", "none"), 0)
    if sev_a >= sev_b:
        return pos_a.get("symbol")
    return pos_b.get("symbol")


# ---------------------------------------------------------------------------
# Portfolio rules (F1 – F7)
# ---------------------------------------------------------------------------

def evaluate_portfolio_rules(
    positions: list[dict],
    small_cap_allocation: dict | None = None,
    concentration: dict | None = None,
    stress_result: dict | None = None,
    correlation_pairs: list | None = None,
    var_result: dict | None = None,
) -> list[Action]:
    """Apply F1-F7 portfolio-level rules.

    Parameters
    ----------
    positions : list[dict]
        Health check positions.
    small_cap_allocation : dict, optional
        From ``check_small_cap_allocation()``.
    concentration : dict, optional
        HHI data from ``analyze_concentration()``.
    stress_result : dict, optional
        Stress test scenario results.
    correlation_pairs : list, optional
        High-correlation pairs.
    var_result : dict, optional
        VaR analysis result.
    """
    actions: list[Action] = []

    # F1/F2: Concentration (HHI)
    if concentration:
        hhi = concentration.get("sector_hhi") or concentration.get("hhi", 0)
        if hhi > 0.50:
            actions.append(Action(
                type=ActionType.TRIM_CLASS,
                urgency=Urgency.HIGH,
                target="concentration",
                reasons=[f"集中度 HHI {hhi:.2f} > 0.50（危険水準）"],
                rule_ids=["F1"],
            ))
        elif hhi > 0.25:
            actions.append(Action(
                type=ActionType.FLAG,
                urgency=Urgency.MEDIUM,
                target="concentration",
                reasons=[f"集中度 HHI {hhi:.2f} > 0.25（やや高い）"],
                rule_ids=["F2"],
            ))

    # F3/F4: Small-cap allocation
    if small_cap_allocation:
        level = small_cap_allocation.get("level", "ok")
        weight = small_cap_allocation.get("weight", 0)
        if level == "critical":
            actions.append(Action(
                type=ActionType.TRIM_CLASS,
                urgency=Urgency.HIGH,
                target="small_cap",
                reasons=[f"小型株比率 {weight*100:.0f}% > 35%（過集中）"],
                rule_ids=["F3"],
            ))
        elif level == "warning":
            actions.append(Action(
                type=ActionType.FLAG,
                urgency=Urgency.MEDIUM,
                target="small_cap",
                reasons=[f"小型株比率 {weight*100:.0f}% > 25%（やや多い）"],
                rule_ids=["F4"],
            ))

    # F5: High correlation (optional)
    if correlation_pairs:
        high_pairs = [p for p in correlation_pairs if p.get("correlation", 0) > 0.85]
        if high_pairs:
            pair_strs = [
                f"{p['symbol_a']}/{p['symbol_b']} r={p['correlation']:.2f}"
                for p in high_pairs[:3]
            ]
            actions.append(Action(
                type=ActionType.FLAG,
                urgency=Urgency.MEDIUM,
                target="correlation",
                reasons=[f"高相関ペア: {', '.join(pair_strs)}"],
                rule_ids=["F5"],
            ))

    # F6: VaR (optional)
    if var_result:
        var_95 = var_result.get("var_95", 0)
        if var_95 is not None and var_95 < -0.15:
            actions.append(Action(
                type=ActionType.FLAG,
                urgency=Urgency.HIGH,
                target="var_risk",
                reasons=[f"VaR(95%) = {var_95*100:.1f}%（深刻な損失リスク）"],
                rule_ids=["F6"],
            ))

    # F7: Stress test (optional)
    if stress_result:
        max_loss = stress_result.get("max_portfolio_loss", 0)
        if max_loss is not None and max_loss < -0.30:
            actions.append(Action(
                type=ActionType.FLAG,
                urgency=Urgency.HIGH,
                target="stress_risk",
                reasons=[f"ストレス最大損失 {max_loss*100:.1f}%（>30%）"],
                rule_ids=["F7"],
            ))

    return actions


# ---------------------------------------------------------------------------
# Urgency regime adjustment
# ---------------------------------------------------------------------------

def adjust_urgency_for_regime(
    actions: list[Action],
    regime: MarketRegime,
) -> list[Action]:
    """Escalate urgency based on market regime.

    - crash: LOW → MEDIUM, MEDIUM → HIGH
    - bear:  small-cap / downtrend rules escalate LOW → MEDIUM
    - bull/neutral: no change
    """
    _BEAR_ESCALATION_RULES = {"P3", "P8"}

    for action in actions:
        if regime.regime == "crash":
            if action.urgency == Urgency.LOW:
                action.urgency = Urgency.MEDIUM
            elif action.urgency == Urgency.MEDIUM:
                action.urgency = Urgency.HIGH
        elif regime.regime == "bear":
            rule_set = set(action.rule_ids)
            if rule_set & _BEAR_ESCALATION_RULES and action.urgency == Urgency.LOW:
                action.urgency = Urgency.MEDIUM

    return actions


# ---------------------------------------------------------------------------
# Action merge
# ---------------------------------------------------------------------------

def merge_actions(actions: list[Action]) -> list[Action]:
    """Merge actions with the same target.

    - Type: highest priority wins (SELL > SWAP > TRIM_CLASS > ADD > FLAG)
    - Urgency: highest wins
    - Reasons & rule_ids: union (deduplicated)
    - screening_hint/filter: from SWAP/ADD preferred
    """
    by_target: dict[str, list[Action]] = {}
    for a in actions:
        by_target.setdefault(a.target, []).append(a)

    merged: list[Action] = []
    for target, group in by_target.items():
        if len(group) == 1:
            merged.append(group[0])
            continue

        best_type = max(group, key=lambda a: _ACTION_PRIORITY[a.type]).type
        best_urgency = max(group, key=lambda a: _URGENCY_ORDER[a.urgency]).urgency

        # Collect unique reasons and rule_ids
        seen_reasons: list[str] = []
        seen_rule_ids: list[str] = []
        for a in group:
            for r in a.reasons:
                if r not in seen_reasons:
                    seen_reasons.append(r)
            for rid in a.rule_ids:
                if rid not in seen_rule_ids:
                    seen_rule_ids.append(rid)

        # Prefer screening info from SWAP/ADD actions
        hint = ""
        filt: dict = {}
        for a in group:
            if a.type in (ActionType.SWAP, ActionType.ADD) and a.screening_hint:
                hint = a.screening_hint
                filt = a.screening_filter
                break
        if not hint:
            for a in group:
                if a.screening_hint:
                    hint = a.screening_hint
                    filt = a.screening_filter
                    break

        merged.append(Action(
            type=best_type,
            target=target,
            urgency=best_urgency,
            reasons=seen_reasons,
            rule_ids=seen_rule_ids,
            screening_hint=hint,
            screening_filter=filt,
        ))

    return merged


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_adjustment_plan(
    health_result: dict,
    regime: MarketRegime,
    concentration: dict | None = None,
    stress_result: dict | None = None,
    correlation_pairs: list | None = None,
    var_result: dict | None = None,
) -> AdjustmentPlan:
    """Generate adjustment plan from health check results.

    Parameters
    ----------
    health_result : dict
        From ``run_health_check()``.
    regime : MarketRegime
        Current market regime.
    concentration : dict, optional
        HHI data (API-heavy, optional).
    stress_result : dict, optional
        Stress test results (API-heavy, optional).
    correlation_pairs : list, optional
        High-correlation pairs (API-heavy, optional).
    var_result : dict, optional
        VaR analysis (API-heavy, optional).

    Returns
    -------
    AdjustmentPlan
    """
    positions = health_result.get("positions", [])
    small_cap_alloc = health_result.get("small_cap_allocation")

    # 1. Position rules
    pos_actions = evaluate_position_rules(
        positions, regime,
        correlation_pairs=correlation_pairs,
        var_result=var_result,
    )

    # 2. Portfolio rules
    pf_actions = evaluate_portfolio_rules(
        positions,
        small_cap_allocation=small_cap_alloc,
        concentration=concentration,
        stress_result=stress_result,
        correlation_pairs=correlation_pairs,
        var_result=var_result,
    )

    all_actions = pos_actions + pf_actions

    # 3. Regime adjustment
    adjust_urgency_for_regime(all_actions, regime)

    # 4. Merge
    merged = merge_actions(all_actions)

    # 5. Sort: urgency DESC → type priority DESC → target ASC
    merged.sort(key=lambda a: (
        -_URGENCY_ORDER[a.urgency],
        -_ACTION_PRIORITY[a.type],
        a.target,
    ))

    # 6. Summary
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for a in merged:
        counts[a.urgency.value] += 1
    summary = (
        f"{counts['HIGH']} HIGH / {counts['MEDIUM']} MEDIUM / {counts['LOW']} LOW "
        f"actions. Regime: {regime.regime}."
    )

    return AdjustmentPlan(
        regime=regime,
        actions=merged,
        candidates={},
        summary=summary,
    )
