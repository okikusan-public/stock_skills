"""Portfolio return estimation with 3 scenarios (KIK-359).

Estimates portfolio returns across optimistic/base/pessimistic scenarios
using two methods:
- Stocks with analyst coverage: target price-based returns
- ETFs (no analyst coverage): historical percentile-based returns

Per-stock estimates accept optional x_sentiment for /market-research deep-dives,
but portfolio-level estimation does not call Grok API (KIK-369).
"""

import math
from typing import Optional

from src.core.common import is_etf as _is_etf_base

try:
    from src.core.health_check import _detect_value_trap
    HAS_VALUE_TRAP = True
except ImportError:
    HAS_VALUE_TRAP = False

# Historical return estimation thresholds
RETURN_CAP = 0.30  # Max annualized return cap (±30%)
MIN_SPREAD = 0.05  # Minimum spread for optimistic/pessimistic scenarios



def _is_etf(stock_detail: dict) -> bool:
    """Check if a symbol is likely an ETF (no analyst coverage).

    Extends the common is_etf() with an additional check: stocks that
    have analyst target prices are never treated as ETFs for return
    estimation purposes (they use the analyst method instead).
    """
    if stock_detail.get("target_mean_price") is not None:
        return False
    return _is_etf_base(stock_detail)


def _compute_buyback_yield(stock_detail: dict) -> float:
    """Compute buyback yield from cashflow data. Returns 0.0 if unavailable."""
    repurchase = stock_detail.get("stock_repurchase")
    market_cap = stock_detail.get("market_cap")
    if repurchase is None or market_cap is None or market_cap <= 0:
        return 0.0
    return abs(repurchase) / market_cap


def _estimate_from_analyst(stock_detail: dict) -> dict:
    """Estimate returns from analyst target prices.

    Formula:
        scenario_return = (target_price - current_price) / current_price + shareholder_yield
        shareholder_yield = dividend_yield + buyback_yield

    Returns
    -------
    dict
        {"optimistic": float, "base": float, "pessimistic": float,
         "method": "analyst", "analyst_count": int|None,
         "target_high": float|None, "target_mean": float|None, "target_low": float|None,
         "recommendation_mean": float|None, "forward_per": float|None}
    """
    price = stock_detail.get("price")
    if not price or price <= 0:
        return _empty_estimate("analyst")

    target_high = stock_detail.get("target_high_price")
    target_mean = stock_detail.get("target_mean_price")
    target_low = stock_detail.get("target_low_price")
    dividend_yield = stock_detail.get("dividend_yield") or 0.0
    buyback_yield = _compute_buyback_yield(stock_detail)
    shareholder_yield = dividend_yield + buyback_yield

    optimistic = None
    base = None
    pessimistic = None

    if target_high is not None:
        optimistic = (target_high - price) / price + shareholder_yield
    if target_mean is not None:
        base = (target_mean - price) / price + shareholder_yield
    if target_low is not None:
        pessimistic = (target_low - price) / price + shareholder_yield

    # Extract analyst count early (needed for spread logic below)
    analyst_count_val = stock_detail.get("number_of_analyst_opinions")
    analyst_count = int(analyst_count_val) if analyst_count_val is not None else None

    # Fallback: if some targets are missing, use available ones
    if base is None and optimistic is not None and pessimistic is not None:
        base = (optimistic + pessimistic) / 2
    if optimistic is None and base is not None:
        optimistic = base * 1.5 if base > 0 else base * 0.5
    if pessimistic is None and base is not None:
        pessimistic = base * 0.5 if base > 0 else base * 1.5

    # Spread fix: when all targets are identical or too few analysts,
    # generate meaningful spread around base
    if base is not None and optimistic is not None and pessimistic is not None:
        if optimistic == pessimistic or (analyst_count is not None and analyst_count < 3):
            optimistic = base * 1.2 if base > 0 else base * 0.8
            pessimistic = base * 0.8 if base > 0 else base * 1.2

    return {
        "optimistic": optimistic,
        "base": base,
        "pessimistic": pessimistic,
        "method": "analyst",
        "analyst_count": analyst_count,
        "target_high": target_high,
        "target_mean": target_mean,
        "target_low": target_low,
        "recommendation_mean": stock_detail.get("recommendation_mean"),
        "forward_per": stock_detail.get("forward_per"),
    }


