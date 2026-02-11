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
        "| 順位 | 銘柄 | 株価 | PER | 押し目% | RSI | 出来高比 | SMA50 | SMA200 | スコア |",
        "|---:|:-----|-----:|----:|------:|----:|-------:|------:|-------:|------:|",
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
        score = _fmt_float(row.get("final_score"))

        lines.append(
            f"| {rank} | {label} | {price} | {per} | {pullback} | {rsi} | {vol_ratio} | {sma50} | {sma200} | {score} |"
        )

    return "\n".join(lines)
