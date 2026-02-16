"""Financial indicators and value-score calculation."""

from typing import Optional


def is_undervalued_per(per: Optional[float], threshold: float = 15.0) -> bool:
    """Return True if PER indicates undervaluation (0 < per < threshold)."""
    if per is None:
        return False
    return 0 < per < threshold


def is_undervalued_pbr(pbr: Optional[float], threshold: float = 1.0) -> bool:
    """Return True if PBR indicates undervaluation (0 < pbr < threshold)."""
    if pbr is None:
        return False
    return 0 < pbr < threshold


def has_good_dividend(dividend_yield: Optional[float], min_yield: float = 0.03) -> bool:
    """Return True if dividend yield meets the minimum threshold."""
    if dividend_yield is None:
        return False
    return dividend_yield >= min_yield


def has_good_roe(roe: Optional[float], min_roe: float = 0.08) -> bool:
    """Return True if ROE meets the minimum threshold."""
    if roe is None:
        return False
    return roe >= min_roe


def _score_per(per: Optional[float], per_max: float) -> float:
    """PER score (25 points max). Lower PER = higher score."""
    if per is None or per <= 0:
        return 0.0
    if per >= per_max * 2:
        return 0.0
    # Linear: PER == 0 -> 25, PER == per_max*2 -> 0
    score = max(0.0, 25.0 * (1.0 - per / (per_max * 2)))
    return round(score, 2)


def _score_pbr(pbr: Optional[float], pbr_max: float) -> float:
    """PBR score (25 points max). Lower PBR = higher score."""
    if pbr is None or pbr <= 0:
        return 0.0
    if pbr >= pbr_max * 2:
        return 0.0
    score = max(0.0, 25.0 * (1.0 - pbr / (pbr_max * 2)))
    return round(score, 2)


def _score_dividend(dividend_yield: Optional[float], div_min: float) -> float:
    """Dividend yield score (20 points max). Higher yield = higher score."""
    if dividend_yield is None or dividend_yield <= 0:
        return 0.0
    # Cap at div_min * 3 for max score
    cap = div_min * 3
    ratio = min(dividend_yield / cap, 1.0)
    return round(20.0 * ratio, 2)


def _score_roe(roe: Optional[float], roe_min: float) -> float:
    """ROE score (15 points max). Higher ROE = higher score."""
    if roe is None or roe <= 0:
        return 0.0
    # Cap at roe_min * 3 for max score
    cap = roe_min * 3
    ratio = min(roe / cap, 1.0)
    return round(15.0 * ratio, 2)


def _score_growth(revenue_growth: Optional[float]) -> float:
    """Revenue growth score (15 points max). Higher growth = higher score."""
    if revenue_growth is None:
        return 0.0
    if revenue_growth <= 0:
        return 0.0
    # Cap at 30% growth for max score
    cap = 0.30
    ratio = min(revenue_growth / cap, 1.0)
    return round(15.0 * ratio, 2)


def calculate_value_score(stock_data: dict, thresholds: Optional[dict] = None) -> float:
    """Calculate a composite value score (0-100) for a stock.

    Breakdown:
      - PER undervaluation:  25 points
      - PBR undervaluation:  25 points
      - Dividend yield:      20 points
      - ROE:                 15 points
      - Revenue growth:      15 points

    Parameters
    ----------
    stock_data : dict
        Keys: 'trailingPE' (or 'per'), 'priceToBook' (or 'pbr'),
              'dividendYield' (or 'dividend_yield'),
              'returnOnEquity' (or 'roe'), 'revenueGrowth' (or 'revenue_growth').
    thresholds : dict, optional
        Keys: 'per_max', 'pbr_max', 'dividend_yield_min', 'roe_min'.
    """
    if thresholds is None:
        thresholds = {}

    per_max = thresholds.get("per_max", 15.0)
    pbr_max = thresholds.get("pbr_max", 1.0)
    div_min = thresholds.get("dividend_yield_min", 0.03)
    roe_min = thresholds.get("roe_min", 0.08)

    # Support both yahoo raw keys and our normalised keys
    per = stock_data.get("trailingPE") or stock_data.get("per")
    pbr = stock_data.get("priceToBook") or stock_data.get("pbr")
    # Prefer trailing (actual) dividend yield, fallback to forward/predicted
    div_yield = (
        stock_data.get("dividend_yield_trailing")
        or stock_data.get("dividendYield")
        or stock_data.get("dividend_yield")
    )
    roe = stock_data.get("returnOnEquity") or stock_data.get("roe")
    growth = stock_data.get("revenueGrowth") or stock_data.get("revenue_growth")

    total = (
        _score_per(per, per_max)
        + _score_pbr(pbr, pbr_max)
        + _score_dividend(div_yield, div_min)
        + _score_roe(roe, roe_min)
        + _score_growth(growth)
    )
    return round(min(total, 100.0), 2)