def _estimate_from_history(stock_detail: dict) -> dict:
    """Estimate returns from historical price data (for ETFs).

    Uses CAGR (Compound Annual Growth Rate) from the full price history
    as the base case, with ±1 standard deviation spread for scenarios.
    Dividends are already reflected in yfinance's adjusted close prices,
    so dividend_yield is not added.

    Formula:
        base        = CAGR = (end/start)^(12/months) - 1
        optimistic  = base + annualized_std
        pessimistic = base - annualized_std

    Returns
    -------
    dict
        {"optimistic": float, "base": float, "pessimistic": float,
         "method": "historical", ...}
    """
    price_history = stock_detail.get("price_history")

    if not price_history or len(price_history) < 22:
        # Not enough data (need at least ~1 month of daily prices)
        return _empty_estimate("historical")

    # Compute monthly returns (~21 trading days per month)
    monthly_returns = []
    step = 21
    for i in range(step, len(price_history), step):
        prev = price_history[i - step]
        curr = price_history[i]
        if prev > 0:
            monthly_returns.append((curr - prev) / prev)

    if not monthly_returns:
        return _empty_estimate("historical")

    n = len(monthly_returns)

    # CAGR: annualized total return over the full period
    start_price = price_history[0]
    end_price = price_history[-1]
    if start_price <= 0:
        return _empty_estimate("historical")

    total_months = n  # approximate months of data
    total_return = end_price / start_price
    if total_months > 0 and total_return > 0:
        cagr = total_return ** (12.0 / total_months) - 1
    else:
        cagr = 0.0

    # Annualized volatility from monthly returns (std * sqrt(12))
    mean_monthly = sum(monthly_returns) / n
    variance = sum((r - mean_monthly) ** 2 for r in monthly_returns) / max(n - 1, 1)
    monthly_std = math.sqrt(variance)
    annual_std = monthly_std * math.sqrt(12)

    # Scenarios: base +/- 1 standard deviation, capped at RETURN_CAP
    spread = max(MIN_SPREAD, annual_std) if annual_std > 0 else MIN_SPREAD
    base = max(-RETURN_CAP, min(RETURN_CAP, cagr))
    optimistic = min(RETURN_CAP, base + spread)
    pessimistic = max(-RETURN_CAP, base - spread)

    # If base is at cap, shift down to make room for spread
    if optimistic == base:
        base = optimistic - spread
        pessimistic = base - spread

    return {
        "optimistic": optimistic,
        "base": base,
        "pessimistic": pessimistic,
        "method": "historical",
        "analyst_count": None,
        "target_high": None,
        "target_mean": None,
        "target_low": None,
        "recommendation_mean": None,
        "forward_per": None,
        "data_months": n,
    }


def _empty_estimate(method: str) -> dict:
    """Return an empty estimate dict."""
    return {
        "optimistic": None,
        "base": None,
        "pessimistic": None,
        "method": method,
        "analyst_count": None,
        "target_high": None,
        "target_mean": None,
        "target_low": None,
        "recommendation_mean": None,
        "forward_per": None,
    }


def estimate_stock_return(
    symbol: str,
    stock_detail: dict,
    news: Optional[list] = None,
    x_sentiment: Optional[dict] = None,
) -> dict:
    """Estimate return for a single stock/ETF.

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    stock_detail : dict
        Output from yahoo_client.get_stock_detail().
    news : list, optional
        News items from yahoo_client.get_stock_news().
    x_sentiment : dict, optional
        Sentiment data from grok_client.search_x_sentiment().

    Returns
    -------
    dict
        {
            "symbol": str,
            "name": str,
            "price": float,
            "currency": str,
            "optimistic": float|None,
            "base": float|None,
            "pessimistic": float|None,
            "method": "analyst"|"historical",
            "analyst_count": int|None,
            "target_high": float|None,
            "target_mean": float|None,
            "target_low": float|None,
            "recommendation_mean": float|None,
            "forward_per": float|None,
            "dividend_yield": float|None,
            "news": list,
            "x_sentiment": dict|None,
        }
    """
    if _is_etf(stock_detail):
        estimate = _estimate_from_history(stock_detail)
    else:
        estimate = _estimate_from_analyst(stock_detail)
        # Fallback: if analyst method produced no estimates (no coverage),
        # try historical method if price_history is available
        if estimate.get("base") is None and stock_detail.get("price_history"):
            estimate = _estimate_from_history(stock_detail)

    # Value trap warning (KIK-381)
    value_trap_warning = None
    if HAS_VALUE_TRAP:
        vt = _detect_value_trap(stock_detail)
        if vt["is_trap"]:
            value_trap_warning = "\u3001".join(vt["reasons"])

    return {
        "symbol": symbol,
        "name": stock_detail.get("name") or "",
        "price": stock_detail.get("price"),
        "currency": stock_detail.get("currency") or "USD",
        "dividend_yield": stock_detail.get("dividend_yield"),
        "buyback_yield": _compute_buyback_yield(stock_detail),
        **estimate,
        "news": news or [],
        "x_sentiment": x_sentiment,
        "value_trap_warning": value_trap_warning,
    }


