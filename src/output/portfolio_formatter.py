"""Output formatters for portfolio management (KIK-342)."""

from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Shared helpers (consistent with formatter.py / stress_formatter.py)
# ---------------------------------------------------------------------------

def _fmt_pct(value: Optional[float]) -> str:
    """Format a decimal ratio as a percentage string (e.g. 0.035 -> '3.50%')."""
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _fmt_pct_sign(value: Optional[float]) -> str:
    """Format a decimal ratio as a signed percentage (e.g. -0.12 -> '-12.00%')."""
    if value is None:
        return "-"
    return f"{value * 100:+.2f}%"


def _fmt_float(value: Optional[float], decimals: int = 2) -> str:
    """Format a float with the given decimal places, or '-' if None."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def _fmt_jpy(value: Optional[float]) -> str:
    """Format a value as Japanese Yen with comma separators."""
    if value is None:
        return "-"
    if value < 0:
        return f"-\u00a5{abs(value):,.0f}"
    return f"\u00a5{value:,.0f}"


def _fmt_usd(value: Optional[float]) -> str:
    """Format a value as US Dollar."""
    if value is None:
        return "-"
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def _fmt_currency_value(value: Optional[float], currency: str = "JPY") -> str:
    """Format a value in the appropriate currency format."""
    if value is None:
        return "-"
    currency = (currency or "JPY").upper()
    if currency == "JPY":
        return _fmt_jpy(value)
    elif currency == "USD":
        return _fmt_usd(value)
    else:
        return f"{value:,.2f} {currency}"


def _pnl_indicator(value: Optional[float]) -> str:
    """Return gain/loss indicator: triangle-up for positive, triangle-down for negative."""
    if value is None:
        return ""
    if value > 0:
        return "\u25b2"  # ▲
    elif value < 0:
        return "\u25bc"  # ▼
    return ""


def _hhi_bar(hhi: float, width: int = 10) -> str:
    """Render a simple text bar for HHI value (0-1 scale)."""
    filled = int(round(hhi * width))
    filled = max(0, min(filled, width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _classify_hhi(hhi: float) -> str:
    """Classify HHI into a risk label."""
    if hhi < 0.25:
        return "\u5206\u6563"  # 分散
    if hhi < 0.50:
        return "\u3084\u3084\u96c6\u4e2d"  # やや集中
    return "\u5371\u967a\u306a\u96c6\u4e2d"  # 危険な集中


# ---------------------------------------------------------------------------
# format_snapshot
# ---------------------------------------------------------------------------

def format_snapshot(snapshot: dict) -> str:
    """Format a portfolio snapshot as a Markdown report.

    Parameters
    ----------
    snapshot : dict
        Expected keys:
        - "timestamp": str (ISO format or display string)
        - "positions": list[dict] with keys:
            symbol, memo, shares, cost_price, current_price,
            market_value_jpy, pnl_jpy, pnl_pct, currency
        - "total_market_value_jpy": float
        - "total_cost_jpy": float
        - "total_pnl_jpy": float
        - "total_pnl_pct": float
        - "fx_rates": dict (e.g. {"USD/JPY": 150.0, "SGD/JPY": 110.0})

    Returns
    -------
    str
        Markdown-formatted snapshot report.
    """
    lines: list[str] = []

    # Header with timestamp
    ts = snapshot.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            ts_display = dt.strftime("%Y/%m/%d %H:%M")
        except (ValueError, TypeError):
            ts_display = str(ts)
    else:
        ts_display = datetime.now().strftime("%Y/%m/%d %H:%M")

    lines.append(f"## \u30dd\u30fc\u30c8\u30d5\u30a9\u30ea\u30aa \u30b9\u30ca\u30c3\u30d7\u30b7\u30e7\u30c3\u30c8 ({ts_display})")
    lines.append("")

    # Positions table
    positions = snapshot.get("positions", [])
    if not positions:
        lines.append("\u4fdd\u6709\u9298\u67c4\u304c\u3042\u308a\u307e\u305b\u3093\u3002")
        return "\n".join(lines)

    lines.append("| \u9298\u67c4 | \u30e1\u30e2 | \u682a\u6570 | \u53d6\u5f97\u5358\u4fa1 | \u73fe\u5728\u4fa1\u683c | \u8a55\u4fa1\u984d | \u640d\u76ca | \u640d\u76ca\u7387 |")
    lines.append("|:-----|:-----|-----:|-------:|-------:|------:|-----:|-----:|")

    for pos in positions:
        symbol = pos.get("symbol", "-")
        memo = pos.get("memo") or ""
        shares = pos.get("shares", 0)
        cost_price = pos.get("cost_price")
        current_price = pos.get("current_price")
        market_value = pos.get("market_value_jpy")
        pnl = pos.get("pnl_jpy")
        pnl_pct = pos.get("pnl_pct")
        currency = pos.get("currency", "JPY")

        cost_str = _fmt_currency_value(cost_price, currency)
        price_str = _fmt_currency_value(current_price, currency)
        mv_str = _fmt_jpy(market_value)

        # PnL with indicator
        indicator = _pnl_indicator(pnl)
        pnl_str = f"{indicator} {_fmt_jpy(pnl)}" if pnl is not None else "-"
        pnl_pct_str = f"{indicator} {_fmt_pct(pnl_pct)}" if pnl_pct is not None else "-"

        lines.append(
            f"| {symbol} | {memo} | {shares:,} | {cost_str} | {price_str} "
            f"| {mv_str} | {pnl_str} | {pnl_pct_str} |"
        )

    lines.append("")

    # Summary
    lines.append("### \u30b5\u30de\u30ea\u30fc")

    total_mv = snapshot.get("total_market_value_jpy")
    total_cost = snapshot.get("total_cost_jpy")
    total_pnl = snapshot.get("total_pnl_jpy")
    total_pnl_pct = snapshot.get("total_pnl_pct")

    lines.append(f"- \u7dcf\u8a55\u4fa1\u984d\uff08\u5186\uff09: {_fmt_jpy(total_mv)}")
    lines.append(f"- \u7dcf\u6295\u8cc7\u984d\uff08\u5186\uff09: {_fmt_jpy(total_cost)}")

    if total_pnl is not None and total_pnl_pct is not None:
        indicator = _pnl_indicator(total_pnl)
        lines.append(
            f"- \u7dcf\u640d\u76ca\uff08\u5186\uff09: {indicator} {_fmt_jpy(total_pnl)} "
            f"({_fmt_pct_sign(total_pnl_pct)})"
        )
    elif total_pnl is not None:
        indicator = _pnl_indicator(total_pnl)
        lines.append(f"- \u7dcf\u640d\u76ca\uff08\u5186\uff09: {indicator} {_fmt_jpy(total_pnl)}")

    lines.append("")

    # FX Rates
    fx_rates = snapshot.get("fx_rates", {})
    if fx_rates:
        lines.append("### \u70ba\u66ff\u30ec\u30fc\u30c8")
        for pair, rate in fx_rates.items():
            lines.append(f"- {pair}: {_fmt_float(rate, decimals=2)}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# format_position_list
# ---------------------------------------------------------------------------

def format_position_list(portfolio: list[dict]) -> str:
    """Format a list of portfolio positions as a Markdown table.

    Parameters
    ----------
    portfolio : list[dict]
        Each dict should contain: symbol, shares, cost_price,
        cost_currency, purchase_date, memo.

    Returns
    -------
    str
        Markdown-formatted table of positions.
    """
    lines: list[str] = []
    lines.append("## \u4fdd\u6709\u9298\u67c4\u4e00\u89a7")
    lines.append("")

    if not portfolio:
        lines.append("\u4fdd\u6709\u9298\u67c4\u304c\u3042\u308a\u307e\u305b\u3093\u3002")
        return "\n".join(lines)

    lines.append("| \u9298\u67c4 | \u682a\u6570 | \u53d6\u5f97\u5358\u4fa1 | \u901a\u8ca8 | \u53d6\u5f97\u65e5 | \u30e1\u30e2 |")
    lines.append("|:-----|-----:|-------:|:-----|:---------|:-----|")

    for pos in portfolio:
        symbol = pos.get("symbol", "-")
        shares = pos.get("shares", 0)
        cost_price = pos.get("cost_price")
        currency = pos.get("cost_currency") or pos.get("currency", "JPY")
        purchase_date = pos.get("purchase_date") or "-"
        memo = pos.get("memo") or ""

        cost_str = _fmt_currency_value(cost_price, currency)

        lines.append(
            f"| {symbol} | {shares:,} | {cost_str} | {currency} "
            f"| {purchase_date} | {memo} |"
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# format_structure_analysis
# ---------------------------------------------------------------------------

def format_structure_analysis(analysis: dict) -> str:
    """Format a portfolio structure analysis as a Markdown report.

    Parameters
    ----------
    analysis : dict
        Expected keys (from concentration.analyze_concentration()):
        - "region_hhi", "region_breakdown"
        - "sector_hhi", "sector_breakdown"
        - "currency_hhi", "currency_breakdown"
        - "max_hhi", "max_hhi_axis"
        - "concentration_multiplier"
        - "risk_level"

    Returns
    -------
    str
        Markdown-formatted structure analysis report.
    """
    lines: list[str] = []
    lines.append("## \u30dd\u30fc\u30c8\u30d5\u30a9\u30ea\u30aa\u69cb\u9020\u5206\u6790")
    lines.append("")

    # --- Region breakdown ---
    lines.append("### \u5730\u57df\u5225\u914d\u5206")
    region_hhi = analysis.get("region_hhi", 0.0)
    region_breakdown = analysis.get("region_breakdown", {})

    lines.append("")
    lines.append("| \u5730\u57df | \u6bd4\u7387 | \u30d0\u30fc |")
    lines.append("|:-----|-----:|:-----|")
    for region, weight in sorted(region_breakdown.items(), key=lambda x: -x[1]):
        bar_len = int(round(weight * 20))
        bar = "\u2588" * bar_len
        lines.append(f"| {region} | {_fmt_pct(weight)} | {bar} |")
    lines.append("")
    lines.append(f"HHI: {_fmt_float(region_hhi, 4)} {_hhi_bar(region_hhi)} ({_classify_hhi(region_hhi)})")
    lines.append("")

    # --- Sector breakdown ---
    lines.append("### \u30bb\u30af\u30bf\u30fc\u5225\u914d\u5206")
    sector_hhi = analysis.get("sector_hhi", 0.0)
    sector_breakdown = analysis.get("sector_breakdown", {})

    lines.append("")
    lines.append("| \u30bb\u30af\u30bf\u30fc | \u6bd4\u7387 | \u30d0\u30fc |")
    lines.append("|:---------|-----:|:-----|")
    for sector, weight in sorted(sector_breakdown.items(), key=lambda x: -x[1]):
        bar_len = int(round(weight * 20))
        bar = "\u2588" * bar_len
        lines.append(f"| {sector} | {_fmt_pct(weight)} | {bar} |")
    lines.append("")
    lines.append(f"HHI: {_fmt_float(sector_hhi, 4)} {_hhi_bar(sector_hhi)} ({_classify_hhi(sector_hhi)})")
    lines.append("")

    # --- Currency breakdown ---
    lines.append("### \u901a\u8ca8\u5225\u914d\u5206")
    currency_hhi = analysis.get("currency_hhi", 0.0)
    currency_breakdown = analysis.get("currency_breakdown", {})

    lines.append("")
    lines.append("| \u901a\u8ca8 | \u6bd4\u7387 | \u30d0\u30fc |")
    lines.append("|:-----|-----:|:-----|")
    for currency, weight in sorted(currency_breakdown.items(), key=lambda x: -x[1]):
        bar_len = int(round(weight * 20))
        bar = "\u2588" * bar_len
        lines.append(f"| {currency} | {_fmt_pct(weight)} | {bar} |")
    lines.append("")
    lines.append(f"HHI: {_fmt_float(currency_hhi, 4)} {_hhi_bar(currency_hhi)} ({_classify_hhi(currency_hhi)})")
    lines.append("")

    # --- Overall judgment ---
    lines.append("### \u7dcf\u5408\u5224\u5b9a")
    max_hhi = analysis.get("max_hhi", 0.0)
    max_axis = analysis.get("max_hhi_axis", "-")
    multiplier = analysis.get("concentration_multiplier", 1.0)
    risk_level = analysis.get("risk_level", "-")

    axis_labels = {
        "sector": "\u30bb\u30af\u30bf\u30fc",
        "region": "\u5730\u57df",
        "currency": "\u901a\u8ca8",
    }
    axis_display = axis_labels.get(max_axis, max_axis)

    lines.append(f"- \u96c6\u4e2d\u5ea6\u500d\u7387: x{_fmt_float(multiplier, 2)}")
    lines.append(f"- \u30ea\u30b9\u30af\u30ec\u30d9\u30eb: **{risk_level}**")
    lines.append(f"- \u6700\u5927\u96c6\u4e2d\u8ef8: {axis_display} (HHI: {_fmt_float(max_hhi, 4)})")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# format_trade_result
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# format_health_check (KIK-356)
# ---------------------------------------------------------------------------

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

    lines.append("## \u4fdd\u6709\u9298\u67c4\u30d8\u30eb\u30b9\u30c1\u30a7\u30c3\u30af")
    lines.append("")

    # Summary table
    lines.append(
        "| \u9298\u67c4 | \u640d\u76ca | \u30c8\u30ec\u30f3\u30c9 "
        "| \u5909\u5316\u306e\u8cea | \u30a2\u30e9\u30fc\u30c8 |"
    )
    lines.append("|:-----|-----:|:-------|:--------|:------------|")

    for pos in positions:
        symbol = pos.get("symbol", "-")
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

        lines.append(
            f"| {symbol} | {pnl_str} | {trend} | {quality} | {alert_str} |"
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


# ---------------------------------------------------------------------------
# format_trade_result
# ---------------------------------------------------------------------------

def format_trade_result(result: dict, action: str) -> str:
    """Format a buy/sell trade result as Markdown.

    Parameters
    ----------
    result : dict
        Expected keys:
        - "symbol": str
        - "shares": int (traded quantity)
        - "price": float (trade price)
        - "currency": str
        - "total_shares": int (updated holding)
        - "avg_cost": float (updated average cost)
        - "memo": str (optional)
    action : str
        "buy" or "sell" (or Japanese equivalents).

    Returns
    -------
    str
        Markdown-formatted trade result.
    """
    lines: list[str] = []

    # Normalize action label
    action_lower = action.lower()
    if action_lower in ("buy", "\u8cfc\u5165", "\u8cb7\u3044"):
        action_label = "\u8cfc\u5165"
    elif action_lower in ("sell", "\u58f2\u5374", "\u58f2\u308a"):
        action_label = "\u58f2\u5374"
    else:
        action_label = action

    symbol = result.get("symbol", "-")
    shares = result.get("shares", 0)
    price = result.get("price")
    currency = result.get("currency", "JPY")
    total_shares = result.get("total_shares")
    avg_cost = result.get("avg_cost")
    memo = result.get("memo") or ""

    lines.append("## \u58f2\u8cb7\u8a18\u9332")
    lines.append("")
    lines.append(f"- \u30a2\u30af\u30b7\u30e7\u30f3: **{action_label}**")
    lines.append(f"- \u9298\u67c4: {symbol}")
    if memo:
        lines.append(f"- \u30e1\u30e2: {memo}")
    lines.append(f"- \u682a\u6570: {shares:,}")
    if price is not None:
        lines.append(f"- \u5358\u4fa1: {_fmt_currency_value(price, currency)}")

    if total_shares is not None:
        avg_cost_str = _fmt_currency_value(avg_cost, currency) if avg_cost is not None else "-"
        lines.append(
            f"- \u66f4\u65b0\u5f8c\u306e\u4fdd\u6709: {total_shares:,}\u682a "
            f"(\u5e73\u5747\u53d6\u5f97\u5358\u4fa1: {avg_cost_str})"
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# format_return_estimate (KIK-359)
# ---------------------------------------------------------------------------

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

    # --- Per-stock details ---
    for pos in positions:
        symbol = pos.get("symbol", "-")
        base_ret = pos.get("base")
        method = pos.get("method", "")
        currency = pos.get("currency", "USD")

        # Header
        base_str = _fmt_pct_sign(base_ret) if base_ret is not None else "-"
        lines.append(f"### {symbol} \u671f\u5f85\u30ea\u30bf\u30fc\u30f3: {base_str}\uff08\u30d9\u30fc\u30b9\uff09")
        lines.append("")

        # Quantitative section
        if method == "analyst":
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

        # News section
        news = pos.get("news", [])
        if news:
            lines.append("\u3010\u30cb\u30e5\u30fc\u30b9\u3011")
            for item in news[:5]:
                title = item.get("title", "")
                publisher = item.get("publisher", "")
                if title:
                    pub_str = f" ({publisher})" if publisher else ""
                    lines.append(f"  - {title}{pub_str}")

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

        lines.append("")

    return "\n".join(lines)