def calculate_shareholder_return_history(stock: dict) -> list[dict]:
    """Calculate shareholder return for multiple fiscal years.

    Uses ``dividend_paid_history``, ``stock_repurchase_history``, and
    ``cashflow_fiscal_years`` from yahoo_client's ``get_stock_detail``.

    Returns a list of dicts (latest-first), each containing:
        fiscal_year, dividend_paid, stock_repurchase,
        total_return_amount, total_return_rate.

    Falls back to current single-period data if history is unavailable.
    """
    market_cap = stock.get("market_cap")
    div_hist: list[float] = stock.get("dividend_paid_history") or []
    rep_hist: list[float] = stock.get("stock_repurchase_history") or []
    fiscal_years: list[int] = stock.get("cashflow_fiscal_years") or []

    if not div_hist and not rep_hist:
        return []

    n = max(len(div_hist), len(rep_hist))
    results: list[dict] = []
    for i in range(n):
        div_raw = div_hist[i] if i < len(div_hist) else None
        rep_raw = rep_hist[i] if i < len(rep_hist) else None
        fy = fiscal_years[i] if i < len(fiscal_years) else None

        dividend_paid = abs(div_raw) if div_raw is not None else None
        stock_repurchase = abs(rep_raw) if rep_raw is not None else None

        total: Optional[float] = None
        if dividend_paid is not None or stock_repurchase is not None:
            total = (dividend_paid or 0.0) + (stock_repurchase or 0.0)

        total_rate: Optional[float] = None
        if market_cap is not None and market_cap > 0 and total is not None:
            total_rate = total / market_cap

        results.append({
            "fiscal_year": fy,
            "dividend_paid": dividend_paid,
            "stock_repurchase": stock_repurchase,
            "total_return_amount": total,
            "total_return_rate": total_rate,
        })

    return results


def assess_return_stability(history: list[dict]) -> dict:
    """Assess shareholder return stability from multi-year history.

    Takes the output of ``calculate_shareholder_return_history()`` and
    classifies stability as one of:

    - ``temporary``: Latest year surged (>=2x previous) — likely one-off
    - ``increasing``: Rates rising year-over-year
    - ``decreasing``: Rates falling year-over-year
    - ``stable``: All years >= 5%
    - ``mixed``: None of the above patterns
    - ``unknown``: Insufficient data (< 2 years with rates)

    Returns dict with keys: stability, label, latest_rate, avg_rate.
    """
    rates = [
        e.get("total_return_rate")
        for e in history
        if e.get("total_return_rate") is not None
    ]

    if len(rates) < 2:
        return {
            "stability": "unknown",
            "label": "❓ データ不足",
            "latest_rate": rates[0] if rates else None,
            "avg_rate": rates[0] if rates else None,
        }

    latest = rates[0]
    prev = rates[1]
    avg_rate = sum(rates) / len(rates)

    # Temporary: latest surged >= 2x previous AND is genuinely high (>= 8%)
    if prev > 0 and latest / prev >= 2.0 and latest >= 0.08:
        return {
            "stability": "temporary",
            "label": "⚠️ 一時的高還元",
            "latest_rate": latest,
            "avg_rate": avg_rate,
        }

    # Increasing: all years non-decreasing (latest first order)
    if all(rates[i] >= rates[i + 1] for i in range(len(rates) - 1)):
        return {
            "stability": "increasing",
            "label": "📈 増加傾向",
            "latest_rate": latest,
            "avg_rate": avg_rate,
        }

    # Decreasing: all years non-increasing
    if all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1)):
        return {
            "stability": "decreasing",
            "label": "📉 減少傾向",
            "latest_rate": latest,
            "avg_rate": avg_rate,
        }

    # Stable: all >= 5%
    if all(r >= 0.05 for r in rates):
        return {
            "stability": "stable",
            "label": "✅ 安定高還元",
            "latest_rate": latest,
            "avg_rate": avg_rate,
        }

    return {
        "stability": "mixed",
        "label": "➡️ 変動あり",
        "latest_rate": latest,
        "avg_rate": avg_rate,
    }


def calculate_shareholder_return(stock: dict) -> dict:
    """Calculate total shareholder return rate.

    Formula: (|dividend_paid| + |stock_repurchase|) / market_cap

    Cashflow values from yfinance are negative (outflows), so abs() is applied.

    Returns a dict with rates as ratios (e.g. 0.05 = 5%).
    """
    market_cap = stock.get("market_cap")
    div_raw = stock.get("dividend_paid")
    rep_raw = stock.get("stock_repurchase")

    dividend_paid = abs(div_raw) if div_raw is not None else None
    stock_repurchase = abs(rep_raw) if rep_raw is not None else None

    total: float | None = None
    if dividend_paid is not None or stock_repurchase is not None:
        total = (dividend_paid or 0.0) + (stock_repurchase or 0.0)

    total_rate: float | None = None
    buyback_yield: float | None = None
    if market_cap is not None and market_cap > 0:
        if total is not None:
            total_rate = total / market_cap
        if stock_repurchase is not None:
            buyback_yield = stock_repurchase / market_cap

    # Prefer trailing (actual) dividend yield, fallback to forward/predicted
    div_yield = stock.get("dividend_yield_trailing") or stock.get("dividend_yield")

    return {
        "dividend_paid": dividend_paid,
        "stock_repurchase": stock_repurchase,
        "total_return_amount": total,
        "total_return_rate": total_rate,
        "dividend_yield": div_yield,
        "buyback_yield": buyback_yield,
    }