def estimate_portfolio_return(csv_path: str, yahoo_client_module) -> dict:
    """Estimate returns for the entire portfolio.

    Fetches detailed data for each position, computes per-stock estimates,
    and calculates a weighted average for the portfolio.

    Parameters
    ----------
    csv_path : str
        Path to portfolio CSV.
    yahoo_client_module
        The yahoo_client module (for get_stock_detail, get_stock_news).

    Returns
    -------
    dict
        {
            "positions": list[dict],  # per-stock estimates
            "portfolio": {
                "optimistic": float|None,
                "base": float|None,
                "pessimistic": float|None,
            },
            "total_value_jpy": float,
            "fx_rates": dict,
        }
    """
    from src.core.portfolio.portfolio_manager import load_portfolio, get_fx_rates
    from src.core.ticker_utils import infer_currency as _infer_currency

    portfolio = load_portfolio(csv_path)
    if not portfolio:
        return {
            "positions": [],
            "portfolio": {"optimistic": None, "base": None, "pessimistic": None},
            "total_value_jpy": 0.0,
            "fx_rates": {"JPY": 1.0},
        }

    # Fetch FX rates
    fx_rates = get_fx_rates(yahoo_client_module)

    # Process each position
    position_estimates = []
    for pos in portfolio:
        symbol = pos["symbol"]

        # Skip cash positions (e.g., JPY.CASH, USD.CASH)
        if symbol.upper().endswith(".CASH"):
            cash_currency = symbol.upper().replace(".CASH", "")
            fx_rate = fx_rates.get(cash_currency, 1.0)
            value_jpy = pos["cost_price"] * pos["shares"] * fx_rate
            position_estimates.append({
                "symbol": symbol,
                "name": f"現金 ({cash_currency})",
                "price": pos["cost_price"],
                "currency": cash_currency,
                "optimistic": 0.0,
                "base": 0.0,
                "pessimistic": 0.0,
                "method": "cash",
                "analyst_count": None,
                "target_high": None,
                "target_mean": None,
                "target_low": None,
                "recommendation_mean": None,
                "forward_per": None,
                "dividend_yield": 0.0,
                "news": [],
                "x_sentiment": None,
                "shares": pos["shares"],
                "cost_price": pos["cost_price"],
                "cost_currency": pos.get("cost_currency", cash_currency),
                "value_jpy": round(value_jpy, 0),
            })
            continue

        # Get detailed stock data (includes analyst fields)
        stock_detail = yahoo_client_module.get_stock_detail(symbol)
        if stock_detail is None or not stock_detail.get("price"):
            position_estimates.append({
                "symbol": symbol,
                "name": "",
                "price": None,
                "currency": pos.get("cost_currency", "JPY"),
                "optimistic": None,
                "base": None,
                "pessimistic": None,
                "method": "no_data",
                "analyst_count": None,
                "target_high": None,
                "target_mean": None,
                "target_low": None,
                "recommendation_mean": None,
                "forward_per": None,
                "dividend_yield": None,
                "news": [],
                "x_sentiment": None,
                "shares": pos["shares"],
                "cost_price": pos["cost_price"],
                "cost_currency": pos.get("cost_currency", "JPY"),
                "value_jpy": 0,
            })
            continue

        # Get news
        news = yahoo_client_module.get_stock_news(symbol)

        # X sentiment: always None in portfolio context (KIK-369).
        # Grok API is reserved for /market-research individual deep-dives.
        x_sentiment = None

        # Estimate returns
        estimate = estimate_stock_return(symbol, stock_detail, news, x_sentiment)

        # Add position weight info
        price = stock_detail.get("price") or 0
        shares = pos["shares"]
        market_currency = stock_detail.get("currency") or _infer_currency(symbol)
        fx_rate = fx_rates.get(market_currency, 1.0)
        value_jpy = price * shares * fx_rate

        estimate["shares"] = shares
        estimate["cost_price"] = pos["cost_price"]
        estimate["cost_currency"] = pos.get("cost_currency", "JPY")
        estimate["value_jpy"] = round(value_jpy, 0)

        position_estimates.append(estimate)

    # Calculate portfolio-level weighted average returns
    total_value_jpy = sum(e.get("value_jpy", 0) for e in position_estimates)

    portfolio_optimistic = 0.0
    portfolio_base = 0.0
    portfolio_pessimistic = 0.0
    has_valid = False

    for est in position_estimates:
        if total_value_jpy <= 0:
            break
        weight = est.get("value_jpy", 0) / total_value_jpy

        if est.get("optimistic") is not None:
            portfolio_optimistic += est["optimistic"] * weight
            has_valid = True
        if est.get("base") is not None:
            portfolio_base += est["base"] * weight
        if est.get("pessimistic") is not None:
            portfolio_pessimistic += est["pessimistic"] * weight

    if not has_valid:
        portfolio_return = {"optimistic": None, "base": None, "pessimistic": None}
    else:
        portfolio_return = {
            "optimistic": round(portfolio_optimistic, 4),
            "base": round(portfolio_base, 4),
            "pessimistic": round(portfolio_pessimistic, 4),
        }

    return {
        "positions": position_estimates,
        "portfolio": portfolio_return,
        "total_value_jpy": round(total_value_jpy, 0),
        "fx_rates": fx_rates,
    }
