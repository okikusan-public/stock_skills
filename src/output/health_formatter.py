"""Health check output formatter (KIK-447, split from portfolio_formatter.py)."""

from src.output._format_helpers import fmt_pct_sign as _fmt_pct_sign
from src.output._format_helpers import fmt_float as _fmt_float


def _render_stock_table(lines: list[str], positions: list[dict]) -> None:
    """Render the stock health check table (individual stocks)."""
    lines.append(
        "| 銘柄 | 損益 | トレンド "
        "| 変化の質 | アラート "
        "| 長期適性 | 還元安定度 | 逆張り |"
    )
    lines.append("|:-----|-----:|:-------|:--------|:------------|:--------|:--------|:-------|")

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

        # Contrarian indicator (KIK-519)
        ct = pos.get("contrarian")
        if ct and ct.get("contrarian_score", 0) > 0:
            ct_grade = ct.get("grade", "-")
            ct_score = ct["contrarian_score"]
            ct_str = f"{ct_grade}{ct_score:.0f}"
        else:
            ct_str = "-"

        lines.append(
            f"| {symbol} | {pnl_str} | {trend} | {quality} "
            f"| {alert_str} | {lt_label} | {rs_label} | {ct_str} |"
        )

    lines.append("")


def _render_etf_table(lines: list[str], positions: list[dict]) -> None:
    """Render the ETF health check table (KIK-469 Phase 2)."""
    lines.append(
        "| 銘柄 | 損益 | トレンド "
        "| 経費率 | AUM | ETFスコア | アラート |"
    )
    lines.append("|:-----|-----:|:-------|:--------|:------|----------:|:--------|")

    for pos in positions:
        symbol = pos.get("symbol", "-")
        pnl_pct = pos.get("pnl_pct", 0)
        pnl_str = _fmt_pct_sign(pnl_pct) if pnl_pct is not None else "-"
        trend = pos.get("trend_health", {}).get("trend", "不明")

        change_q = pos.get("change_quality", {})
        etf_health = change_q.get("etf_health") or pos.get("long_term", {}).get("etf_health")
        if etf_health:
            expense = etf_health.get("expense_label", "-")
            aum = etf_health.get("aum_label", "-")
            score = etf_health.get("score", "-")
            score_str = f"{score}/100" if isinstance(score, (int, float)) else "-"
        else:
            expense = "-"
            aum = "-"
            score_str = "-"

        alert = pos.get("alert", {})
        alert_emoji = alert.get("emoji", "")
        alert_label = alert.get("label", "なし")
        alert_str = f"{alert_emoji} {alert_label}" if alert_emoji else "なし"

        lines.append(
            f"| {symbol} | {pnl_str} | {trend} | {expense} "
            f"| {aum} | {score_str} | {alert_str} |"
        )

    lines.append("")


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
        lines.append("## 保有銘柄ヘルスチェック")
        lines.append("")
        lines.append("保有銘柄がありません。")
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
        return "  → " + ", ".join(shown) + suffix

    lines.append("## 📊 ヘルスチェック サマリー（" + str(total) + "銘柄）")
    lines.append("")
    lines.append(f"🔴 撤退検討  : {len(exit_syms)}銘柄{_syms_str(exit_syms)}")
    lines.append(f"⚠️  注意      : {len(caution_syms)}銘柄{_syms_str(caution_syms)}")
    lines.append(f"⏰ 早期警告  : {len(early_syms)}銘柄{_syms_str(early_syms)}")
    lines.append(f"✅ 異常なし  : {healthy_count}銘柄")
    lines.append("")
    lines.append("─── 詳細 ────────────────────────────────")
    lines.append("")

    # KIK-469 Phase 2: Split tables by stock/ETF
    stock_positions = health_data.get("stock_positions")
    etf_positions = health_data.get("etf_positions")

    if stock_positions is None:
        # Backward compat: old format without partition keys
        lines.append("## 保有銘柄ヘルスチェック")
        lines.append("")
        _render_stock_table(lines, positions)
    else:
        has_both = bool(stock_positions) and bool(etf_positions)
        if stock_positions:
            if has_both:
                lines.append("## 個別株ヘルスチェック")
                lines.append("")
            else:
                lines.append("## 保有銘柄ヘルスチェック")
                lines.append("")
            _render_stock_table(lines, stock_positions)
        if etf_positions:
            if has_both:
                lines.append("## ETFヘルスチェック")
                lines.append("")
            else:
                lines.append("## 保有銘柄ヘルスチェック")
                lines.append("")
            _render_etf_table(lines, etf_positions)

    # Summary counts
    total = summary.get("total", 0)
    healthy = summary.get("healthy", 0)
    early = summary.get("early_warning", 0)
    caution = summary.get("caution", 0)
    exit_count = summary.get("exit", 0)
    lines.append(
        f"**{total}銘柄**: "
        f"健全 {healthy} / "
        f"⚡早期警告 {early} / "
        f"⚠注意 {caution} / "
        f"🚨撤退 {exit_count}"
    )
    lines.append("")

    # Small-cap allocation (KIK-438)
    small_cap_alloc = health_data.get("small_cap_allocation")
    if small_cap_alloc:
        level = small_cap_alloc["level"]
        emoji = {"ok": "✅", "warning": "⚠️", "critical": "🔴"}[level]
        lines.append(f"{emoji} {small_cap_alloc['message']}")
        lines.append("")

    # Alert details
    if alerts:
        lines.append("## アラート詳細")
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
                f"- トレンド: {trend}"
                f"（SMA50={_fmt_float(sma50)}, "
                f"SMA200={_fmt_float(sma200)}, "
                f"RSI={_fmt_float(rsi)}）"
            )

            # ETF-specific context (KIK-469)
            etf_h = change_q.get("etf_health")
            if change_q.get("is_etf") and etf_h:
                lines.append(f"- ETF: {etf_h.get('fund_category', '-')} / {etf_h.get('fund_family', '-')}")
                lines.append(f"- 経費率: {etf_h.get('expense_label', '-')} / AUM: {etf_h.get('aum_label', '-')}")
                for etf_alert in etf_h.get("alerts", []):
                    lines.append(f"- {etf_alert}")
            else:
                lines.append(
                    f"- 変化の質: {quality_label}"
                    f"（変化スコア {change_score:.0f}/100）"
                )

            # Long-term suitability context (KIK-371)
            lt = pos.get("long_term", {})
            lt_label = lt.get("label", "-")
            lt_summary = lt.get("summary", "")
            if lt_label not in ("対象外", "-"):
                lines.append(
                    f"- 長期適性: {lt_label}"
                    f"（{lt_summary}）"
                )

            # Value trap warning (KIK-381)
            vt = pos.get("value_trap")
            if vt and vt.get("is_trap"):
                lines.append(
                    f"- \U0001fa64 **バリュートラップ兆候**: "
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
                        f"- ⚠️ **一時的高還元**: "
                        f"{rs.get('reason', '')}"
                        f"（直近 {latest_pct:.1f}%、"
                        f"平均 {avg_pct:.1f}%）"
                    )
                elif stability == "decreasing":
                    lines.append(
                        f"- 📉 **株主還元減少傾向**: "
                        f"{rs.get('reason', '')}"
                    )
                elif stability in ("stable", "increasing"):
                    lines.append(
                        f"- {rs.get('label', '')} "
                        f"（直近 {latest_pct:.1f}%）"
                    )
                elif stability and stability.startswith("single_"):
                    lines.append(
                        f"- {rs.get('label', '')} "
                        f"（{rs.get('reason', '')}）"
                    )

            # Contrarian signal for alerted stocks (KIK-519)
            ct = pos.get("contrarian")
            if ct and ct.get("contrarian_score", 0) > 0:
                ct_score = ct["contrarian_score"]
                ct_grade = ct.get("grade", "-")
                ct_tech = ct.get("technical", {}).get("score", 0)
                ct_val = ct.get("valuation", {}).get("score", 0)
                ct_fund = ct.get("fundamental", {}).get("score", 0)
                ct_sent = ct.get("sentiment", {}).get("score", 0) if ct.get("sentiment") else 0
                if ct_sent > 0:
                    lines.append(
                        f"- 逆張りスコア: {ct_score:.0f}/100 (グレード{ct_grade}) "
                        f"[テク{ct_tech:.0f} バリュ{ct_val:.0f} ファンダ{ct_fund:.0f} センチ{ct_sent:.0f}]"
                    )
                else:
                    lines.append(
                        f"- 逆張りスコア: {ct_score:.0f}/100 (グレード{ct_grade}) "
                        f"[テク{ct_tech:.0f} バリュ{ct_val:.0f} ファンダ{ct_fund:.0f}]"
                    )
                if ct_grade in ("A", "B"):
                    lines.append(
                        "  → **逆張り買い候補**: "
                        "ファンダは健全だがセンチメント悪化の可能性"
                    )
                elif ct_grade == "C":
                    lines.append(
                        "  → 弱い逆張りシグナル: "
                        "一部条件が整っている"
                    )

            # Action suggestion based on alert level
            level = alert.get("level", "none")
            if level == "early_warning":
                lines.append(
                    "→ 一時的な調整の"
                    "可能性。ウォッチ強化"
                )
            elif level == "caution":
                lines.append(
                    "→ ポジション縮小"
                    "を検討"
                )
            elif level == "exit":
                lines.append(
                    "→ 投資仮説が崩壊。"
                    "exitを検討"
                )

            lines.append("")

    return "\n".join(lines)
