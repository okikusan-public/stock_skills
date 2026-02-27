"""Markdown formatter for adjustment plans (KIK-496)."""

from __future__ import annotations

from src.core.portfolio.adjustment_advisor import (
    AdjustmentPlan,
    Action,
    Urgency,
)


_URGENCY_EMOJI = {
    Urgency.HIGH: "\U0001f6a8",   # red rotating light
    Urgency.MEDIUM: "\u26a0\ufe0f",  # warning sign
    Urgency.LOW: "\u2139\ufe0f",   # info
}

_URGENCY_LABEL = {
    Urgency.HIGH: "HIGH",
    Urgency.MEDIUM: "MEDIUM",
    Urgency.LOW: "LOW",
}


def format_adjustment_plan(plan: AdjustmentPlan) -> str:
    """Format an adjustment plan as Markdown.

    Parameters
    ----------
    plan : AdjustmentPlan
        Plan from ``generate_adjustment_plan()``.

    Returns
    -------
    str
        Markdown-formatted report.
    """
    lines: list[str] = []
    lines.append("## Portfolio Adjustment Plan\n")

    # Regime info
    regime = plan.regime
    regime_parts = [f"**{regime.regime.upper()}**"]
    if regime.sma50_above_200:
        regime_parts.append("SMA50 > SMA200")
    else:
        regime_parts.append("SMA50 < SMA200")
    if regime.rsi is not None:
        regime_parts.append(f"RSI {regime.rsi}")
    if regime.drawdown is not None:
        regime_parts.append(f"DD {regime.drawdown*100:.1f}%")
    lines.append(f"Market Regime: {', '.join(regime_parts)}\n")

    if not plan.actions:
        lines.append("**調整不要** — 全ポジション健全です。\n")
        return "\n".join(lines)

    # Group by urgency
    by_urgency: dict[Urgency, list[Action]] = {
        Urgency.HIGH: [],
        Urgency.MEDIUM: [],
        Urgency.LOW: [],
    }
    for a in plan.actions:
        by_urgency[a.urgency].append(a)

    for urg in (Urgency.HIGH, Urgency.MEDIUM, Urgency.LOW):
        group = by_urgency[urg]
        if not group:
            continue

        emoji = _URGENCY_EMOJI[urg]
        label = _URGENCY_LABEL[urg]
        lines.append(f"### {emoji} {label} Priority\n")
        lines.append("| Action | Target | Reasons | Rules |")
        lines.append("|:-------|:-------|:--------|:------|")

        for a in group:
            action_str = a.type.value
            reasons_str = "; ".join(a.reasons)
            rules_str = ", ".join(a.rule_ids)
            lines.append(f"| {action_str} | {a.target} | {reasons_str} | {rules_str} |")

        lines.append("")

    # Summary
    lines.append("---")
    lines.append(f"**Summary:** {plan.summary}")

    return "\n".join(lines)
