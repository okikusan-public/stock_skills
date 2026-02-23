"""Simulation and what-if output formatters (KIK-447, split from portfolio_formatter.py)."""

from src.output._format_helpers import fmt_pct_sign as _fmt_pct_sign
from src.output._format_helpers import fmt_float as _fmt_float
from src.output._portfolio_utils import _fmt_jpy, _fmt_currency_value, _fmt_k


_JUDGMENT_EMOJI = {
    "recommend": "\u2705",       # ✅
    "caution": "\u26a0\ufe0f",   # ⚠️
    "not_recommended": "\U0001f6a8",  # 🚨
}

_JUDGMENT_LABEL = {
    "recommend": "この追加は推奨",
    "caution": "注意して検討",
    "not_recommended": "この追加は非推奨",
}

_JUDGMENT_LABEL_SWAP = {
    "recommend": "このスワップは推奨",
    "caution": "注意して検討",
    "not_recommended": "このスワップは非推奨",
}


def format_simulation(result) -> str:
    """Format compound interest simulation results as Markdown.

    Parameters
    ----------
    result : SimulationResult or dict
        Output from simulator.simulate_portfolio().

    Returns
    -------
    str
        Markdown-formatted simulation report.
    """
    # Support both SimulationResult and dict
    if hasattr(result, "to_dict"):
        d = result.to_dict()
    else:
        d = result

    scenarios = d.get("scenarios", {})
    years = d.get("years", 0)
    monthly_add = d.get("monthly_add", 0.0)
    reinvest_dividends = d.get("reinvest_dividends", True)
    target = d.get("target")

    lines: list[str] = []

    # Empty scenarios
    if not scenarios:
        lines.append("## \u8907\u5229\u30b7\u30df\u30e5\u30ec\u30fc\u30b7\u30e7\u30f3")
        lines.append("")
        lines.append(
            "\u63a8\u5b9a\u30ea\u30bf\u30fc\u30f3\u304c\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002"
            "\u5148\u306b /stock-portfolio forecast \u3092\u5b9f\u884c\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
        )
        return "\n".join(lines)

    # Header
    if monthly_add > 0:
        add_str = f"\u6708{monthly_add:,.0f}\u5186\u7a4d\u7acb"
    else:
        add_str = "\u7a4d\u7acb\u306a\u3057"
    lines.append(f"## {years}\u5e74\u30b7\u30df\u30e5\u30ec\u30fc\u30b7\u30e7\u30f3\uff08{add_str}\uff09")
    lines.append("")

    # Base scenario table
    base_snapshots = scenarios.get("base", [])
    if base_snapshots:
        base_return = d.get("portfolio_return_base")
        if base_return is not None:
            ret_str = f"{base_return * 100:+.2f}%"
        else:
            ret_str = "-"
        lines.append(f"### \u30d9\u30fc\u30b9\u30b7\u30ca\u30ea\u30aa\uff08\u5e74\u5229 {ret_str}\uff09")
        lines.append("")
        lines.append("| \u5e74 | \u8a55\u4fa1\u984d | \u7d2f\u8a08\u6295\u5165 | \u904b\u7528\u76ca | \u914d\u5f53\u7d2f\u8a08 |")
        lines.append("|----|--------|----------|--------|----------|")

        for snap in base_snapshots:
            yr = snap.get("year", 0) if isinstance(snap, dict) else snap.year
            value = snap.get("value", 0) if isinstance(snap, dict) else snap.value
            cum_input = snap.get("cumulative_input", 0) if isinstance(snap, dict) else snap.cumulative_input
            cap_gain = snap.get("capital_gain", 0) if isinstance(snap, dict) else snap.capital_gain
            cum_div = snap.get("cumulative_dividends", 0) if isinstance(snap, dict) else snap.cumulative_dividends

            if yr == 0:
                lines.append(
                    f"| {yr} | {_fmt_k(value)} | {_fmt_k(cum_input)} | - | - |"
                )
            else:
                lines.append(
                    f"| {yr} | {_fmt_k(value)} | {_fmt_k(cum_input)} "
                    f"| {_fmt_k(cap_gain)} | {_fmt_k(cum_div)} |"
                )

        lines.append("")

    # Scenario comparison (final year)
    scenario_labels = {
        "optimistic": "\u697d\u89b3",
        "base": "\u30d9\u30fc\u30b9",
        "pessimistic": "\u60b2\u89b3",
    }

    has_comparison = len(scenarios) > 1 or (len(scenarios) == 1 and "base" in scenarios)
    if has_comparison:
        lines.append(
            "### \u30b7\u30ca\u30ea\u30aa\u6bd4\u8f03\uff08\u6700\u7d42\u5e74\uff09"
        )
        lines.append("")
        lines.append("| \u30b7\u30ca\u30ea\u30aa | \u6700\u7d42\u8a55\u4fa1\u984d | \u904b\u7528\u76ca |")
        lines.append("|:---------|----------:|-------:|")

        for key in ["optimistic", "base", "pessimistic"]:
            snaps = scenarios.get(key)
            if not snaps:
                continue
            last = snaps[-1]
            value = last.get("value", 0) if isinstance(last, dict) else last.value
            cap_gain = last.get("capital_gain", 0) if isinstance(last, dict) else last.capital_gain
            label = scenario_labels.get(key, key)
            lines.append(
                f"| {label} | {_fmt_k(value)} | {_fmt_k(cap_gain)} |"
            )

        lines.append("")

    # Target analysis
    if target is not None:
        lines.append("### \u76ee\u6a19\u9054\u6210\u5206\u6790")
        lines.append("")
        lines.append(f"- \u76ee\u6a19\u984d: {_fmt_k(target)}")

        target_year_base = d.get("target_year_base")
        target_year_opt = d.get("target_year_optimistic")
        target_year_pess = d.get("target_year_pessimistic")

        if target_year_base is not None:
            lines.append(
                f"- \u30d9\u30fc\u30b9\u30b7\u30ca\u30ea\u30aa: "
                f"**{target_year_base:.1f}\u5e74\u3067\u9054\u6210\u898b\u8fbc\u307f**"
            )
        else:
            lines.append(
                "- \u30d9\u30fc\u30b9\u30b7\u30ca\u30ea\u30aa: \u671f\u9593\u5185\u672a\u9054"
            )

        if target_year_opt is not None:
            lines.append(
                f"- \u697d\u89b3\u30b7\u30ca\u30ea\u30aa: "
                f"{target_year_opt:.1f}\u5e74\u3067\u9054\u6210\u898b\u8fbc\u307f"
            )
        elif "optimistic" in scenarios:
            lines.append(
                "- \u697d\u89b3\u30b7\u30ca\u30ea\u30aa: \u671f\u9593\u5185\u672a\u9054"
            )

        if target_year_pess is not None:
            lines.append(
                f"- \u60b2\u89b3\u30b7\u30ca\u30ea\u30aa: "
                f"{target_year_pess:.1f}\u5e74\u3067\u9054\u6210\u898b\u8fbc\u307f"
            )
        elif "pessimistic" in scenarios:
            lines.append(
                "- \u60b2\u89b3\u30b7\u30ca\u30ea\u30aa: \u671f\u9593\u5185\u672a\u9054"
            )

        required_monthly = d.get("required_monthly")
        if required_monthly is not None and required_monthly > 0:
            lines.append("")
            lines.append(
                f"- \u76ee\u6a19\u9054\u6210\u306b\u5fc5\u8981\u306a\u6708\u984d\u7a4d\u7acb: "
                f"\u00a5{required_monthly:,.0f}"
            )

        lines.append("")

    # Dividend reinvestment effect
    dividend_effect = d.get("dividend_effect", 0)
    dividend_effect_pct = d.get("dividend_effect_pct", 0)

    lines.append(
        "### \u914d\u5f53\u518d\u6295\u8cc7\u306e\u52b9\u679c"
    )
    lines.append("")

    if not reinvest_dividends:
        lines.append("- \u914d\u5f53\u518d\u6295\u8cc7: OFF")
    else:
        lines.append(
            f"- \u914d\u5f53\u518d\u6295\u8cc7\u306b\u3088\u308b\u8907\u5229\u52b9\u679c: "
            f"+{_fmt_k(dividend_effect)}"
        )
        lines.append(
            f"- \u914d\u5f53\u306a\u3057\u6bd4: "
            f"+{dividend_effect_pct * 100:.1f}%"
        )

    lines.append("")

    return "\n".join(lines)


