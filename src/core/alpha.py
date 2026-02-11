"""Alpha signal: change score calculation (KIK-346, KIK-349).

Detects stocks with positive fundamental changes that the market
has not yet priced in.  Returns a composite "change score" (0-100)
based on four indicators: accruals quality, revenue growth
acceleration, FCF yield, and ROE improvement trend.

KIK-349 fixes:
  - Accruals: cap at 15 for Utilities/Financial Services (structural bias)
  - Revenue acceleration: require current_growth > 0 (negative shrinking != acceleration)
  - FCF yield: raise thresholds to reduce PER double-counting
  - ROE trend: require latest ROE >= 8% and all periods positive (exclude red→black recovery)
  - Earnings growth penalty: negative growth reduces total change score
"""

import numpy as np
from typing import Optional


# Sectors where depreciation structurally inflates operating CF vs net income
_SECTOR_CAP_ACCRUALS = {"Utilities", "Financial Services"}


# ---------------------------------------------------------------------------
# 1. Accruals (earnings quality) -- 25 pts
# ---------------------------------------------------------------------------

def compute_accruals_score(stock_detail: dict) -> tuple[float, Optional[float]]:
    """Accruals score.  Returns (score, raw_accruals).

    accruals = (net_income - operating_cf) / total_assets
    Lower values indicate higher-quality earnings backed by cash.

    Capped at 15 for Utilities/Financial Services to prevent structural bias.
    """
    net_income = stock_detail.get("net_income_stmt")
    operating_cf = stock_detail.get("operating_cashflow")
    total_assets = stock_detail.get("total_assets")

    if net_income is None or operating_cf is None or total_assets is None:
        return 0.0, None
    if total_assets == 0:
        return 0.0, None

    accruals = (net_income - operating_cf) / total_assets

    if accruals < -0.05:
        score = 25.0
    elif accruals < 0.0:
        score = 20.0
    elif accruals < 0.05:
        score = 15.0
    elif accruals < 0.10:
        score = 10.0
    else:
        score = 0.0

    # KIK-349: Cap for sectors with structurally low accruals
    sector = stock_detail.get("sector") or ""
    if sector in _SECTOR_CAP_ACCRUALS:
        score = min(score, 15.0)

    return score, accruals


# ---------------------------------------------------------------------------
# 2. Revenue growth acceleration -- 25 pts
# ---------------------------------------------------------------------------

def compute_revenue_acceleration_score(stock_detail: dict) -> tuple[float, Optional[float]]:
    """Revenue growth acceleration score.  Returns (score, raw_acceleration).

    Compares current-period revenue growth rate with the prior period's
    growth rate.  A positive acceleration means growth is speeding up.

    KIK-349: Requires current_growth > 0.  Shrinking losses (-20% → -5%)
    are not genuine acceleration.
    """
    rev = stock_detail.get("revenue_history")

    if not rev or len(rev) < 3:
        return 0.0, None

    # rev[0]=latest, rev[1]=one period ago, rev[2]=two periods ago
    rev0, rev1, rev2 = rev[0], rev[1], rev[2]

    if rev0 is None or rev1 is None or rev2 is None:
        return 0.0, None
    if rev1 == 0 or rev2 == 0:
        return 0.0, None

    current_growth = (rev0 - rev1) / abs(rev1)
    previous_growth = (rev1 - rev2) / abs(rev2)
    acceleration = current_growth - previous_growth

    # KIK-349: Guard — negative current growth means no genuine acceleration
    if current_growth < 0:
        return 0.0, acceleration

    if acceleration > 0.10:
        score = 25.0
    elif acceleration > 0.05:
        score = 20.0
    elif acceleration > 0.0:
        score = 15.0
    elif acceleration > -0.05:
        score = 10.0
    else:
        score = 0.0

    return score, acceleration


# ---------------------------------------------------------------------------
# 3. FCF yield -- 25 pts
# ---------------------------------------------------------------------------

def compute_fcf_yield_score(stock_detail: dict) -> tuple[float, Optional[float]]:
    """FCF yield score.  Returns (score, raw_fcf_yield).

    fcf_yield = fcf / market_cap

    KIK-349: Thresholds raised to reduce double-counting with PER
    (low PER already captures "cheap relative to earnings").
    """
    fcf = stock_detail.get("fcf")
    market_cap = stock_detail.get("market_cap")

    if fcf is None or market_cap is None:
        return 0.0, None
    if market_cap == 0:
        return 0.0, None

    fcf_yield = fcf / market_cap

    # KIK-349: Raised thresholds (was 0.10/0.06/0.03/0.0)
    if fcf_yield > 0.12:
        score = 25.0
    elif fcf_yield > 0.08:
        score = 20.0
    elif fcf_yield > 0.05:
        score = 15.0
    elif fcf_yield > 0.02:
        score = 10.0
    else:
        score = 0.0

    return score, fcf_yield


