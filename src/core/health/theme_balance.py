"""Theme balance checks for portfolio health (KIK-605).

Detects:
1. Theme concentration — too many stocks or too much weight in a single theme.
2. Sector-relative PER warning — stock PER significantly above sector median.
3. Theme cooling — trending themes losing momentum vs. previous scan.
"""

from __future__ import annotations

from src.core._thresholds import th


# ---------------------------------------------------------------------------
# Theme concentration
# ---------------------------------------------------------------------------

def check_theme_concentration(
    positions: list[dict],
    themes_map: dict[str, list[str]],
) -> list[dict]:
    """Check if any theme is over-concentrated in PF.

    Args:
        positions: list of position dicts, each with at least ``symbol`` and
            ``weight`` (float 0-1).
        themes_map: mapping ``{symbol: [theme1, theme2, ...]}``.

    Returns:
        list of warnings, each ``{theme, weight, stock_count, symbols, level}``.
        ``level`` is ``'warn'`` or ``'danger'``.
    """
    max_weight = th("theme_balance", "max_theme_weight", 0.20)
    max_stocks = th("theme_balance", "max_theme_stocks", 3)

    # Aggregate weight and count per theme
    theme_agg: dict[str, dict] = {}
    for pos in positions:
        sym = pos.get("symbol", "")
        w = pos.get("weight", 0.0)
        if not isinstance(w, (int, float)):
            w = 0.0
        for theme in themes_map.get(sym, []):
            if theme not in theme_agg:
                theme_agg[theme] = {"weight": 0.0, "count": 0, "symbols": []}
            theme_agg[theme]["weight"] += w
            theme_agg[theme]["count"] += 1
            theme_agg[theme]["symbols"].append(sym)

    warnings: list[dict] = []
    for theme, agg in sorted(theme_agg.items()):
        w = agg["weight"]
        cnt = agg["count"]
        # Determine level: danger if both thresholds exceeded, else warn
        over_weight = w > max_weight
        over_count = cnt >= max_stocks
        if over_weight or over_count:
            level = "danger" if (over_weight and over_count) else "warn"
            warnings.append({
                "theme": theme,
                "weight": round(w, 4),
                "stock_count": cnt,
                "symbols": agg["symbols"],
                "level": level,
            })
    return warnings


# ---------------------------------------------------------------------------
# Sector-relative PER warning
# ---------------------------------------------------------------------------

def check_sector_relative_per(
    positions: list[dict],
    sector_median_per: dict[str, float],
) -> list[dict]:
    """Flag positions whose PER is far above sector median.

    Args:
        positions: list of position dicts, each with ``symbol``, ``sector``,
            and ``per`` (trailing PER).
        sector_median_per: mapping ``{sector: median_per}``.

    Returns:
        list of warnings ``{symbol, sector, per, sector_median, ratio, level}``.
    """
    multiplier = th("theme_balance", "per_warn_multiplier", 2.0)
    warnings: list[dict] = []
    for pos in positions:
        sym = pos.get("symbol", "")
        sector = pos.get("sector", "")
        per = pos.get("per")
        if per is None or not isinstance(per, (int, float)) or per <= 0:
            continue
        median = sector_median_per.get(sector)
        if median is None or median <= 0:
            continue
        ratio = per / median
        if ratio >= multiplier:
            warnings.append({
                "symbol": sym,
                "sector": sector,
                "per": round(per, 2),
                "sector_median": round(median, 2),
                "ratio": round(ratio, 2),
                "level": "warn",
            })
    return warnings


# ---------------------------------------------------------------------------
# Theme cooling / staleness detection
# ---------------------------------------------------------------------------

def detect_theme_cooling(
    current_trends: list[dict],
    previous_trends: list[dict],
) -> list[dict]:
    """Detect themes that are cooling down.

    Compares two snapshots of trending themes (each a list of dicts with
    ``theme`` and ``confidence`` keys).

    Returns:
        list of cooling themes: ``{theme, prev_confidence, current_confidence,
        status}`` where status is ``'cooling'`` (confidence dropped) or
        ``'gone'`` (theme disappeared from current scan).
    """
    current_map: dict[str, float] = {}
    for t in current_trends:
        name = t.get("theme", "").strip().lower()
        if name:
            current_map[name] = float(t.get("confidence", 0.0))

    prev_map: dict[str, float] = {}
    for t in previous_trends:
        name = t.get("theme", "").strip().lower()
        if name:
            prev_map[name] = float(t.get("confidence", 0.0))

    results: list[dict] = []
    for theme, prev_conf in prev_map.items():
        cur_conf = current_map.get(theme)
        if cur_conf is None:
            results.append({
                "theme": theme,
                "prev_confidence": round(prev_conf, 2),
                "current_confidence": 0.0,
                "status": "gone",
            })
        elif cur_conf < prev_conf:
            results.append({
                "theme": theme,
                "prev_confidence": round(prev_conf, 2),
                "current_confidence": round(cur_conf, 2),
                "status": "cooling",
            })

    # Sort by severity: gone first, then by confidence drop magnitude
    results.sort(key=lambda r: (0 if r["status"] == "gone" else 1, -(r["prev_confidence"] - r["current_confidence"])))
    return results
