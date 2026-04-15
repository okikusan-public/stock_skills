"""Rebalance proposal output formatter (KIK-447, split from portfolio_formatter.py)."""

from src.core.ticker_utils import get_lot_size, round_to_lot_size
from src.output._format_helpers import fmt_pct_sign as _fmt_pct_sign
from src.output._format_helpers import fmt_float as _fmt_float


_ACTION_LABELS = {
    "sell": "売り",
    "reduce": "減らす",
    "increase": "増やす",
}

def _estimate_shares_annotation(
    symbol: str, value_jpy: float, current_price: float | None,
) -> str:
    """Generate a lot-size-aware share estimate annotation.

    Returns empty string for lot_size=1 stocks or when price is unavailable.
    """
    lot = get_lot_size(symbol)
    if lot <= 1 or not current_price or current_price <= 0:
        return ""
    estimated_shares = int(value_jpy / current_price)
    rounded = round_to_lot_size(estimated_shares, symbol)
    if rounded <= 0:
        rounded = lot
    return f"\u2252 {rounded}\u682a\uff08{lot}\u682a\u5358\u4f4d\uff09"


_ACTION_EMOJI = {
    "sell": "\U0001f534",      # red circle
    "reduce": "\U0001f7e1",    # yellow circle
    "increase": "\U0001f7e2",  # green circle
}


def format_rebalance_report(proposal: dict) -> str:
    """Format a rebalance proposal as markdown.

    Parameters
    ----------
    proposal : dict
        Output of rebalancer.generate_rebalance_proposal().

    Returns
    -------
    str
        Markdown-formatted report.
    """
    lines: list[str] = []

    strategy = proposal.get("strategy", "balanced")
    strategy_label = {
        "defensive": "ディフェンシブ",
        "balanced": "バランス",
        "aggressive": "アグレッシブ",
    }.get(strategy, strategy)
    lines.append(f"## リバランス提案 ({strategy_label})")
    lines.append("")

    # --- Before / After ---
    before = proposal.get("before", {})
    after = proposal.get("after", {})

    lines.append("### 現在 → 提案後")
    lines.append("")
    lines.append("| 指標 | 現在 | 提案後 |")
    lines.append("|:-----|-----:|------:|")
    lines.append(
        f"| ベース期待値 | {_fmt_pct_sign(before.get('base_return'))} "
        f"| {_fmt_pct_sign(after.get('base_return'))} |"
    )
    lines.append(
        f"| セクターHHI | {_fmt_float(before.get('sector_hhi'), 4)} "
        f"| {_fmt_float(after.get('sector_hhi'), 4)} |"
    )
    lines.append(
        f"| 地域HHI | {_fmt_float(before.get('region_hhi'), 4)} "
        f"| {_fmt_float(after.get('region_hhi'), 4)} |"
    )
    lines.append("")

    # --- Cash summary ---
    freed = proposal.get("freed_cash_jpy", 0)
    additional = proposal.get("additional_cash_jpy", 0)
    if freed > 0 or additional > 0:
        lines.append("### 資金")
        lines.append("")
        if freed > 0:
            lines.append(f"- **売却・削減による確保資金:** {freed:,.0f}円")
        if additional > 0:
            lines.append(f"- **追加投入資金:** {additional:,.0f}円")
        lines.append(f"- **合計利用可能資金:** {freed + additional:,.0f}円")
        lines.append("")

    # --- Actions ---
    actions = proposal.get("actions", [])
    if not actions:
        lines.append("### アクション")
        lines.append("")
        lines.append("現在のポートフォリオは制約範囲内です。リバランス不要。")
        lines.append("")
        return "\n".join(lines)

    lines.append("### アクション")
    lines.append("")

    for i, action in enumerate(actions, 1):
        act_type = action.get("action", "")
        emoji = _ACTION_EMOJI.get(act_type, "")
        label = _ACTION_LABELS.get(act_type, act_type)
        symbol = action.get("symbol", "")
        name = action.get("name", "")
        name_str = f" {name}" if name else ""
        reason = action.get("reason", "")

        if act_type == "sell":
            value = action.get("value_jpy", 0)
            lines.append(
                f"{i}. {emoji} **{label}**: {symbol}{name_str} 全株"
                f" → {reason}"
            )
            if value > 0:
                lines.append(f"   確保資金: {value:,.0f}円")
        elif act_type == "reduce":
            ratio = action.get("ratio", 0)
            value = action.get("value_jpy", 0)
            lines.append(
                f"{i}. {emoji} **{label}**: {symbol}{name_str}"
                f" {ratio*100:.0f}%削減 → {reason}"
            )
            if value > 0:
                lines.append(f"   確保資金: {value:,.0f}円")
            lot_note = _estimate_shares_annotation(
                symbol, value, action.get("current_price"),
            )
            if lot_note:
                lines.append(f"   {lot_note}")
        elif act_type == "increase":
            amount = action.get("amount_jpy", 0)
            lines.append(
                f"{i}. {emoji} **{label}**: {symbol}{name_str}"
                f" +{amount:,.0f}円 → {reason}"
            )
            lot_note = _estimate_shares_annotation(
                symbol, amount, action.get("current_price"),
            )
            if lot_note:
                lines.append(f"   {lot_note}")

        lines.append("")

    # --- Constraints ---
    constraints = proposal.get("constraints", {})
    if constraints:
        lines.append("### 適用制約")
        lines.append("")
        lines.append(
            f"- 1銘柄上限: {constraints.get('max_single_ratio', 0)*100:.0f}%"
        )
        lines.append(
            f"- セクターHHI上限: {constraints.get('max_sector_hhi', 0):.2f}"
        )
        lines.append(
            f"- 地域HHI上限: {constraints.get('max_region_hhi', 0):.2f}"
        )
        lines.append(
            f"- 相関ペア合計上限:"
            f" {constraints.get('max_corr_pair_ratio', 0)*100:.0f}%"
        )
        lines.append("")

    return "\n".join(lines)
