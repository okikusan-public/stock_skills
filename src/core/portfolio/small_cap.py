"""Small-cap classification and allocation rules (KIK-438).

Provides region-aware market-cap classification and portfolio-level
small-cap allocation checks.
"""

from src.core._thresholds import th

# Region-specific small-cap thresholds (local currency).
# Values match KIK-437 _SMALL_CAP_MARKET_CAP in screening presets.
_SMALL_CAP_THRESHOLDS: dict[str, float] = {
    "jp": 100_000_000_000,       # 1000億円
    "us": 1_000_000_000,         # $1B
    "sg": 2_000_000_000,         # SGD 2B
    "th": 30_000_000_000,        # THB 30B
    "my": 5_000_000_000,         # MYR 5B
    "id": 15_000_000_000_000,    # IDR 15T
    "ph": 50_000_000_000,        # PHP 50B
    "hk": 10_000_000_000,        # HKD 10B
    "kr": 1_000_000_000_000,     # KRW 1T
    "tw": 30_000_000_000,        # TWD 30B
    "cn": 10_000_000_000,        # CNY 10B
    "gb": 500_000_000,           # GBP 500M
    "de": 1_000_000_000,         # EUR 1B
    "fr": 1_000_000_000,         # EUR 1B
    "ca": 1_000_000_000,         # CAD 1B
    "au": 1_500_000_000,         # AUD 1.5B
    "br": 5_000_000_000,         # BRL 5B
    "in": 100_000_000_000,       # INR 100B
}

# Large-cap threshold = small-cap * multiplier
_LARGE_CAP_MULTIPLIER = 5


def classify_market_cap(market_cap: float | None, region_code: str) -> str:
    """Classify stock size from market cap and region code.

    Returns
    -------
    str
        "小型", "中型", "大型", or "不明"
    """
    if market_cap is None or market_cap <= 0:
        return "不明"
    small_threshold = _SMALL_CAP_THRESHOLDS.get(region_code)
    if small_threshold is None:
        return "不明"
    if market_cap <= small_threshold:
        return "小型"
    if market_cap <= small_threshold * _LARGE_CAP_MULTIPLIER:
        return "中型"
    return "大型"


def check_small_cap_allocation(small_cap_weight: float) -> dict:
    """Check portfolio-level small-cap allocation.

    Returns
    -------
    dict
        {"level": "ok"|"warning"|"critical", "weight": float, "message": str}
    """
    warn_pct = th("health", "small_cap_warn_pct", 0.25)
    crit_pct = th("health", "small_cap_crit_pct", 0.35)

    if small_cap_weight > crit_pct:
        return {
            "level": "critical",
            "weight": small_cap_weight,
            "message": f"小型株比率 {small_cap_weight * 100:.0f}% — 過集中（>{crit_pct * 100:.0f}%）",
        }
    if small_cap_weight > warn_pct:
        return {
            "level": "warning",
            "weight": small_cap_weight,
            "message": f"小型株比率 {small_cap_weight * 100:.0f}% — 注意（>{warn_pct * 100:.0f}%）",
        }
    return {
        "level": "ok",
        "weight": small_cap_weight,
        "message": f"小型株比率 {small_cap_weight * 100:.0f}% — 正常",
    }
