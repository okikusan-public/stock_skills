"""Yahoo Finance API wrapper with JSON file-based caching."""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yfinance as yf
from yfinance import EquityQuery


CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
CACHE_TTL_HOURS = 24


def _cache_path(symbol: str) -> Path:
    """Return the cache file path for a given symbol."""
    safe_name = symbol.replace(".", "_").replace("/", "_")
    return CACHE_DIR / f"{safe_name}.json"


def _read_cache(symbol: str) -> Optional[dict]:
    """Read cached data if it exists and is still valid."""
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_at = datetime.fromisoformat(data.get("_cached_at", ""))
        if datetime.now() - cached_at > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return data
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def _write_cache(symbol: str, data: dict) -> None:
    """Write data to cache with a timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["_cached_at"] = datetime.now().isoformat()
    path = _cache_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_get(info: dict, key: str) -> Any:
    """Safely retrieve a value from the info dict, returning None on failure."""
    try:
        value = info.get(key)
        if value is None:
            return None
        # yfinance occasionally returns 'Infinity' or NaN
        if isinstance(value, float) and (value != value or abs(value) == float("inf")):
            return None
        return value
    except Exception:
        return None


def _normalize_ratio(value: Any) -> Optional[float]:
    """Normalize a ratio value. If > 1, assume it's a percentage and convert."""
    if value is None:
        return None
    if value > 1:
        return value / 100.0
    return value


def get_stock_info(symbol: str) -> Optional[dict]:
    """Fetch basic stock information for a single symbol.

    Returns a dict with standardized keys, or None if the fetch fails entirely.
    Individual fields that are unavailable are set to None.
    """
    # Check cache first
    cached = _read_cache(symbol)
    if cached is not None:
        return cached

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info or info.get("regularMarketPrice") is None:
            return None

        result = {
            "symbol": symbol,
            "name": _safe_get(info, "shortName") or _safe_get(info, "longName"),
            "sector": _safe_get(info, "sector"),
            "industry": _safe_get(info, "industry"),
            "currency": _safe_get(info, "currency"),
            # Price
            "price": _safe_get(info, "regularMarketPrice"),
            "market_cap": _safe_get(info, "marketCap"),
            # Valuation
            "per": _safe_get(info, "trailingPE"),
            "forward_per": _safe_get(info, "forwardPE"),
            "pbr": _safe_get(info, "priceToBook"),
            "psr": _safe_get(info, "priceToSalesTrailing12Months"),
            # Profitability
            "roe": _safe_get(info, "returnOnEquity"),
            "roa": _safe_get(info, "returnOnAssets"),
            "profit_margin": _safe_get(info, "profitMargins"),
            "operating_margin": _safe_get(info, "operatingMargins"),
            # Dividend (normalize: yfinance may return % like 2.56 instead of 0.0256)
            "dividend_yield": _normalize_ratio(_safe_get(info, "dividendYield")),
            "payout_ratio": _safe_get(info, "payoutRatio"),
            # Growth
            "revenue_growth": _safe_get(info, "revenueGrowth"),
            "earnings_growth": _safe_get(info, "earningsGrowth"),
            # Financial health
            "debt_to_equity": _safe_get(info, "debtToEquity"),
            "current_ratio": _safe_get(info, "currentRatio"),
            "free_cashflow": _safe_get(info, "freeCashflow"),
            # Other
            "beta": _safe_get(info, "beta"),
            "fifty_two_week_high": _safe_get(info, "fiftyTwoWeekHigh"),
            "fifty_two_week_low": _safe_get(info, "fiftyTwoWeekLow"),
        }

        _write_cache(symbol, result)
        return result

    except Exception as e:
        print(f"[yahoo_client] Error fetching {symbol}: {e}")
        return None


def get_multiple_stocks(symbols: list[str]) -> dict[str, Optional[dict]]:
    """Fetch stock info for multiple symbols with a 1-second delay between requests.

    Returns a dict mapping symbol -> stock info (or None on failure).
    """
    results: dict[str, Optional[dict]] = {}
    for i, symbol in enumerate(symbols):
        results[symbol] = get_stock_info(symbol)
        # Wait 1 second between requests (skip after the last one)
        if i < len(symbols) - 1:
            time.sleep(1)
    return results


# ---------------------------------------------------------------------------
# Detail cache helpers
# ---------------------------------------------------------------------------

def _detail_cache_path(symbol: str) -> Path:
    """Return the detail-cache file path for a given symbol."""
    safe_name = symbol.replace(".", "_").replace("/", "_")
    return CACHE_DIR / f"{safe_name}_detail.json"


