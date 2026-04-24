"""3-axis quality scoring for stocks (KIK-708).

Scores each stock on three independent axes (0-10):
  - Return:     Shareholder yield + earnings coverage + consistency
  - Growth:     Organic growth + ROIC + cash conversion + runway + capital allocation
  - Durability: Financial robustness + earnings durability + model resilience + liquidity

Formula v3.1 — finalized through 4-LLM × 3-round debate + 5-agent review.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Optional

import yaml

from src.data.common import safe_float, is_etf

# ---------------------------------------------------------------------------
# Config loading (cached at module level)
# ---------------------------------------------------------------------------

_CONFIG: dict | None = None


def _load_config() -> dict:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    # __file__ = src/data/scoring.py → parent.parent.parent = project root
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "scoring.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        _CONFIG = yaml.safe_load(f)
    return _CONFIG


def _reset_config() -> None:
    """Reset cached config (for testing)."""
    global _CONFIG
    _CONFIG = None


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, value))


def _normalize_de(value) -> float | None:
    """Return D/E as percentage. yfinance always returns percentage form
    (e.g., 7.255 = 7.255%, 105.0 = 105%) per docs/data-models.md.
    No heuristic conversion — KIK-709 removed the < 10 detection that
    misclassified low-leverage stocks like NVDA (7.2%) and AUTO.JK (3.5%).
    """
    if value is None:
        return None
    return safe_float(value)


# ---------------------------------------------------------------------------
# Return Score (還元性) v3.1
# ---------------------------------------------------------------------------

def score_return(
    info: dict,
    portfolio_entry: dict | None = None,
    durability_score: float | None = None,
) -> dict:
    """Score shareholder return quality (0-10).

    Parameters
    ----------
    info : dict
        Output of get_stock_info().
    portfolio_entry : dict | None
        Row from portfolio.csv (has div_yield, buyback_yield, total_return).
    durability_score : float | None
        Pre-computed durability score for cap rule application.
    """
    cfg = _load_config()
    w = cfg["weights"]["return"]
    thr = cfg["thresholds"]

    # A: Shareholder Yield
    if portfolio_entry:
        div_y = safe_float(portfolio_entry.get("div_yield"))
        bb_y = safe_float(portfolio_entry.get("buyback_yield"))
    else:
        div_y = safe_float(info.get("dividend_yield")) * 100  # ratio → %
        bb_y = 0.0
    total_yield = div_y + bb_y

    # Zero-dividend rule: yield < threshold → A only
    zero_threshold = thr.get("zero_div_yield", 1.0)
    if total_yield < zero_threshold:
        score = _clamp(total_yield)  # 0-10, yield% = score directly
        return {"score": round(score, 1), "A": round(score, 1),
                "B": 0.0, "C": 0.0, "capped": False}

    a_score = _clamp(total_yield)  # 10% cap → score 10

    # B: Earnings Coverage (1 / payout_ratio)
    payout = safe_float(info.get("payout_ratio"))
    if payout and payout > 0:
        cap = thr.get("coverage_cap", 3.0)
        coverage = min(1.0 / payout, cap)
        b_score = _clamp(coverage / cap * 10)
    else:
        b_score = 5.0  # no data → neutral

    # C: Consistency (payout health)
    if payout and payout > 0:
        if payout < 0.5:
            c_score = 10.0
        elif payout < 0.8:
            c_score = 6.0
        else:
            c_score = 2.0
    else:
        c_score = 5.0  # no data → neutral

    raw = w["yield"] * a_score + w["coverage"] * b_score + w["consistency"] * c_score
    score = _clamp(raw)

    # Cap rule: durability < threshold → return capped
    capped = False
    if durability_score is not None:
        for rule in thr.get("cap_rules", []):
            if durability_score < rule["durability_below"] and score > rule["return_max"]:
                score = rule["return_max"]
                capped = True
                break

    return {"score": round(score, 1), "A": round(a_score, 1),
            "B": round(b_score, 1), "C": round(c_score, 1), "capped": capped}


# ---------------------------------------------------------------------------
# Growth Score (成長性) v3.1
# ---------------------------------------------------------------------------

def score_growth(
    info: dict,
    detail: dict | None = None,
    overrides: dict | None = None,
) -> dict:
    """Score growth quality (0-10).

    Parameters
    ----------
    info : dict
        Output of get_stock_info().
    detail : dict | None
        Output of get_stock_detail() (for operating_income_history, depreciation).
    overrides : dict | None
        Manual overrides, e.g. {"runway": 8, "acquisition_flag": True}.
    """
    cfg = _load_config()
    w = cfg["weights"]["growth"]
    thr = cfg["thresholds"]
    overrides = overrides or {}

    # A: Normalized Organic Growth = max(EG, RG), capped
    eg = safe_float(info.get("earnings_growth")) * 100
    rg = safe_float(info.get("revenue_growth")) * 100
    organic = max(eg, rg)
    cap = thr.get("organic_growth_cap", 30)

    if overrides.get("acquisition_flag"):
        organic *= 0.5

    organic = min(organic, cap)
    a_score = _clamp(max(0, organic) / (cap / 10))  # 30%=10

    # B: ROIC (ROA as proxy)
    roa = safe_float(info.get("roa")) * 100
    roic_cap = thr.get("roic_cap", 30)
    b_score = _clamp(max(0, roa) / (roic_cap / 10))

    # C: Adjusted Cash Conversion = (OCF - depreciation) / NOPAT
    c_score = 5.0  # default neutral
    if detail:
        ocf = safe_float(detail.get("operating_cashflow"))
        dep = safe_float(detail.get("depreciation"))
        ni = safe_float(detail.get("net_income_stmt"))
        dep_abs = abs(dep) if dep else 0

        if ni > 0 and ocf > 0:
            adj_cf = (ocf - dep_abs) / ni
            c_score = _clamp(adj_cf * 5)  # 2.0x = 10

    # D: Growth Runway (sector default or override)
    runway_cfg = cfg.get("growth_runway", {})
    sector = info.get("sector") or ""
    sector_defaults = runway_cfg.get("sector_defaults", {})
    fallback = runway_cfg.get("fallback", 4)
    d_score = float(overrides.get("runway", sector_defaults.get(sector, fallback)))

    # E: Capital Allocation (buyback yield)
    bb_y = safe_float(overrides.get("buyback_yield"))
    e_score = _clamp(bb_y * 1.5 + 2)  # base 2 + buyback bonus

    raw = (w["organic"] * a_score + w["roic"] * b_score +
           w["cashflow"] * c_score + w["runway"] * d_score +
           w["capital"] * e_score)

    # Asymmetric beta stability multiplier
    beta = info.get("beta")
    beta_cfg = cfg.get("stability_beta", {})
    if beta is not None:
        beta_val = safe_float(beta)
        if beta_val < 1:
            coeff = beta_cfg.get("low_beta_coeff", 0.05)
            floor = beta_cfg.get("low_beta_floor", 0.90)
            multiplier = max(floor, 1 - (1 - beta_val) * coeff)
        else:
            coeff = beta_cfg.get("high_beta_coeff", 0.20)
            floor = beta_cfg.get("high_beta_floor", 0.75)
            multiplier = max(floor, 1 - (beta_val - 1) * coeff)
    else:
        multiplier = 1.0

    score = _clamp(raw * multiplier)

    return {"score": round(score, 1), "raw": round(raw, 1),
            "multiplier": round(multiplier, 3),
            "A": round(a_score, 1), "B": round(b_score, 1),
            "C": round(c_score, 1), "D": round(d_score, 1),
            "E": round(e_score, 1)}


# ---------------------------------------------------------------------------
# Durability Score (持続性) v3.1
# ---------------------------------------------------------------------------

def score_durability(info: dict, detail: dict | None = None) -> dict:
    """Score business durability (0-10).

    Parameters
    ----------
    info : dict
        Output of get_stock_info().
    detail : dict | None
        Output of get_stock_detail() (for operating_income_history, interest_expense).
    """
    cfg = _load_config()
    w = cfg["weights"]["durability"]
    thr = cfg["thresholds"]
    de_cfg = thr.get("de_penalty", {})

    # A: Financial Robustness (interest coverage)
    a_score = 7.0  # default (no data or no debt)
    if detail:
        interest = detail.get("interest_expense")
        total_debt = safe_float(info.get("total_debt", detail.get("total_debt")))

        if interest is not None and interest != 0:
            op_hist = detail.get("operating_income_history", [])
            if op_hist:
                ebit = op_hist[0]
            else:
                op_margin = safe_float(info.get("operating_margin"))
                rev_hist = detail.get("revenue_history", [])
                revenue = rev_hist[0] if rev_hist else 0
                ebit = op_margin * revenue if op_margin and revenue else 0

            if ebit > 0:
                int_cov = min(abs(ebit / interest), 20)
                a_score = _clamp(int_cov / 2)  # 20x=10, 10x=5
        elif total_debt == 0 or total_debt is None:
            a_score = 10.0  # no debt

    # D/E penalty on A (using normalized D/E)
    de_val = _normalize_de(info.get("debt_to_equity"))
    de_penalty_applied = None
    if de_val is not None:
        if de_val > de_cfg.get("level2", 200):
            a_score = min(a_score, 3.0)
            de_penalty_applied = ">200%"
        elif de_val > de_cfg.get("level1", 100):
            a_score = min(a_score, 5.0)
            de_penalty_applied = ">100%"

    # B: Earnings Durability (operating margin × stability, 3-year average)
    op_margin = safe_float(info.get("operating_margin")) * 100
    stability = 1.0

    if detail:
        op_hist = detail.get("operating_income_history", [])
        rev_hist = detail.get("revenue_history", [])
        if len(op_hist) >= 2 and len(rev_hist) >= 2:
            min_len = min(len(op_hist), len(rev_hist))
            margins = []
            for i in range(min_len):
                if rev_hist[i] and rev_hist[i] != 0:
                    margins.append(op_hist[i] / rev_hist[i] * 100)
            if len(margins) >= 2:
                op_margin = statistics.mean(margins)
                mu = statistics.mean(margins)
                if mu > 0:
                    sigma = statistics.stdev(margins)
                    cv = sigma / mu
                    stability = 1 / (1 + cv)
                else:
                    stability = 0.0

    # KIK-709: Industry-aware margin divisor
    sector = info.get("sector") or ""
    industry = info.get("industry") or ""
    industry_divisors = cfg.get("industry_divisors", {})
    divisor = industry_divisors.get(industry)
    if divisor is None:
        # Sector-level fallback
        if "Tech" in sector or "Communication" in sector:
            divisor = 6  # high-margin software/platform
        elif "Energy" in sector or "Financial" in sector:
            divisor = 4
        else:
            divisor = 2
    b_raw = op_margin / divisor

    b_score = _clamp(b_raw * stability)

    # C: Business Model Resilience (margin maintenance years)
    c_score = 5.0
    if detail:
        op_hist = detail.get("operating_income_history", [])
        if len(op_hist) >= 2:
            maintained = sum(1 for i in range(1, len(op_hist))
                             if op_hist[i - 1] >= op_hist[i] * 0.9)
            total_comparisons = len(op_hist) - 1
            if total_comparisons > 0:
                c_score = _clamp(maintained / total_comparisons * 10)

    # D: Liquidity (current ratio)
    cr = safe_float(info.get("current_ratio"))
    if cr > 2.5:
        d_score = 9.0
    elif cr > 1.5:
        d_score = 7.0
    elif cr > 1.0:
        d_score = 5.0
    elif cr > 0:
        d_score = 3.0
    else:
        d_score = 5.0

    raw = (w["financial"] * a_score + w["earnings"] * b_score +
           w["model"] * c_score + w["liquidity"] * d_score)

    # D/E hard cap: >250% → durability total ≤ 3
    hard_cap = de_cfg.get("hard_cap", 250)
    if de_val is not None and de_val > hard_cap:
        raw = min(raw, 3.0)
        de_penalty_applied = f">{hard_cap}% hard cap"

    score = _clamp(raw)

    # KIK-709: Quarterly warning — TTM margin vs annual average divergence
    quarterly_warning = None
    ttm_margin = safe_float(info.get("operating_margin")) * 100
    if op_margin > 0 and ttm_margin > 0:
        divergence = (ttm_margin - op_margin) / op_margin
        if divergence < -0.20:  # TTM is 20%+ below annual average
            quarterly_warning = f"TTM margin {ttm_margin:.1f}% vs avg {op_margin:.1f}% ({divergence*100:+.0f}%)"

    return {"score": round(score, 1), "A": round(a_score, 1),
            "B": round(b_score, 1), "C": round(c_score, 1),
            "D": round(d_score, 1), "de_penalty": de_penalty_applied,
            "quarterly_warning": quarterly_warning}


# ---------------------------------------------------------------------------
# Integrated Quality Score
# ---------------------------------------------------------------------------

def _classify_quadrant(
    total: float,
    ret: float,
    growth: float,
    durability: float,
    capped: bool,
    cfg: dict,
) -> str:
    """Classify into one of 4 quadrants (priority order, exclusive)."""
    q = cfg.get("quadrants", {})

    sell_cfg = q.get("sell", {})
    if durability < sell_cfg.get("durability_below", 3) or capped:
        return "売却検討"

    watch_cfg = q.get("watch", {})
    if (durability < watch_cfg.get("durability_below", 5)
            or total < watch_cfg.get("total_below", 5)):
        return "要監視"

    add_cfg = q.get("add", {})
    axes_min = add_cfg.get("all_axes_min", 4)
    if (total >= add_cfg.get("total_min", 7)
            and ret >= axes_min and growth >= axes_min and durability >= axes_min):
        return "買い増し"

    return "保有継続"


def _compute_total(
    info: dict,
    detail: dict | None,
    portfolio_entry: dict | None = None,
    growth_overrides: dict | None = None,
) -> dict:
    """Shared scoring pipeline: durability → return (cap) → growth → total → quadrant."""
    cfg = _load_config()

    dur_result = score_durability(info, detail)
    ret_result = score_return(info, portfolio_entry=portfolio_entry,
                              durability_score=dur_result["score"])
    growth_result = score_growth(info, detail, overrides=growth_overrides)

    tw = cfg["weights"]["total"]
    total = (tw["durability"] * dur_result["score"] +
             tw["growth"] * growth_result["score"] +
             tw["return"] * ret_result["score"])
    total = round(_clamp(total), 1)

    quadrant = _classify_quadrant(
        total, ret_result["score"], growth_result["score"],
        dur_result["score"], ret_result["capped"], cfg,
    )

    return {
        "return": ret_result["score"],
        "growth": growth_result["score"],
        "durability": dur_result["score"],
        "total": total,
        "quadrant": quadrant,
        "components": {
            "return_detail": ret_result,
            "growth_detail": growth_result,
            "durability_detail": dur_result,
        },
    }


def score_quality(symbol: str) -> dict:
    """Compute 3-axis quality score for a single symbol.

    Calls get_stock_info() and get_stock_detail() internally.
    """
    from src.data.yahoo_client import get_stock_info, get_stock_detail

    info = get_stock_info(symbol)
    if info is None:
        return {"symbol": symbol, "error": "データ取得失敗"}

    detail = get_stock_detail(symbol)

    if detail and is_etf(detail):
        return {"symbol": symbol, "score": None, "note": "ETF: 別枠"}

    result = _compute_total(info, detail)
    result["symbol"] = symbol
    return result


def score_portfolio() -> list[dict]:
    """Score all portfolio holdings and return sorted by total score (desc)."""
    from src.data.portfolio_io import load_portfolio
    from src.data.yahoo_client import get_stock_info, get_stock_detail

    positions = load_portfolio()
    results = []

    for pos in positions:
        symbol = pos["symbol"]
        info = get_stock_info(symbol)
        if info is None:
            results.append({"symbol": symbol, "error": "データ取得失敗"})
            continue

        detail = get_stock_detail(symbol)

        if detail and is_etf(detail):
            results.append({"symbol": symbol, "score": None, "note": "ETF: 別枠"})
            continue

        result = _compute_total(
            info, detail,
            portfolio_entry=pos,
            growth_overrides={"buyback_yield": safe_float(pos.get("buyback_yield"))},
        )
        result["symbol"] = symbol
        result["role"] = pos.get("role", "")
        # Remove detailed components for portfolio-level output
        result.pop("components", None)
        results.append(result)

    results.sort(key=lambda r: r.get("total", -1), reverse=True)
    return results
