"""Filter functions for stock screening criteria."""

from typing import Optional


def apply_filters(stock_data: dict, criteria: dict) -> bool:
    """Return True if stock_data passes all criteria.

    Supported criteria keys:
      - max_per:            PER upper bound
      - max_pbr:            PBR upper bound
      - min_dividend_yield: Dividend yield lower bound
      - min_roe:            ROE lower bound
      - min_revenue_growth: Revenue growth lower bound

    If a stock_data field is None the corresponding criterion is skipped
    (the stock is not penalised for missing data).
    """
    checks = [
        ("max_per", "per", "max"),
        ("max_pbr", "pbr", "max"),
        ("min_dividend_yield", "dividend_yield", "min"),
        ("min_roe", "roe", "min"),
        ("min_revenue_growth", "revenue_growth", "min"),
        ("min_earnings_growth", "earnings_growth", "min"),
        ("min_market_cap", "market_cap", "min"),
        ("min_total_shareholder_return", "total_shareholder_return", "min"),
    ]

    for criteria_key, data_key, direction in checks:
        if criteria_key not in criteria:
            continue
        value = stock_data.get(data_key)
        if value is None:
            # Skip criterion when data is unavailable
            continue
        threshold = criteria[criteria_key]
        if direction == "max" and value > threshold:
            return False
        if direction == "min" and value < threshold:
            return False

    return True
