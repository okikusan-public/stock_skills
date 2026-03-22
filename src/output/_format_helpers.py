"""Shared formatting helpers used across all output formatters (KIK-394)."""

from typing import Optional


# ---------------------------------------------------------------------------
# Currency formatters (canonical location, moved from _portfolio_utils KIK-572)
# ---------------------------------------------------------------------------

def fmt_jpy(value: Optional[float]) -> str:
    """Format a value as Japanese Yen with comma separators."""
    if value is None:
        return "-"
    if value < 0:
        return f"-\u00a5{abs(value):,.0f}"
    return f"\u00a5{value:,.0f}"


def fmt_usd(value: Optional[float]) -> str:
    """Format a value as US Dollar."""
    if value is None:
        return "-"
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def fmt_currency_value(value: Optional[float], currency: str = "JPY") -> str:
    """Format a value in the appropriate currency format."""
    if value is None:
        return "-"
    currency = (currency or "JPY").upper()
    if currency == "JPY":
        return fmt_jpy(value)
    elif currency == "USD":
        return fmt_usd(value)
    else:
        return f"{value:,.2f} {currency}"


def fmt_pct(value: Optional[float]) -> str:
    """Format a decimal ratio as a percentage string (e.g. 0.035 -> '3.50%')."""
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def fmt_float(value: Optional[float], decimals: int = 2) -> str:
    """Format a float with the given decimal places, or '-' if None."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def fmt_pct_sign(value: Optional[float]) -> str:
    """Format a decimal ratio as a signed percentage (e.g. -0.12 -> '-12.00%')."""
    if value is None:
        return "-"
    return f"{value * 100:+.2f}%"


def fmt_float_sign(value: Optional[float], decimals: int = 2) -> str:
    """Format a float with sign and given decimal places."""
    if value is None:
        return "-"
    return f"{value:+.{decimals}f}"


def build_label(row: dict) -> str:
    """Build stock label with annotation markers (KIK-418/419).

    Combines symbol + name + any note markers from screen_annotator.
    """
    symbol = row.get("symbol", "-")
    name = row.get("name") or ""
    label = f"{symbol} {name}".strip() if name else symbol
    markers = row.get("_note_markers", "")
    if markers:
        label = f"{label} {markers}"
    return label


def hhi_bar(hhi: float, width: int = 10) -> str:
    """Render a simple text bar for HHI value (0-1 scale)."""
    filled = int(round(hhi * width))
    filled = max(0, min(filled, width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


# ---------------------------------------------------------------------------
# Screening table renderer (KIK-575)
# ---------------------------------------------------------------------------

# Column type: (header_name, alignment, cell_fn)
# cell_fn signature: (rank: int, row: dict) -> str

def render_screening_table(
    results: list[dict],
    columns: list[tuple],
    empty_msg: str = "該当銘柄なし",
    legends: list[str] | None = None,
) -> str:
    """Render a screening result table in Markdown (KIK-575).

    Parameters
    ----------
    results : list[dict]
        Screening result rows.
    columns : list[tuple]
        Each tuple: (header: str, align: str, cell_fn: callable)
        cell_fn(rank, row) -> str
    empty_msg : str
        Message when results is empty.
    legends : list[str] | None
        Optional footer legend lines.

    Returns
    -------
    str
        Markdown table string.
    """
    if not results:
        return empty_msg

    # Header
    header = "| " + " | ".join(c[0] for c in columns) + " |"
    separator = "|" + "|".join(c[1] for c in columns) + "|"
    lines = [header, separator]

    # Rows
    for rank, row in enumerate(results, start=1):
        cells = [c[2](rank, row) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")

    # Legends
    if legends:
        lines.append("")
        lines.extend(legends)

    # Annotation footer
    _append_annotation_footer(lines, results)

    return "\n".join(lines)


def _append_annotation_footer(lines: list[str], results: list[dict]) -> None:
    """Append note annotation legend if any results have markers."""
    has_markers = any(r.get("_note_markers") for r in results)
    if not has_markers:
        return
    lines.append("")
    lines.append("**マーカー凡例**: ⚠️=懸念メモあり / 📝=学びメモあり / 👀=様子見")
    noted = [
        (r.get("symbol", "?"), r.get("_note_summary", ""))
        for r in results if r.get("_note_summary")
    ]
    if noted:
        lines.append("")
        lines.append("**メモ詳細**:")
        for sym, summary in noted:
            lines.append(f"- **{sym}**: {summary}")