def _read_detail_cache(symbol: str) -> Optional[dict]:
    """Read detail-cached data if it exists and is still valid (24h TTL)."""
    path = _detail_cache_path(symbol)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_at = datetime.fromisoformat(data.get("_cached_at", ""))
        if datetime.now() - cached_at > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return data
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def _write_detail_cache(symbol: str, data: dict) -> None:
    """Write detail data to cache with a timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["_cached_at"] = datetime.now().isoformat()
    path = _detail_cache_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _try_get_field(df: Any, field_names: list[str]) -> Optional[float]:
    """Try to extract a numeric value from a DataFrame row using multiple
    possible field names.  Returns None if the DataFrame is empty or none of
    the names exist.
    """
    try:
        if df is None or df.empty:
            return None
        for name in field_names:
            if name in df.index:
                value = df.loc[name].iloc[0]
                # Convert numpy / pandas types to plain Python float
                if value is not None and value == value:  # NaN check
                    return float(value)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# get_stock_detail
# ---------------------------------------------------------------------------

def get_stock_detail(symbol: str) -> Optional[dict]:
    """Fetch detailed stock information including financial statements.

    Extends the base data from ``get_stock_info`` with price history,
    balance-sheet ratios, cash-flow, EPS growth, and debt/EBITDA figures.

    Returns a merged dict or None if the base data cannot be fetched.
    """
    # 1. Get base data first
    base = get_stock_info(symbol)
    if base is None:
        return None

    # 2. Check detail cache
    cached = _read_detail_cache(symbol)
    if cached is not None:
        return cached

    # 3. Fetch additional data from yfinance
    try:
        time.sleep(1)  # rate-limit consistent with existing pattern
        ticker = yf.Ticker(symbol)

        # --- Price history (6 months) ---
        price_history: Optional[list[float]] = None
        try:
            hist = ticker.history(period="6mo")
            if hist is not None and not hist.empty and "Close" in hist.columns:
                price_history = [float(v) for v in hist["Close"].tolist()]
        except Exception:
            pass

        # --- Balance sheet: equity ratio ---
        equity_ratio: Optional[float] = None
        try:
            bs = ticker.balance_sheet
            if bs is not None and not bs.empty:
                col = bs.iloc[:, 0]  # most recent column
                equity = _try_get_field(bs, [
                    "Stockholders Equity",
                    "Total Stockholder Equity",
                    "Stockholders' Equity",
                    "StockholdersEquity",
                    "Total Equity Gross Minority Interest",
                ])
                total_assets = _try_get_field(bs, [
                    "Total Assets",
                    "TotalAssets",
                ])
                if equity is not None and total_assets is not None and total_assets != 0:
                    equity_ratio = float(equity / total_assets)
        except Exception:
            pass

        # --- Cash flow ---
        operating_cashflow: Optional[float] = None
        fcf: Optional[float] = None
        try:
            cf = ticker.cashflow
            operating_cashflow = _try_get_field(cf, [
                "Operating Cash Flow",
                "Total Cash From Operating Activities",
                "Cash Flow From Continuing Operating Activities",
            ])
            fcf = _try_get_field(cf, [
                "Free Cash Flow",
                "FreeCashFlow",
            ])
        except Exception:
            pass

        # --- Income statement: EPS & net income ---
        eps_current: Optional[float] = None
        eps_previous: Optional[float] = None
        eps_growth: Optional[float] = None
        net_income_stmt: Optional[float] = None
        try:
            inc = ticker.income_stmt
            if inc is not None and not inc.empty:
                # Net income from most recent period
                net_income_stmt = _try_get_field(inc, [
                    "Net Income",
                    "NetIncome",
                    "Net Income Common Stockholders",
                ])

                # Diluted EPS – latest two years for growth calculation
                eps_field_name = None
                for candidate in ["Diluted EPS", "DilutedEPS"]:
                    if candidate in inc.index:
                        eps_field_name = candidate
                        break

                if eps_field_name is not None:
                    eps_row = inc.loc[eps_field_name]
                    if len(eps_row) >= 1:
                        val = eps_row.iloc[0]
                        if val is not None and val == val:
                            eps_current = float(val)
                    if len(eps_row) >= 2:
                        val = eps_row.iloc[1]
                        if val is not None and val == val:
                            eps_previous = float(val)
                    if (
                        eps_current is not None
                        and eps_previous is not None
                        and eps_previous != 0
                    ):
                        eps_growth = float(
                            (eps_current - eps_previous) / abs(eps_previous)
                        )
        except Exception:
            pass

        # --- Additional info fields ---
        total_debt: Optional[float] = None
        ebitda: Optional[float] = None
        try:
            info = ticker.info
            total_debt = _safe_get(info, "totalDebt")
            ebitda = _safe_get(info, "ebitda")
        except Exception:
            pass

        # 4. Merge into base dict
        result = dict(base)  # shallow copy to avoid mutating cached base
        result.update({
            "price_history": price_history,
            "equity_ratio": equity_ratio,
            "operating_cashflow": operating_cashflow,
            "net_income_stmt": net_income_stmt,
            "fcf": fcf,
            "total_debt": total_debt,
            "ebitda": ebitda,
            "eps_current": eps_current,
            "eps_previous": eps_previous,
            "eps_growth": eps_growth,
        })

        # 5. Cache the result
        _write_detail_cache(symbol, result)
        return result

    except Exception as e:
        print(f"[yahoo_client] Error fetching detail for {symbol}: {e}")
        return None


# ---------------------------------------------------------------------------
# EquityQuery-based screening via yf.screen()
# ---------------------------------------------------------------------------

def screen_stocks(
    query: EquityQuery,
    size: int = 250,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
) -> list[dict]:
    """Screen stocks using yfinance EquityQuery + yf.screen().

    Parameters
    ----------
    query : EquityQuery
        Pre-built EquityQuery object containing all screening conditions.
    size : int
        Maximum number of results to request (max 250 for yf.screen).
    sort_field : str
        Field to sort results by (default: market cap descending).
    sort_asc : bool
        Sort ascending if True, descending if False.

    Returns
    -------
    list[dict]
        List of quote dicts returned by yf.screen(). Each dict contains
        raw Yahoo Finance fields such as 'symbol', 'shortName',
        'regularMarketPrice', 'trailingPE', 'priceToBook',
        'dividendYield', 'returnOnEquity', etc.
        Returns an empty list on error.
    """
    try:
        response = yf.screen(query, size=size, sortField=sort_field, sortAsc=sort_asc)
        if response is None:
            print("[yahoo_client] yf.screen() returned None")
            return []
        quotes = response.get("quotes", [])
        if not isinstance(quotes, list):
            print(f"[yahoo_client] Unexpected quotes type: {type(quotes)}")
            return []
        return quotes
    except Exception as e:
        print(f"[yahoo_client] Error in screen_stocks: {e}")
        return []