def _fmt_health_section(health_list: list[dict], title: str) -> list[str]:
    """Format a health check section (shared by proposed and removed stocks)."""
    lines: list[str] = [f"### {title}", ""]
    for ph in health_list:
        symbol = ph.get("symbol", "-")
        alert = ph.get("alert", {})
        level = alert.get("level", "none")
        label = alert.get("label", "なし")
        if level == "none":
            lines.append(f"✅ {symbol}: OK")
        elif level == "early_warning":
            lines.append(f"⚡ {symbol}: {label}")
        elif level == "caution":
            lines.append(f"⚠️ {symbol}: {label}")
        elif level == "exit":
            lines.append(f"🚨 {symbol}: {label}")
        # KIK-469 Phase 2: ETF info
        etf_h = ph.get("change_quality", {}).get("etf_health")
        if etf_h:
            exp = etf_h.get("expense_label", "-")
            aum = etf_h.get("aum_label", "-")
            score = etf_h.get("score", "-")
            lines.append(f"  ETF: \u7d4c\u8cbb\u7387 {exp} / AUM {aum} / \u30b9\u30b3\u30a2 {score}/100")
            for etf_alert in etf_h.get("alerts", []):
                lines.append(f"  \u26a0\ufe0f {etf_alert}")
    lines.append("")
    return lines


