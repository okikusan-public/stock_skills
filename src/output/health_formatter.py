"""Health check output formatter (KIK-447, split from portfolio_formatter.py)."""

from src.output._format_helpers import fmt_pct_sign as _fmt_pct_sign
from src.output._format_helpers import fmt_float as _fmt_float


def format_health_check(health_data: dict) -> str:
    """Format portfolio health check results as a Markdown report.

    Parameters
    ----------
    health_data : dict
        Output from health_check.run_health_check().

    Returns
    -------
    str
        Markdown-formatted health check report.
    """
    lines: list[str] = []

    positions = health_data.get("positions", [])
    alerts = health_data.get("alerts", [])
    summary = health_data.get("summary", {})

    if not positions:
        lines.append("## \u4fdd\u6709\u9298\u67c4\u30d8\u30eb\u30b9\u30c1\u30a7\u30c3\u30af")
        lines.append("")
        lines.append("\u4fdd\u6709\u9298\u67c4\u304c\u3042\u308a\u307e\u305b\u3093\u3002")
        return "\n".join(lines)

    # --- Compact summary (KIK-442) ---
    total = len(positions)
    exit_syms = [p["symbol"] for p in positions if p.get("alert", {}).get("level") == "exit"]
    caution_syms = [p["symbol"] for p in positions if p.get("alert", {}).get("level") == "caution"]
    early_syms = [p["symbol"] for p in positions if p.get("alert", {}).get("level") == "early_warning"]
    healthy_count = sum(1 for p in positions if p.get("alert", {}).get("level", "none") == "none")

    def _syms_str(syms: list, max_shown: int = 5) -> str:
        if not syms:
            return ""
        shown = syms[:max_shown]
        suffix = " ..." if len(syms) > max_shown else ""
        return "  \u2192 " + ", ".join(shown) + suffix

    lines.append("## \U0001f4ca \u30d8\u30eb\u30b9\u30c1\u30a7\u30c3\u30af \u30b5\u30de\u30ea\u30fc\uff08" + str(total) + "\u9298\u67c4\uff09")
    lines.append("")
    lines.append(f"\U0001f534 \u64a4\u9000\u691c\u8a0e  : {len(exit_syms)}\u9298\u67c4{_syms_str(exit_syms)}")
    lines.append(f"\u26a0\ufe0f  \u6ce8\u610f      : {len(caution_syms)}\u9298\u67c4{_syms_str(caution_syms)}")
    lines.append(f"\u23f0 \u65e9\u671f\u8b66\u544a  : {len(early_syms)}\u9298\u67c4{_syms_str(early_syms)}")
    lines.append(f"\u2705 \u7570\u5e38\u306a\u3057  : {healthy_count}\u9298\u67c4")
    lines.append("")
    lines.append("\u2500\u2500\u2500 \u8a73\u7d30 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    lines.append("")

    lines.append("## \u4fdd\u6709\u9298\u67c4\u30d8\u30eb\u30b9\u30c1\u30a7\u30c3\u30af")
    lines.append("")

    # Summary table
    lines.append(
        "| \u9298\u67c4 | \u640d\u76ca | \u30c8\u30ec\u30f3\u30c9 "
        "| \u5909\u5316\u306e\u8cea | \u30a2\u30e9\u30fc\u30c8 "
        "| \u9577\u671f\u9069\u6027 | \u9084\u5143\u5b89\u5b9a\u5ea6 |"
    )
    lines.append("|:-----|-----:|:-------|:--------|:------------|:--------|:--------|")

    for pos in positions:
        symbol = pos.get("symbol", "-")
        if pos.get("is_small_cap"):
            symbol += " [小型]"
        pnl_pct = pos.get("pnl_pct", 0)
        pnl_str = _fmt_pct_sign(pnl_pct) if pnl_pct is not None else "-"

        trend = pos.get("trend_health", {}).get("trend", "不明")
        quality = pos.get("change_quality", {}).get("quality_label", "-")
        alert = pos.get("alert", {})
        alert_emoji = alert.get("emoji", "")
        alert_label = alert.get("label", "なし")

        if alert_emoji:
            alert_str = f"{alert_emoji} {alert_label}"
        else:
            alert_str = "なし"

        # Value trap indicator (KIK-381)
        vt = pos.get("value_trap", {})
        if vt.get("is_trap"):
            alert_str += " \U0001fa64"

        # Long-term suitability (KIK-371)
        lt = pos.get("long_term", {})
        lt_label = lt.get("label", "-")

        # Return stability (KIK-403)
        rs = pos.get("return_stability", {})
        rs_label = rs.get("label", "-") if rs else "-"

        lines.append(
            f"| {symbol} | {pnl_str} | {trend} | {quality} "
            f"| {alert_str} | {lt_label} | {rs_label} |"
        )

    lines.append("")

    # Summary counts
    total = summary.get("total", 0)
    healthy = summary.get("healthy", 0)
    early = summary.get("early_warning", 0)
    caution = summary.get("caution", 0)
    exit_count = summary.get("exit", 0)
    lines.append(
        f"**{total}\u9298\u67c4**: "
        f"\u5065\u5168 {healthy} / "
        f"\u26a1\u65e9\u671f\u8b66\u544a {early} / "
        f"\u26a0\u6ce8\u610f {caution} / "
        f"\U0001f6a8\u64a4\u9000 {exit_count}"
    )
    lines.append("")

    # Small-cap allocation (KIK-438)
    small_cap_alloc = health_data.get("small_cap_allocation")
    if small_cap_alloc:
        level = small_cap_alloc["level"]
        emoji = {"ok": "\u2705", "warning": "\u26a0\ufe0f", "critical": "\U0001f534"}[level]
        lines.append(f"{emoji} {small_cap_alloc['message']}")
        lines.append("")

    # Alert details
    if alerts:
        lines.append("## \u30a2\u30e9\u30fc\u30c8\u8a73\u7d30")
        lines.append("")

        for pos in alerts:
            symbol = pos.get("symbol", "-")
            alert = pos.get("alert", {})
            emoji = alert.get("emoji", "")
            label = alert.get("label", "")
            reasons = alert.get("reasons", [])
            trend_h = pos.get("trend_health", {})
            change_q = pos.get("change_quality", {})
            change_score = change_q.get("change_score", 0)

            lines.append(f"### {emoji} {symbol}（{label}）")
            lines.append("")

            for reason in reasons:
                lines.append(f"- {reason}")

            # Additional context
            trend = trend_h.get("trend", "不明")
            rsi = trend_h.get("rsi", float("nan"))
            sma50 = trend_h.get("sma50", float("nan"))
            sma200 = trend_h.get("sma200", float("nan"))
            quality_label = change_q.get("quality_label", "-")

            lines.append(
                f"- \u30c8\u30ec\u30f3\u30c9: {trend}"
                f"\uff08SMA50={_fmt_float(sma50)}, "
                f"SMA200={_fmt_float(sma200)}, "
                f"RSI={_fmt_float(rsi)}\uff09"
            )
            lines.append(
                f"- \u5909\u5316\u306e\u8cea: {quality_label}"
                f"\uff08\u5909\u5316\u30b9\u30b3\u30a2 {change_score:.0f}/100\uff09"
            )

            # Long-term suitability context (KIK-371)
            lt = pos.get("long_term", {})
            lt_label = lt.get("label", "-")
            lt_summary = lt.get("summary", "")
            if lt_label not in ("対象外", "-"):
                lines.append(
                    f"- \u9577\u671f\u9069\u6027: {lt_label}"
                    f"\uff08{lt_summary}\uff09"
                )

            # Value trap warning (KIK-381)
            vt = pos.get("value_trap")
            if vt and vt.get("is_trap"):
                lines.append(
                    f"- \U0001fa64 **\u30d0\u30ea\u30e5\u30fc\u30c8\u30e9\u30c3\u30d7\u5146\u5019**: "
                    f"{', '.join(vt['reasons'])}"
                )

            # Shareholder return stability context (KIK-403)
            rs = pos.get("return_stability")
            if rs:
                stability = rs.get("stability")
                latest_pct = (rs.get("latest_rate") or 0) * 100
                avg_pct = (rs.get("avg_rate") or 0) * 100
                if stability == "temporary":
                    lines.append(
                        f"- \u26a0\ufe0f **\u4e00\u6642\u7684\u9ad8\u9084\u5143**: "
                        f"{rs.get('reason', '')}"
                        f"\uff08\u76f4\u8fd1 {latest_pct:.1f}%\u3001"
                        f"\u5e73\u5747 {avg_pct:.1f}%\uff09"
                    )
                elif stability == "decreasing":
                    lines.append(
                        f"- \U0001f4c9 **\u682a\u4e3b\u9084\u5143\u6e1b\u5c11\u50be\u5411**: "
                        f"{rs.get('reason', '')}"
                    )
                elif stability in ("stable", "increasing"):
                    lines.append(
                        f"- {rs.get('label', '')} "
                        f"\uff08\u76f4\u8fd1 {latest_pct:.1f}%\uff09"
                    )
                elif stability and stability.startswith("single_"):
                    lines.append(
                        f"- {rs.get('label', '')} "
                        f"\uff08{rs.get('reason', '')}\uff09"
                    )

            # Action suggestion based on alert level
            level = alert.get("level", "none")
            if level == "early_warning":
                lines.append(
                    "\u2192 \u4e00\u6642\u7684\u306a\u8abf\u6574\u306e"
                    "\u53ef\u80fd\u6027\u3002\u30a6\u30a9\u30c3\u30c1\u5f37\u5316"
                )
            elif level == "caution":
                lines.append(
                    "\u2192 \u30dd\u30b8\u30b7\u30e7\u30f3\u7e2e\u5c0f"
                    "\u3092\u691c\u8a0e"
                )
            elif level == "exit":
                lines.append(
                    "\u2192 \u6295\u8cc7\u4eee\u8aac\u304c\u5d29\u58ca\u3002"
                    "exit\u3092\u691c\u8a0e"
                )

            lines.append("")

    return "\n".join(lines)
