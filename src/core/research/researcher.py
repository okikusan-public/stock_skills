"""Deep research orchestration for stocks, industries, and markets (KIK-367).

Integrates yfinance quantitative data with Grok API qualitative data
(X posts, web search) to produce multi-faceted research reports.
"""

import sys

from src.core.screening.indicators import calculate_value_score

# Grok API: graceful degradation when module is unavailable
try:
    from src.data import grok_client

    HAS_GROK = True
except ImportError:
    HAS_GROK = False

_grok_warned = [False]


def _grok_available() -> bool:
    """Return True if grok_client is importable and API key is set."""
    return HAS_GROK and grok_client.is_available()


def _safe_grok_call(func, *args, **kwargs):
    """Call a grok_client function with error handling.

    Returns the function result on success, or None on any exception.
    Prints a warning to stderr on the first failure (subsequent suppressed).
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if not _grok_warned[0]:
            print(
                f"[researcher] Grok API error (subsequent errors suppressed): {e}",
                file=sys.stderr,
            )
            _grok_warned[0] = True
        return None


def _extract_fundamentals(info: dict) -> dict:
    """Extract fundamental fields from yahoo_client data."""
    return {
        "price": info.get("price"),
        "market_cap": info.get("market_cap"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "per": info.get("per"),
        "pbr": info.get("pbr"),
        "roe": info.get("roe"),
        "dividend_yield": info.get("dividend_yield"),
        "revenue_growth": info.get("revenue_growth"),
        "eps_growth": info.get("eps_growth"),
        "beta": info.get("beta"),
        "debt_to_equity": info.get("debt_to_equity"),
    }


def _empty_sentiment() -> dict:
    """Return an empty X sentiment result."""
    return {
        "positive": [],
        "negative": [],
        "sentiment_score": 0.0,
        "raw_response": "",
    }


def _empty_stock_deep() -> dict:
    """Return an empty stock deep research result."""
    return {
        "recent_news": [],
        "catalysts": {"positive": [], "negative": []},
        "analyst_views": [],
        "x_sentiment": {"score": 0.0, "summary": "", "key_opinions": []},
        "competitive_notes": [],
        "raw_response": "",
    }


def _empty_industry() -> dict:
    """Return an empty industry research result."""
    return {
        "trends": [],
        "key_players": [],
        "growth_drivers": [],
        "risks": [],
        "regulatory": [],
        "investor_focus": [],
        "raw_response": "",
    }


def _empty_market() -> dict:
    """Return an empty market research result."""
    return {
        "price_action": "",
        "macro_factors": [],
        "sentiment": {"score": 0.0, "summary": ""},
        "upcoming_events": [],
        "sector_rotation": [],
        "raw_response": "",
    }


def _empty_business() -> dict:
    """Return an empty business model research result."""
    return {
        "overview": "",
        "segments": [],
        "revenue_model": "",
        "competitive_advantages": [],
        "key_metrics": [],
        "growth_strategy": [],
        "risks": [],
        "raw_response": "",
    }


def research_stock(symbol: str, yahoo_client_module) -> dict:
    """Run comprehensive stock research combining yfinance and Grok API.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "7203.T", "AAPL").
    yahoo_client_module
        The yahoo_client module (enables mock injection in tests).

    Returns
    -------
    dict
        Integrated research data with fundamentals, value score,
        Grok deep research, X sentiment, and news.
    """
    # 1. Fetch base data via yahoo_client
    info = yahoo_client_module.get_stock_info(symbol)
    if info is None:
        info = {}

    company_name = info.get("name") or ""
    fundamentals = _extract_fundamentals(info)

    # 2. Calculate value score
    value_score = calculate_value_score(info)

    # 3. Grok API: deep research + X sentiment
    grok_research = _empty_stock_deep()
    x_sentiment = _empty_sentiment()

    if _grok_available():
        deep = _safe_grok_call(
            grok_client.search_stock_deep, symbol, company_name
        )
        if deep is not None:
            grok_research = deep

        sent = _safe_grok_call(
            grok_client.search_x_sentiment, symbol, company_name
        )
        if sent is not None:
            x_sentiment = sent

    # 4. News from yahoo_client (if the function exists)
    news = []
    if hasattr(yahoo_client_module, "get_stock_news"):
        try:
            news = yahoo_client_module.get_stock_news(symbol) or []
        except Exception:
            pass

    return {
        "symbol": symbol,
        "name": company_name,
        "type": "stock",
        "fundamentals": fundamentals,
        "value_score": value_score,
        "grok_research": grok_research,
        "x_sentiment": x_sentiment,
        "news": news,
    }


def research_industry(theme: str) -> dict:
    """Run industry/theme research via Grok API.

    Parameters
    ----------
    theme : str
        Industry name or theme (e.g. "semiconductor", "EV", "AI").

    Returns
    -------
    dict
        Industry research data. ``api_unavailable`` is True when
        Grok is unavailable.
    """
    grok_result = _empty_industry()
    grok_available = False
    if _grok_available():
        grok_available = True
        result = _safe_grok_call(grok_client.search_industry, theme)
        if result is not None:
            grok_result = result

    return {
        "theme": theme,
        "type": "industry",
        "grok_research": grok_result,
        "api_unavailable": not grok_available,
    }


def research_market(market: str, yahoo_client_module=None) -> dict:
    """Run market overview research via yfinance + Grok.

    Parameters
    ----------
    market : str
        Market name or index (e.g. "Nikkei 225", "S&P500").
    yahoo_client_module : module, optional
        The yahoo_client module for macro indicators (enables mock injection).
        When ``None``, macro_indicators will be empty (backward compatible).

    Returns
    -------
    dict
        Market research data with ``macro_indicators`` (Layer 1, always)
        and ``grok_research`` (Layer 2).
    """
    # Layer 1: yfinance quantitative (always available)
    macro_indicators: list[dict] = []
    if yahoo_client_module and hasattr(yahoo_client_module, "get_macro_indicators"):
        try:
            macro_indicators = yahoo_client_module.get_macro_indicators() or []
        except Exception:
            pass

    # Layer 2: Grok qualitative (when API key is set)
    grok_research = _empty_market()
    grok_available = False
    if _grok_available():
        grok_available = True
        result = _safe_grok_call(grok_client.search_market, market)
        if result is not None:
            grok_research = result

    return {
        "market": market,
        "type": "market",
        "macro_indicators": macro_indicators,
        "grok_research": grok_research,
        "api_unavailable": not grok_available,
    }


def research_business(symbol: str, yahoo_client_module) -> dict:
    """Run business model research combining yfinance and Grok.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "7751.T", "AAPL").
    yahoo_client_module
        The yahoo_client module (enables mock injection in tests).

    Returns
    -------
    dict
        Business model research data. ``api_unavailable`` is True when
        Grok is unavailable.
    """
    # Fetch company name from yfinance for prompt enrichment
    info = yahoo_client_module.get_stock_info(symbol)
    if info is None:
        info = {}
    company_name = info.get("name") or ""

    grok_result = _empty_business()
    grok_available = False
    if _grok_available():
        grok_available = True
        result = _safe_grok_call(grok_client.search_business, symbol, company_name)
        if result is not None:
            grok_result = result

    return {
        "symbol": symbol,
        "name": company_name,
        "type": "business",
        "grok_research": grok_result,
        "api_unavailable": not grok_available,
    }