def format_what_if(result: dict) -> str:
    """Format What-If simulation result as Markdown.

    Parameters
    ----------
    result : dict
        Output from portfolio_simulation.run_what_if_simulation().
        KIK-451: Supports optional swap fields: removals, removed_health,
        proceeds_jpy, net_cash_jpy.

    Returns
    -------
    str
        Markdown-formatted What-If report.
    """
    lines: list[str] = []

    proposed = result.get("proposed", [])
    removals = result.get("removals", [])    # KIK-451
    before = result.get("before", {})
    after = result.get("after", {})
    proposed_health = result.get("proposed_health", [])
    removed_health = result.get("removed_health", [])    # KIK-451
    required_cash = result.get("required_cash_jpy", 0)
    proceeds = result.get("proceeds_jpy")    # KIK-451 (None when not a swap)
    net_cash = result.get("net_cash_jpy")    # KIK-451
    judgment = result.get("judgment", {})

    is_swap = bool(removals)

    lines.append("## What-If シミュレーション")
    lines.append("")

    # --- (KIK-451) Removed stocks table ---
    if removals:
        lines.append("### 売却銘柄")
        lines.append("")
        lines.append("| 銘柄 | 株数 | 売却代金（試算） |")
        lines.append("|:-----|-----:|----------------:|")
        for rem in removals:
            symbol = rem.get("symbol", "-")
            shares = rem.get("shares", 0)
            rem_proceeds = rem.get("proceeds_jpy", 0.0)
            lines.append(
                f"| {symbol} | {shares:,} | {_fmt_jpy(rem_proceeds)} |"
            )
        lines.append("")
        lines.append(f"売却代金合計: {_fmt_jpy(proceeds or 0.0)}")
        lines.append("")

    # --- Proposed stocks ---
    if proposed:
        lines.append("### 追加銘柄")
        lines.append("")
        lines.append("| 銘柄 | 株数 | 単価 | 通貨 | 金額 |")
        lines.append("|:-----|-----:|------:|:-----|------:|")

        for prop in proposed:
            symbol = prop.get("symbol", "-")
            shares = prop.get("shares", 0)
            price = prop.get("cost_price", 0)
            currency = prop.get("cost_currency", "JPY")
            amount = shares * price
            price_str = _fmt_currency_value(price, currency)
            amount_str = _fmt_currency_value(amount, currency)
            lines.append(
                f"| {symbol} | {shares:,} | {price_str} "
                f"| {currency} | {amount_str} |"
            )

        lines.append("")
        lines.append(f"必要資金合計: {_fmt_jpy(required_cash)}")
        lines.append("")

    # --- (KIK-451) Cash balance for swap mode ---
    if is_swap:
        lines.append("### 資金収支")
        lines.append("")
        lines.append("| 項目 | 金額 |")
        lines.append("|:-----|-----:|")
        if proposed:
            lines.append(f"| 購入必要資金 | {_fmt_jpy(required_cash)} |")
        lines.append(f"| 売却代金（試算） | {_fmt_jpy(proceeds or 0.0)} |")
        if net_cash is not None and proposed:
            suffix = "（余剰資金）" if net_cash >= 0 else "（追加資金が必要）"
            lines.append(f"| 差額 | {_fmt_jpy(net_cash)}{suffix} |")
        lines.append("")

    # --- Portfolio change comparison ---
    after_label = "スワップ後" if is_swap else "追加後"
    lines.append("### ポートフォリオ変化")
    lines.append("")
    lines.append(f"| 指標 | 現在 | {after_label} | 変化 |")
    lines.append("|:-----|------:|------:|:------|")

    # Total value
    bv = before.get("total_value_jpy", 0)
    av = after.get("total_value_jpy", 0)
    if bv > 0:
        change_pct = (av - bv) / bv
        change_str = _fmt_pct_sign(change_pct)
    else:
        change_str = "-"
    lines.append(
        f"| 総評価額 | {_fmt_jpy(bv)} | {_fmt_jpy(av)} | {change_str} |"
    )

    # Sector HHI
    b_shhi = before.get("sector_hhi", 0)
    a_shhi = after.get("sector_hhi", 0)
    hhi_indicator = (
        "✅ 改善" if a_shhi < b_shhi
        else "⚠️ 悪化" if a_shhi > b_shhi
        else "↔️ 変化なし"
    )
    lines.append(
        f"| セクターHHI | {_fmt_float(b_shhi, 2)} "
        f"| {_fmt_float(a_shhi, 2)} | {hhi_indicator} |"
    )

    # Region HHI
    b_rhhi = before.get("region_hhi", 0)
    a_rhhi = after.get("region_hhi", 0)
    rhhi_indicator = (
        "✅ 改善" if a_rhhi < b_rhhi
        else "⚠️ 悪化" if a_rhhi > b_rhhi
        else "↔️ 変化なし"
    )
    lines.append(
        f"| 地域HHI | {_fmt_float(b_rhhi, 2)} "
        f"| {_fmt_float(a_rhhi, 2)} | {rhhi_indicator} |"
    )

    # Forecast base return
    b_ret = before.get("forecast_base")
    a_ret = after.get("forecast_base")
    if b_ret is not None and a_ret is not None:
        diff_pp = (a_ret - b_ret) * 100
        ret_indicator = (
            f"✅ +{diff_pp:.1f}pp" if diff_pp > 0
            else f"⚠️ {diff_pp:.1f}pp" if diff_pp < 0
            else "↔️ 0pp"
        )
        lines.append(
            f"| 期待リターン(ベース) "
            f"| {_fmt_pct_sign(b_ret)} "
            f"| {_fmt_pct_sign(a_ret)} | {ret_indicator} |"
        )
    lines.append("")

    # --- Proposed stock health ---
    if proposed_health:
        lines += _fmt_health_section(proposed_health, "提案銘柄ヘルスチェック")

    # --- (KIK-451) Removed stock health ---
    if removed_health:
        lines += _fmt_health_section(removed_health, "売却銘柄ヘルスチェック")

    # --- Judgment ---
    lines.append("### 総合判定")
    lines.append("")
    rec = judgment.get("recommendation", "caution")
    emoji = _JUDGMENT_EMOJI.get(rec, "")
    if is_swap and proposed:
        label = _JUDGMENT_LABEL_SWAP.get(rec, rec)
    else:
        label = _JUDGMENT_LABEL.get(rec, rec)
    lines.append(f"{emoji} **{label}**")
    for reason in judgment.get("reasons", []):
        lines.append(f"- {reason}")
    lines.append("")

    return "\n".join(lines)
