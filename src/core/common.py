"""Shared utility functions used across multiple core modules.

Extracted from portfolio_manager, rebalancer, health_check, return_estimate,
correlation, scenario_analysis, and shock_sensitivity to eliminate duplication.
"""

import math


def is_cash(symbol: str) -> bool:
    """Check if symbol represents a cash position (e.g., JPY.CASH, USD.CASH)."""
    return symbol.upper().endswith(".CASH")


def is_etf(stock_detail: dict) -> bool:
    """Return True if stock_detail looks like an ETF (lacks fundamental data).

    Detection rules (from health_check.py, broadest coverage):
      1. quoteType == "ETF"
      2. No sector AND no net_income_stmt AND no operating_cashflow AND no revenue_history
    """
    if stock_detail.get("quoteType") == "ETF":
        return True
    info = stock_detail.get("info", stock_detail)
    has_sector = bool(info.get("sector"))
    has_net_income = bool(stock_detail.get("net_income_stmt"))
    has_operating_cf = bool(stock_detail.get("operating_cashflow"))
    has_revenue_hist = bool(stock_detail.get("revenue_history"))
    if not has_sector and not has_net_income and not has_operating_cf and not has_revenue_hist:
        return True
    return False


def finite_or_none(v):
    """Return v if finite number, else None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def safe_float(value, default: float = 0.0) -> float:
    """Convert value to float safely, returning default on failure.

    Handles None, NaN, Inf, and non-numeric strings.
    """
    result = finite_or_none(value)
    return result if result is not None else default
