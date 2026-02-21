"""Structure analysis and shareholder-return output formatters (KIK-447, split from portfolio_formatter.py)."""

from src.output._format_helpers import fmt_pct as _fmt_pct
from src.output._format_helpers import fmt_float as _fmt_float
from src.output._format_helpers import hhi_bar as _hhi_bar
from src.output._portfolio_utils import _classify_hhi


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

    # --- Size breakdown (KIK-438) ---
    lines.append("### \u898f\u6a21\u5225\u69cb\u6210")
    size_hhi = analysis.get("size_hhi", 0.0)
    size_breakdown = analysis.get("size_breakdown", {})

    if size_breakdown:
        lines.append("")
        lines.append("| \u898f\u6a21 | \u6bd4\u7387 | \u30d0\u30fc |")
        lines.append("|:-----|-----:|:-----|")
        for size_class, weight in sorted(size_breakdown.items(), key=lambda x: -x[1]):
            bar_len = int(round(weight * 20))
            bar = "\u2588" * bar_len
            lines.append(f"| {size_class} | {_fmt_pct(weight)} | {bar} |")
        lines.append("")
        lines.append(f"HHI: {_fmt_float(size_hhi, 4)} {_hhi_bar(size_hhi)} ({_classify_hhi(size_hhi)})")
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
        "size": "\u898f\u6a21",
    }
    axis_display = axis_labels.get(max_axis, max_axis)

    lines.append(f"- \u96c6\u4e2d\u5ea6\u500d\u7387: x{_fmt_float(multiplier, 2)}")
    lines.append(f"- \u30ea\u30b9\u30af\u30ec\u30d9\u30eb: **{risk_level}**")
    lines.append(f"- \u6700\u5927\u96c6\u4e2d\u8ef8: {axis_display} (HHI: {_fmt_float(max_hhi, 4)})")
    lines.append("")

    return "\n".join(lines)


def format_shareholder_return_analysis(data: dict) -> str:
    """Format portfolio shareholder return analysis as markdown.

    Parameters
    ----------
    data : dict
        Output of portfolio_manager.get_portfolio_shareholder_return().
        Keys: positions, weighted_avg_rate.

    Returns
    -------
    str
        Markdown-formatted section.
    """
    positions = data.get("positions", [])
    avg_rate = data.get("weighted_avg_rate")
    if not positions:
        return ""

    lines: list[str] = []
    lines.append("## 株主還元分析")
    lines.append("")
    lines.append("| 銘柄 | 総株主還元率 |")
    lines.append("|:-----|-----:|")
    for pr in positions:
        lines.append(f"| {pr['symbol']} | {pr['rate'] * 100:.2f}% |")
    lines.append("")
    if avg_rate is not None:
        lines.append(f"- **加重平均 総株主還元率**: {avg_rate * 100:.2f}%")
        lines.append("")
    return "\n".join(lines)
