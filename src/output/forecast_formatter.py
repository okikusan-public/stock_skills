"""Forecast / return-estimate output formatter (KIK-447, split from portfolio_formatter.py)."""

from src.output._format_helpers import fmt_pct as _fmt_pct
from src.output._format_helpers import fmt_pct_sign as _fmt_pct_sign
from src.output._portfolio_utils import _fmt_jpy, _fmt_currency_value


def format_return_estimate(estimate: dict) -> str:
    """Format portfolio return estimation as a Markdown report.

    Parameters
    ----------
    estimate : dict
        Output from return_estimate.estimate_portfolio_return().
        Expected keys:
        - "positions": list[dict] with per-stock estimates
        - "portfolio": {"optimistic": float, "base": float, "pessimistic": float}
        - "total_value_jpy": float
        - "fx_rates": dict

    Returns
    -------
    str
        Markdown-formatted return estimation report.
    """
    lines: list[str] = []

    portfolio = estimate.get("portfolio", {})
    positions = estimate.get("positions", [])
    total_value = estimate.get("total_value_jpy", 0)

    if not positions:
        lines.append("## \u63a8\u5b9a\u5229\u56de\u308a\uff0812\u30f6\u6708\uff09")
        lines.append("")
        lines.append("\u4fdd\u6709\u9298\u67c4\u304c\u3042\u308a\u307e\u305b\u3093\u3002")
        return "\n".join(lines)

    # --- Compact summary (KIK-442) ---
    ranked_all = [
        p for p in positions
        if p.get("base") is not None and p.get("method") != "no_data"
    ]
    ranked_all.sort(key=lambda p: p["base"], reverse=True)

    opt_ret = portfolio.get("optimistic")
    base_ret_pf = portfolio.get("base")
    pess_ret = portfolio.get("pessimistic")

    opt_str = _fmt_pct_sign(opt_ret) if opt_ret is not None else "-"
    base_str_pf = _fmt_pct_sign(base_ret_pf) if base_ret_pf is not None else "-"
    pess_str = _fmt_pct_sign(pess_ret) if pess_ret is not None else "-"

    lines.append("## \U0001f4c8 \u30d5\u30a9\u30fc\u30ad\u30e3\u30b9\u30c8 \u30b5\u30de\u30ea\u30fc\uff0812\u30f6\u6708\uff09")
    lines.append("")
    lines.append(
        f"  \u697d\u89b3: {opt_str}  "
        f"\u30d9\u30fc\u30b9: {base_str_pf}  "
        f"\u60b2\u89b3: {pess_str}"
    )
    lines.append(f"  \u7dcf\u8a55\u4fa1\u984d: {_fmt_jpy(total_value)}")
    lines.append("")

    if len(ranked_all) >= 2:
        top3 = ranked_all[:3]
        top3_str = " / ".join(
            f"{p['symbol']} {_fmt_pct_sign(p['base'])}" for p in top3
        )
        lines.append(f"  \u671f\u5f85\u30ea\u30bf\u30fc\u30f3 TOP3:  {top3_str}")

        top_symbols_set = {p["symbol"] for p in top3}
        btm_candidates = [p for p in ranked_all[-3:] if p["symbol"] not in top_symbols_set]
        if btm_candidates:
            btm_str = " / ".join(
                f"{p['symbol']} {_fmt_pct_sign(p['base'])}" for p in btm_candidates
            )
            lines.append(f"  \u671f\u5f85\u30ea\u30bf\u30fc\u30f3 BTM3:  {btm_str}")

    lines.append("")
    lines.append("\u2500\u2500\u2500 \u9298\u67c4\u5225\u8a73\u7d30 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    lines.append("")

    # --- Portfolio summary ---
    lines.append("## \u63a8\u5b9a\u5229\u56de\u308a\uff0812\u30f6\u6708\uff09")
    lines.append("")

    lines.append("| \u30b7\u30ca\u30ea\u30aa | \u5229\u56de\u308a | \u640d\u76ca\u984d |")
    lines.append("|:---------|------:|------:|")

    for label, key in [
        ("\u697d\u89b3", "optimistic"),
        ("\u30d9\u30fc\u30b9", "base"),
        ("\u60b2\u89b3", "pessimistic"),
    ]:
        ret = portfolio.get(key)
        if ret is not None:
            pnl_amount = ret * total_value if total_value else 0
            lines.append(
                f"| {label} | {_fmt_pct_sign(ret)} | {_fmt_jpy(pnl_amount)} |"
            )
        else:
            lines.append(f"| {label} | - | - |")

    lines.append("")
    lines.append(f"\u7dcf\u8a55\u4fa1\u984d: {_fmt_jpy(total_value)}")
    lines.append("")

    # --- Warning summary (KIK-390) ---
    warnings = [
        p for p in positions if p.get("value_trap_warning")
    ]
    if warnings:
        lines.append("### \u26a0\ufe0f \u6ce8\u610f\u9298\u67c4")
        lines.append("")
        for w in warnings:
            lines.append(f"- **{w['symbol']}**: {w['value_trap_warning']}")
        lines.append("")

    # --- TOP 3 / BOTTOM 3 (KIK-390) ---
    ranked = [
        p for p in positions
        if p.get("base") is not None and p.get("method") != "no_data"
    ]
    ranked.sort(key=lambda p: p["base"], reverse=True)

    if len(ranked) >= 2:
        top_n = ranked[:3]
        bottom_n = ranked[-3:] if len(ranked) >= 6 else ranked[-min(3, len(ranked)):]
        # Deduplicate if overlap (small portfolios)
        top_symbols = {p["symbol"] for p in top_n}

        lines.append("### \U0001f51d \u671f\u5f85\u30ea\u30bf\u30fc\u30f3 TOP")
        lines.append("")
        for i, p in enumerate(top_n, 1):
            count = p.get("analyst_count")
            count_str = f" ({count}\u540d)" if count else ""
            lines.append(
                f"{i}. **{p['symbol']}** {_fmt_pct_sign(p['base'])}{count_str}"
            )
        lines.append("")

        # Only show BOTTOM if there are stocks not already in TOP
        bottom_only = [p for p in bottom_n if p["symbol"] not in top_symbols]
        if bottom_only:
            lines.append("### \U0001f4c9 \u671f\u5f85\u30ea\u30bf\u30fc\u30f3 BOTTOM")
            lines.append("")
            for i, p in enumerate(bottom_only, 1):
                count = p.get("analyst_count")
                count_str = f" ({count}\u540d)" if count else ""
                lines.append(
                    f"{i}. **{p['symbol']}** {_fmt_pct_sign(p['base'])}{count_str}"
                )
            lines.append("")

    # --- Per-stock details ---
    for pos in positions:
        symbol = pos.get("symbol", "-")
        base_ret = pos.get("base")
        method = pos.get("method", "")
        currency = pos.get("currency", "USD")

        # Header
        base_str = _fmt_pct_sign(base_ret) if base_ret is not None else "-"
        etf_badge = " [ETF]" if pos.get("is_etf") else ""  # KIK-469 P2
        lines.append(f"### {symbol}{etf_badge} \u671f\u5f85\u30ea\u30bf\u30fc\u30f3: {base_str}\uff08\u30d9\u30fc\u30b9\uff09")
        lines.append("")

        # Quantitative section
        if method == "no_data":
            lines.append("\u3010\u5b9a\u91cf\u3011\u30c7\u30fc\u30bf\u53d6\u5f97\u5931\u6557")
            lines.append("  \u2192 \u60b2\u89b3 - / \u30d9\u30fc\u30b9 - / \u697d\u89b3 -")
        elif method == "analyst":
            target_mean = pos.get("target_mean")
            analyst_count = pos.get("analyst_count")
            forward_per = pos.get("forward_per")

            target_str = _fmt_currency_value(target_mean, currency) if target_mean else "-"
            count_str = f"{analyst_count}\u540d" if analyst_count else "-"
            fpe_str = f"{forward_per:.1f}x" if forward_per else "-"
            confidence = "\u53c2\u8003\u5024" if (analyst_count or 0) < 5 else ""
            confidence_suffix = f" \u203b{confidence}" if confidence else ""

            lines.append(
                f"\u3010\u5b9a\u91cf\u3011\u30a2\u30ca\u30ea\u30b9\u30c8\u76ee\u6a19 {target_str}"
                f"\uff08{count_str}\uff09"
                f"\u3001Forward PER {fpe_str}"
                f"{confidence_suffix}"
            )
        else:
            data_months = pos.get("data_months", 0)
            lines.append(
                f"\u3010\u5b9a\u91cf\u3011\u904e\u53bb\u30ea\u30bf\u30fc\u30f3\u5206\u5e03"
                f"\uff08{data_months}\u30f6\u6708\u5206\uff09"
            )
            # KIK-469 Phase 2: ETF volatility display
            vol = pos.get("annualized_volatility")
            if vol is not None:
                lines.append(f"  \u5e74\u7387\u30dc\u30e9\u30c6\u30a3\u30ea\u30c6\u30a3: {vol * 100:.1f}%")

        # News and sentiment sections (skip for no_data)
        if method != "no_data":
            # News section - count only (KIK-390)
            news = pos.get("news", [])
            if news:
                lines.append(f"\u3010\u30cb\u30e5\u30fc\u30b9\u3011{len(news)}\u4ef6")

            # X Sentiment section
            x_sentiment = pos.get("x_sentiment")
            if x_sentiment and (x_sentiment.get("positive") or x_sentiment.get("negative")):
                lines.append("\u3010X \u30bb\u30f3\u30c1\u30e1\u30f3\u30c8\u3011")
                for factor in (x_sentiment.get("positive") or [])[:3]:
                    lines.append(f"  \u25b2 {factor}")
                for factor in (x_sentiment.get("negative") or [])[:3]:
                    lines.append(f"  \u25bc {factor}")

            # 3-scenario summary
            opt = pos.get("optimistic")
            base_r = pos.get("base")
            pess = pos.get("pessimistic")
            if opt is not None and base_r is not None and pess is not None:
                lines.append(
                    f"  \u2192 \u60b2\u89b3 {_fmt_pct_sign(pess)} / "
                    f"\u30d9\u30fc\u30b9 {_fmt_pct_sign(base_r)} / "
                    f"\u697d\u89b3 {_fmt_pct_sign(opt)}"
                )

            # Value trap warning (KIK-385)
            vt_warning = pos.get("value_trap_warning")
            if vt_warning:
                lines.append(f"  \U0001fa64 **\u30d0\u30ea\u30e5\u30fc\u30c8\u30e9\u30c3\u30d7\u5146\u5019**: {vt_warning}")

        lines.append("")

    return "\n".join(lines)
