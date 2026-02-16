"""Output formatters for screening results."""

from typing import Optional


def _fmt_pct(value: Optional[float]) -> str:
    """Format a decimal ratio as a percentage string (e.g. 0.035 -> '3.50%')."""
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _fmt_float(value: Optional[float], decimals: int = 2) -> str:
    """Format a float with the given decimal places, or '-' if None."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def format_markdown(results: list[dict]) -> str:
    """Format screening results as a Markdown table.

    Parameters
    ----------
    results : list[dict]
        Each dict should contain: symbol, name, price, per, pbr,
        dividend_yield, roe, value_score.

    Returns
    -------
    str
        A Markdown-formatted table string.
    """
    if not results:
        return "該当する銘柄が見つかりませんでした。"

    lines = [
        "| 順位 | 銘柄 | 株価 | PER | PBR | 配当利回り | ROE | スコア |",
        "|---:|:-----|-----:|----:|----:|---------:|----:|------:|",
    ]

    for rank, row in enumerate(results, start=1):
        symbol = row.get("symbol", "-")
        name = row.get("name") or ""
        label = f"{symbol} {name}".strip() if name else symbol

        price = _fmt_float(row.get("price"), decimals=0) if row.get("price") is not None else "-"
        per = _fmt_float(row.get("per"))
        pbr = _fmt_float(row.get("pbr"))
        div_yield = _fmt_pct(row.get("dividend_yield"))
        roe = _fmt_pct(row.get("roe"))
        score = _fmt_float(row.get("value_score"))

        lines.append(
            f"| {rank} | {label} | {price} | {per} | {pbr} | {div_yield} | {roe} | {score} |"
        )

    return "\n".join(lines)


def format_query_markdown(results: list[dict]) -> str:
    """Format EquityQuery screening results as a Markdown table.

    Includes sector column since QueryScreener results span diverse sectors.

    Parameters
    ----------
    results : list[dict]
        Each dict should contain: symbol, name, price, per, pbr,
        dividend_yield, roe, value_score, sector.

    Returns
    -------
    str
        A Markdown-formatted table string.
    """
    if not results:
        return "該当する銘柄が見つかりませんでした。"

    lines = [
        "| 順位 | 銘柄 | セクター | 株価 | PER | PBR | 配当利回り | ROE | スコア |",
        "|---:|:-----|:---------|-----:|----:|----:|---------:|----:|------:|",
    ]

    for rank, row in enumerate(results, start=1):
        symbol = row.get("symbol", "-")
        name = row.get("name") or ""
        label = f"{symbol} {name}".strip() if name else symbol
        sector = row.get("sector") or "-"

        price = _fmt_float(row.get("price"), decimals=0) if row.get("price") is not None else "-"
        per = _fmt_float(row.get("per"))
        pbr = _fmt_float(row.get("pbr"))
        div_yield = _fmt_pct(row.get("dividend_yield"))
        roe = _fmt_pct(row.get("roe"))
        score = _fmt_float(row.get("value_score"))

        lines.append(
            f"| {rank} | {label} | {sector} | {price} | {per} | {pbr} | {div_yield} | {roe} | {score} |"
        )

    return "\n".join(lines)


def format_pullback_markdown(results: list[dict]) -> str:
    """Format pullback screening results as a Markdown table."""
    if not results:
        return "押し目条件に合致する銘柄が見つかりませんでした。（上昇トレンド中の押し目銘柄なし）"

    lines = [
        "| 順位 | 銘柄 | 株価 | PER | 押し目% | RSI | 出来高比 | SMA50 | SMA200 | スコア | 一致度 | 総合スコア |",
        "|---:|:-----|-----:|----:|------:|----:|-------:|------:|-------:|------:|:------:|------:|",
    ]

    for rank, row in enumerate(results, start=1):
        symbol = row.get("symbol", "-")
        name = row.get("name") or ""
        label = f"{symbol} {name}".strip() if name else symbol

        price = _fmt_float(row.get("price"), decimals=0) if row.get("price") is not None else "-"
        per = _fmt_float(row.get("per"))
        pullback = _fmt_pct(row.get("pullback_pct"))
        rsi = _fmt_float(row.get("rsi"), decimals=1)
        vol_ratio = _fmt_float(row.get("volume_ratio"))
        sma50 = _fmt_float(row.get("sma50"), decimals=0) if row.get("sma50") is not None else "-"
        sma200 = _fmt_float(row.get("sma200"), decimals=0) if row.get("sma200") is not None else "-"

        # Bounce score
        bounce_score = row.get("bounce_score")
        bounce_str = f"{bounce_score:.0f}点" if bounce_score is not None else "-"

        # Match type
        match_type = row.get("match_type", "full")
        match_str = "★完全一致" if match_type == "full" else "△部分一致"

        score = _fmt_float(row.get("final_score") or row.get("value_score"))

        lines.append(
            f"| {rank} | {label} | {price} | {per} | {pullback} | {rsi} | {vol_ratio} | {sma50} | {sma200} | {bounce_str} | {match_str} | {score} |"
        )

    return "\n".join(lines)


def format_alpha_markdown(results: list[dict]) -> str:
    """Format alpha signal screening results as a Markdown table.

    Shows 2-axis scoring: value_score (100pt) + change_score (100pt) = total_score (200pt+).
    Also shows pullback status and key change indicators.
    """
    if not results:
        return "アルファシグナル条件に合致する銘柄が見つかりませんでした。"

    lines = [
        "| 順位 | 銘柄 | 株価 | PER | PBR | 割安 | 変化 | 総合 | 押し目 | ア | 加速 | FCF | ROE趨勢 |",
        "|---:|:-----|-----:|----:|----:|----:|----:|----:|:------:|:--:|:---:|:---:|:------:|",
    ]

    for rank, row in enumerate(results, start=1):
        symbol = row.get("symbol", "-")
        name = row.get("name") or ""
        label = f"{symbol} {name}".strip() if name else symbol

        price = _fmt_float(row.get("price"), decimals=0) if row.get("price") is not None else "-"
        per = _fmt_float(row.get("per"))
        pbr = _fmt_float(row.get("pbr"))

        value_score = _fmt_float(row.get("value_score"))
        change_score = _fmt_float(row.get("change_score"))
        total_score = _fmt_float(row.get("total_score"))

        # Pullback status
        pullback = row.get("pullback_match", "none")
        if pullback == "full":
            pb_str = "★"
        elif pullback == "partial":
            pb_str = "△"
        else:
            pb_str = "-"

        # Change indicators: ◎(>=20) ○(>=15) △(>=10) ×(<10)
        def _indicator(score):
            if score is None:
                return "-"
            if score >= 20:
                return "◎"
            if score >= 15:
                return "○"
            if score >= 10:
                return "△"
            return "×"

        accruals = _indicator(row.get("accruals_score"))
        rev_accel = _indicator(row.get("rev_accel_score"))
        fcf = _indicator(row.get("fcf_yield_score"))
        roe_trend = _indicator(row.get("roe_trend_score"))

        lines.append(
            f"| {rank} | {label} | {price} | {per} | {pbr} "
            f"| {value_score} | {change_score} | {total_score} | {pb_str} "
            f"| {accruals} | {rev_accel} | {fcf} | {roe_trend} |"
        )

    # Legend
    lines.append("")
    lines.append("**凡例**: 割安=割安スコア(100点) / 変化=変化スコア(100点) / 総合=割安+変化(+押し目ボーナス)")
    lines.append("**変化指標**: ア=アクルーアルズ(利益の質) / 加速=売上成長加速度 / FCF=FCF利回り / ROE趨勢=ROE改善トレンド")
    lines.append("**判定**: ◎=優秀(20+) ○=良好(15+) △=普通(10+) ×=不足(<10)")

    return "\n".join(lines)


def format_shareholder_return_markdown(results: list[dict]) -> str:
    """Format shareholder-return screening results as Markdown table."""
    if not results:
        return "_該当銘柄なし_"
    lines = []
    lines.append("| # | 銘柄 | セクター | PER | ROE | 配当利回り | 自社株買い | 総還元率 | 安定度 |")
    lines.append("|--:|:-----|:--------|----:|----:|----------:|---------:|--------:|:------|")
    for i, s in enumerate(results, 1):
        name = s.get("name", s.get("symbol", "?"))
        symbol = s.get("symbol", "")
        sector = s.get("sector", "-")
        per = s.get("per") or s.get("trailingPE")
        roe = s.get("roe") or s.get("returnOnEquity")
        div_yield = s.get("dividend_yield_trailing") or s.get("dividend_yield")
        buyback = s.get("buyback_yield")
        total_sr = s.get("total_shareholder_return")
        stability_label = s.get("return_stability_label", "-")

        per_str = f"{per:.1f}" if per else "-"
        roe_str = f"{roe*100:.1f}%" if roe else "-"
        div_str = f"{div_yield*100:.2f}%" if div_yield else "-"
        bb_str = f"{buyback*100:.2f}%" if buyback else "-"
        sr_str = f"**{total_sr*100:.2f}%**" if total_sr else "-"

        lines.append(f"| {i} | {name} ({symbol}) | {sector} | {per_str} | {roe_str} | {div_str} | {bb_str} | {sr_str} | {stability_label} |")
    return "\n".join(lines)


def format_trending_markdown(results: list[dict], market_context: str = "") -> str:
    """Format trending stock screening results as a Markdown table."""
    if not results:
        return "X上でトレンド中の銘柄が見つかりませんでした。"

    lines = []

    if market_context:
        lines.append(f"> **X市場センチメント**: {market_context}")
        lines.append("")

    lines.append(
        "| 順位 | 銘柄 | 話題の理由 | 株価 | PER | PBR | 配当利回り | ROE | スコア | 判定 |"
    )
    lines.append(
        "|---:|:-----|:---------|-----:|----:|----:|---------:|----:|------:|:----:|"
    )

    for rank, row in enumerate(results, start=1):
        symbol = row.get("symbol", "-")
        name = row.get("name") or ""
        label = f"{symbol} {name}".strip() if name else symbol

        reason = row.get("trending_reason") or "-"
        if len(reason) > 40:
            reason = reason[:37] + "..."

        price = _fmt_float(row.get("price"), decimals=0) if row.get("price") is not None else "-"
        per = _fmt_float(row.get("per"))
        pbr = _fmt_float(row.get("pbr"))
        div_yield = _fmt_pct(row.get("dividend_yield"))
        roe = _fmt_pct(row.get("roe"))
        score = _fmt_float(row.get("value_score"))

        classification = row.get("classification", "")
        if "データ不足" in classification:
            cls_str = "⚪不足"
        elif "割安" in classification:
            cls_str = "🟢割安"
        elif "適正" in classification:
            cls_str = "🟡適正"
        else:
            cls_str = "🔴割高"

        lines.append(
            f"| {rank} | {label} | {reason} | {price} | {per} | {pbr} "
            f"| {div_yield} | {roe} | {score} | {cls_str} |"
        )

    lines.append("")
    lines.append("**判定基準**: 🟢割安(スコア60+) / 🟡適正(スコア30-59) / 🔴割高(スコア30未満) / ⚪不足(データ取得失敗)")
    lines.append("**データソース**: X (Twitter) トレンド → Yahoo Finance ファンダメンタルズ")

    return "\n".join(lines)