# ---------------------------------------------------------------------------
# 4. ROE improvement trend -- 25 pts
# ---------------------------------------------------------------------------

def compute_roe_trend_score(stock_detail: dict) -> tuple[float, Optional[float]]:
    """ROE improvement trend score.  Returns (score, raw_slope).

    Calculates ROE for three periods and fits a linear regression to
    determine if ROE is improving over time.

    KIK-349: Requires latest ROE >= 8% and all periods positive.
    Excludes red-to-black recovery (normalization, not improvement).
    """
    ni_hist = stock_detail.get("net_income_history")
    eq_hist = stock_detail.get("equity_history")

    if not ni_hist or not eq_hist:
        return 0.0, None
    if len(ni_hist) < 3 or len(eq_hist) < 3:
        return 0.0, None

    # Compute ROE for latest 3 periods
    roes = []
    for i in range(3):
        ni = ni_hist[i]
        eq = eq_hist[i]
        if ni is None or eq is None or eq == 0:
            return 0.0, None
        roes.append(ni / eq)

    # KIK-349: Exclude red→black recovery and low-ROE stocks
    if any(r < 0 for r in roes):
        return 0.0, None
    if roes[0] < 0.08:
        return 0.0, None

    # roes[0]=latest, roes[1]=mid, roes[2]=oldest
    # polyfit expects x in chronological order: oldest -> newest
    y = [roes[2], roes[1], roes[0]]
    x = [0, 1, 2]

    coeffs = np.polyfit(x, y, deg=1)
    slope = float(coeffs[0])

    if slope > 0.03:
        score = 25.0
    elif slope > 0.01:
        score = 20.0
    elif slope > 0.0:
        score = 15.0
    elif slope > -0.01:
        score = 10.0
    else:
        score = 0.0

    return score, slope


# ---------------------------------------------------------------------------
# Composite change score
# ---------------------------------------------------------------------------

_PASS_THRESHOLD = 15.0


def compute_change_score(stock_detail: dict) -> dict:
    """Compute composite change score across all four indicators.

    KIK-349: Adds earnings growth penalty.  Negative earnings growth
    reduces the total change score (up to -20 pts).

    Returns:
        dict with keys:
            change_score     -- aggregate score 0-100
            accruals         -- {"score": float, "raw": Optional[float]}
            revenue_acceleration -- {"score": float, "raw": Optional[float]}
            fcf_yield        -- {"score": float, "raw": Optional[float]}
            roe_trend        -- {"score": float, "raw": Optional[float]}
            earnings_penalty -- penalty applied for negative earnings growth
            passed_count     -- number of indicators scoring >= 15
            quality_pass     -- True if passed_count >= 3
    """
    acc_score, acc_raw = compute_accruals_score(stock_detail)
    rev_score, rev_raw = compute_revenue_acceleration_score(stock_detail)
    fcf_score, fcf_raw = compute_fcf_yield_score(stock_detail)
    roe_score, roe_raw = compute_roe_trend_score(stock_detail)

    # KIK-349: Earnings growth penalty
    earnings_growth = stock_detail.get("earnings_growth")
    penalty = 0.0
    if earnings_growth is not None and earnings_growth < 0:
        if earnings_growth < -0.20:
            penalty = -20.0
        elif earnings_growth < -0.10:
            penalty = -15.0
        else:
            penalty = -10.0

    total = acc_score + rev_score + fcf_score + roe_score + penalty
    total = max(total, 0.0)  # Floor at 0

    passed = sum(
        1 for s in [acc_score, rev_score, fcf_score, roe_score]
        if s >= _PASS_THRESHOLD
    )

    return {
        "change_score": total,
        "accruals": {"score": acc_score, "raw": acc_raw},
        "revenue_acceleration": {"score": rev_score, "raw": rev_raw},
        "fcf_yield": {"score": fcf_score, "raw": fcf_raw},
        "roe_trend": {"score": roe_score, "raw": roe_raw},
        "earnings_penalty": penalty,
        "passed_count": passed,
        "quality_pass": passed >= 3,
    }
