"""Ticker symbol utilities: currency/country inference from symbol suffixes.

Merged from portfolio_manager.py and scenario_analysis.py to provide
a single source of truth for suffix-based lookups.
"""

import re
from typing import Optional

from src.core.common import is_cash


# ---------------------------------------------------------------------------
# Symbol detection pattern (single source of truth)
# ---------------------------------------------------------------------------

SYMBOL_PATTERN = re.compile(
    r"(\d{4}\.[A-Z]+|[A-Z][A-Z0-9]{0,4}(?:\.[A-Z]{1,2})?)"
)


def extract_symbol(text: str) -> Optional[str]:
    """Extract a ticker symbol from text (e.g. 7203.T, AAPL, D05.SI)."""
    m = SYMBOL_PATTERN.search(text)
    return m.group(1) if m else None


def extract_all_symbols(text: str) -> list[str]:
    """Extract all unique ticker symbols from text."""
    return list(set(SYMBOL_PATTERN.findall(text)))


# Comprehensive suffix -> region mapping (from portfolio_manager.py)
SUFFIX_TO_REGION = {
    ".T": "Japan",
    ".SI": "Singapore",
    ".BK": "Thailand",
    ".KL": "Malaysia",
    ".JK": "Indonesia",
    ".PS": "Philippines",
    ".HK": "Hong Kong",
    ".KS": "South Korea",
    ".KQ": "South Korea",
    ".TW": "Taiwan",
    ".TWO": "Taiwan",
    ".SS": "China",
    ".SZ": "China",
    ".L": "United Kingdom",
    ".DE": "Germany",
    ".PA": "France",
    ".TO": "Canada",
    ".AX": "Australia",
    ".SA": "Brazil",
    ".NS": "India",
    ".BO": "India",
}

# Backward-compatible alias (KIK-392)
SUFFIX_TO_COUNTRY = SUFFIX_TO_REGION

# Comprehensive suffix -> currency mapping (from portfolio_manager.py)
SUFFIX_TO_CURRENCY = {
    ".T": "JPY",
    ".SI": "SGD",
    ".BK": "THB",
    ".KL": "MYR",
    ".JK": "IDR",
    ".PS": "PHP",
    ".HK": "HKD",
    ".KS": "KRW",
    ".KQ": "KRW",
    ".TW": "TWD",
    ".TWO": "TWD",
    ".SS": "CNY",
    ".SZ": "CNY",
    ".L": "GBP",
    ".DE": "EUR",
    ".PA": "EUR",
    ".TO": "CAD",
    ".AX": "AUD",
    ".SA": "BRL",
    ".NS": "INR",
    ".BO": "INR",
}


def cash_currency(symbol: str) -> str:
    """Extract currency from cash symbol (e.g., 'JPY.CASH' -> 'JPY')."""
    return symbol.upper().replace(".CASH", "")


def infer_currency(symbol: str, info: dict | None = None) -> str:
    """Infer the currency from the ticker symbol suffix.

    If *info* is provided and contains a 'currency' key, that value
    is returned directly (used by scenario_analysis).  Otherwise
    falls back to suffix-based lookup.
    """
    if info is not None:
        currency_from_info = info.get("currency")
        if currency_from_info:
            return currency_from_info
    if is_cash(symbol):
        return cash_currency(symbol)
    for suffix, currency in SUFFIX_TO_CURRENCY.items():
        if symbol.upper().endswith(suffix.upper()):
            return currency
    # No suffix typically means USD
    if "." not in symbol:
        return "USD"
    return "USD"


# Suffix -> lowercase region code mapping (KIK-438)
SUFFIX_TO_REGION_CODE = {
    ".T": "jp", ".SI": "sg", ".BK": "th", ".KL": "my", ".JK": "id",
    ".PS": "ph", ".HK": "hk", ".KS": "kr", ".KQ": "kr",
    ".TW": "tw", ".TWO": "tw", ".SS": "cn", ".SZ": "cn",
    ".L": "gb", ".DE": "de", ".PA": "fr", ".TO": "ca",
    ".AX": "au", ".SA": "br", ".NS": "in", ".BO": "in",
}


def infer_region_code(symbol: str) -> str:
    """Infer lowercase region code from ticker suffix (KIK-438).

    Examples: "jp", "us", "sg", "hk".
    """
    if is_cash(symbol):
        cur = cash_currency(symbol)
        if cur == "JPY":
            return "jp"
        if cur == "USD":
            return "us"
        for suffix, c in SUFFIX_TO_CURRENCY.items():
            if c == cur:
                return SUFFIX_TO_REGION_CODE.get(suffix, "us")
        return "us"
    for suffix, code in SUFFIX_TO_REGION_CODE.items():
        if symbol.upper().endswith(suffix.upper()):
            return code
    if "." not in symbol:
        return "us"
    return "us"


def infer_country(symbol: str, info: dict | None = None) -> str:
    """Infer the country/region from the ticker symbol suffix.

    If *info* is provided and contains 'country' or 'region' key,
    that value is returned directly (used by scenario_analysis).
    Otherwise falls back to suffix-based lookup.
    """
    if info is not None:
        country_from_info = info.get("country") or info.get("region")
        if country_from_info:
            return country_from_info
    if is_cash(symbol):
        cur = cash_currency(symbol)
        # Reverse lookup: find country for this currency
        for suffix, c in SUFFIX_TO_CURRENCY.items():
            if c == cur:
                return SUFFIX_TO_REGION.get(suffix, "Unknown")
        if cur == "USD":
            return "United States"
        if cur == "JPY":
            return "Japan"
        return "Unknown"
    for suffix, country in SUFFIX_TO_REGION.items():
        if symbol.upper().endswith(suffix.upper()):
            return country
    # No suffix typically means US stock
    if "." not in symbol:
        return "United States"
    return "Unknown"
