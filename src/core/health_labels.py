"""Label and verdict generation for portfolio health checks (KIK-371).

Extracted from health_check.py as part of KIK-512 module split.
Contains long-term investment suitability classification logic.
"""

from src.core.common import is_cash as _is_cash, is_etf as _is_etf, finite_or_none
from src.core._thresholds import th
from src.core.health_etf import check_etf_health

# ---------------------------------------------------------------------------
# Long-term investment suitability thresholds (KIK-371, KIK-446)
# ---------------------------------------------------------------------------
_LT_ROE_HIGH = th("health", "lt_roe_high", 0.15)
_LT_ROE_LOW = th("health", "lt_roe_low", 0.10)
_LT_EPS_GROWTH_HIGH = th("health", "lt_eps_growth_high", 0.10)
_LT_DIVIDEND_HIGH = th("health", "lt_dividend_high", 0.02)
_LT_PER_OVERVALUED = th("health", "lt_per_overvalued", 40)
_LT_PER_SAFE = th("health", "lt_per_safe", 25)


def check_long_term_suitability(
    stock_detail: dict,
    shareholder_return_data: dict | None = None,
) -> dict:
    """Evaluate long-term holding suitability from fundamental data.

    Classifies a holding based on ROE, EPS growth, shareholder return, and PER.

    Parameters
    ----------
    stock_detail : dict
        From yahoo_client.get_stock_detail(). Expected keys:
        roe, eps_growth, dividend_yield, per.
    shareholder_return_data : dict, optional
        From calculate_shareholder_return(). When provided,
        total_return_rate (dividend + buyback) is used instead of
        dividend_yield alone.

    Returns
    -------
    dict
        Keys: label, roe_status, eps_growth_status, dividend_status,
        per_risk, score, summary.
    """
    symbol = stock_detail.get("symbol", "")

    if _is_cash(symbol):
        return {
            "label": "対象外",
            "roe_status": "n/a",
            "eps_growth_status": "n/a",
            "dividend_status": "n/a",
            "per_risk": "n/a",
            "score": 0,
            "summary": "-",
        }

    if _is_etf(stock_detail):
        etf_health = check_etf_health(stock_detail)
        return {
            "label": "対象外",
            "roe_status": "n/a",
            "eps_growth_status": "n/a",
            "dividend_status": "n/a",
            "per_risk": "n/a",
            "score": etf_health["score"],
            "summary": "ETF",
            "etf_health": etf_health,
        }

    roe = finite_or_none(stock_detail.get("roe"))
    eps_growth = finite_or_none(stock_detail.get("eps_growth"))
    dividend_yield = finite_or_none(stock_detail.get("dividend_yield"))
    per = finite_or_none(stock_detail.get("per"))

    # --- ROE classification ---
    if roe is None:
        roe_status = "unknown"
        roe_score = 0
    elif roe >= _LT_ROE_HIGH:
        roe_status = "high"
        roe_score = 2
    elif roe >= _LT_ROE_LOW:
        roe_status = "medium"
        roe_score = 1
    else:
        roe_status = "low"
        roe_score = 0

    # --- EPS Growth classification ---
    if eps_growth is None:
        eps_growth_status = "unknown"
        eps_score = 0
    elif eps_growth >= _LT_EPS_GROWTH_HIGH:
        eps_growth_status = "growing"
        eps_score = 2
    elif eps_growth >= 0:
        eps_growth_status = "flat"
        eps_score = 1
    else:
        eps_growth_status = "declining"
        eps_score = 0

    # --- Shareholder return classification (KIK-403) ---
    # Prefer total return rate (dividend + buyback) if available
    total_return_rate = None
    if shareholder_return_data is not None:
        total_return_rate = finite_or_none(
            shareholder_return_data.get("total_return_rate")
        )
    return_metric = total_return_rate if total_return_rate is not None else dividend_yield
    _used_total_return = total_return_rate is not None

    if return_metric is None:
        dividend_status = "unknown"
        div_score = 0
    elif return_metric >= _LT_DIVIDEND_HIGH:
        dividend_status = "high"
        div_score = 1
    elif return_metric > 0:
        dividend_status = "medium"
        div_score = 0.5
    else:
        dividend_status = "low"
        div_score = 0

    # --- PER risk classification ---
    if per is None:
        per_risk = "unknown"
        per_score = 0
    elif per > _LT_PER_OVERVALUED:
        per_risk = "overvalued"
        per_score = -1
    elif per <= _LT_PER_SAFE:
        per_risk = "safe"
        per_score = 1
    else:
        per_risk = "moderate"
        per_score = 0

    total_score = roe_score + eps_score + div_score + per_score

    # --- Label determination ---
    if (roe_status == "high" and eps_growth_status == "growing"
            and dividend_status == "high"
            and per_risk not in ("overvalued", "unknown")):
        label = "長期向き"
    elif per_risk == "overvalued" or roe_status == "low":
        label = "短期向き"
    else:
        label = "要検討"

    # --- Summary string ---
    parts = []
    if roe_status == "high":
        parts.append("高ROE")
    elif roe_status == "low":
        parts.append("低ROE")
    if eps_growth_status == "growing":
        parts.append("EPS成長")
    elif eps_growth_status == "declining":
        parts.append("EPS減少")
    if dividend_status == "high":
        parts.append("高還元" if _used_total_return else "高配当")
    if per_risk == "overvalued":
        parts.append("割高PER")
    # Count unknown fields for summary
    unknown_count = sum(1 for s in [roe_status, eps_growth_status, dividend_status, per_risk] if s == "unknown")
    if unknown_count > 0:
        parts.append(f"データ不足({unknown_count}項目)")

    summary = "・".join(parts) if parts else "データ不足"

    return {
        "label": label,
        "roe_status": roe_status,
        "eps_growth_status": eps_growth_status,
        "dividend_status": dividend_status,
        "per_risk": per_risk,
        "score": total_score,
        "summary": summary,
    }
