"""Value stock screening engine."""

import time
from pathlib import Path
from typing import Optional

import yaml

from src.core.alpha import compute_change_score
from src.core.filters import apply_filters
from src.core.indicators import calculate_value_score, calculate_shareholder_return
from src.core.query_builder import build_query
from src.core.technicals import detect_pullback_in_uptrend

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "screening_presets.yaml"


def _load_preset(preset_name: str) -> dict:
    """Load screening criteria from the presets YAML file."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    presets = config.get("presets", {})
    if preset_name not in presets:
        raise ValueError(f"Unknown preset: '{preset_name}'. Available: {list(presets.keys())}")
    return presets[preset_name].get("criteria", {})


class ValueScreener:
    """Screen stocks for value investment opportunities."""

    def __init__(self, yahoo_client, market):
        """Initialise the screener.

        Parameters
        ----------
        yahoo_client : module or object
            Must expose ``get_stock_info(symbol) -> dict | None``.
        market : Market
            Must expose ``get_default_symbols() -> list[str]``
            and ``get_thresholds() -> dict``.
        """
        self.yahoo_client = yahoo_client
        self.market = market

    def screen(
        self,
        symbols: Optional[list[str]] = None,
        criteria: Optional[dict] = None,
        preset: Optional[str] = None,
        top_n: int = 20,
    ) -> list[dict]:
        """Run the screening process and return the top results.

        Parameters
        ----------
        symbols : list[str], optional
            Ticker symbols to screen. Defaults to the market's default list.
        criteria : dict, optional
            Filter criteria (e.g. ``{'max_per': 15, 'min_roe': 0.05}``).
        preset : str, optional
            Name of a preset defined in ``config/screening_presets.yaml``.
            Ignored when *criteria* is explicitly provided.
        top_n : int
            Maximum number of results to return, sorted by value score descending.

        Returns
        -------
        list[dict]
            Each dict contains: symbol, name, price, per, pbr,
            dividend_yield, roe, value_score.
        """
        # Resolve symbols
        if symbols is None:
            symbols = self.market.get_default_symbols()

        # Resolve criteria (explicit criteria takes priority over preset)
        if criteria is None:
            if preset is not None:
                criteria = _load_preset(preset)
            else:
                criteria = {}

        thresholds = self.market.get_thresholds()

        results: list[dict] = []

        for symbol in symbols:
            data = self.yahoo_client.get_stock_info(symbol)
            if data is None:
                continue

            # Apply filter criteria
            if not apply_filters(data, criteria):
                continue

            # Calculate value score
            score = calculate_value_score(data, thresholds)

            results.append({
                "symbol": data.get("symbol", symbol),
                "name": data.get("name"),
                "price": data.get("price"),
                "per": data.get("per"),
                "pbr": data.get("pbr"),
                "dividend_yield": data.get("dividend_yield"),
                "roe": data.get("roe"),
                "value_score": score,
            })

        # Sort by value_score descending, take top N
        results.sort(key=lambda r: r["value_score"], reverse=True)
        return results[:top_n]


class QueryScreener:
    """Screen stocks using yfinance EquityQuery + yf.screen().

    Unlike ValueScreener which iterates over a symbol list one-by-one,
    QueryScreener sends conditions directly to Yahoo Finance's screener
    API and retrieves matching stocks in a single call per region.

    This class does NOT require a Market object or a pre-built symbol list.
    """

    def __init__(self, yahoo_client):
        """Initialise the screener.

        Parameters
        ----------
        yahoo_client : module or object
            Must expose ``screen_stocks(query, size, sort_field, sort_asc) -> list[dict]``.
        """
        self.yahoo_client = yahoo_client

    @staticmethod
    def _normalize_quote(quote: dict) -> dict:
        """Normalize a raw yf.screen() quote dict to the project's standard keys.

        The raw quote uses Yahoo Finance field names (e.g. 'trailingPE',
        'priceToBook'). This converts them to the project's internal names
        (e.g. 'per', 'pbr') so that ``calculate_value_score`` and other
        downstream code works seamlessly.
        """
        # dividendYield from yfinance is always a percentage (e.g. 3.5 for 3.5%)
        raw_div = quote.get("dividendYield")
        if raw_div is not None:
            raw_div = raw_div / 100.0

        # returnOnEquity similarly may need normalisation
        raw_roe = quote.get("returnOnEquity")
        if raw_roe is not None and raw_roe > 1:
            raw_roe = raw_roe / 100.0

        # revenueGrowth / earningsGrowth may be percentages
        raw_rev_growth = quote.get("revenueGrowth")
        if raw_rev_growth is not None and abs(raw_rev_growth) > 5:
            raw_rev_growth = raw_rev_growth / 100.0

        # --- Anomaly guard: sanitize extreme values ---
        raw_per = quote.get("trailingPE")
        if raw_per is not None and 0 < raw_per < 1.0:
            raw_per = None

        raw_pbr = quote.get("priceToBook")
        if raw_pbr is not None and raw_pbr < 0.05:
            raw_pbr = None

        if raw_div is not None and raw_div > 0.15:
            raw_div = None

        if raw_roe is not None and (raw_roe < -1.0 or raw_roe > 2.0):
            raw_roe = None

        return {
            "symbol": quote.get("symbol", ""),
            "name": quote.get("shortName") or quote.get("longName"),
            "sector": quote.get("sector"),
            "industry": quote.get("industry"),
            "currency": quote.get("currency"),
            # Price
            "price": quote.get("regularMarketPrice"),
            "market_cap": quote.get("marketCap"),
            # Valuation
            "per": raw_per,
            "forward_per": quote.get("forwardPE"),
            "pbr": raw_pbr,
            # Profitability
            "roe": raw_roe,
            # Dividend
            "dividend_yield": raw_div,
            # Growth
            "revenue_growth": raw_rev_growth,
            "earnings_growth": quote.get("earningsGrowth"),
            # Exchange info
            "exchange": quote.get("exchange"),
        }

    def screen(
        self,
        region: str,
        criteria: Optional[dict] = None,
        preset: Optional[str] = None,
        exchange: Optional[str] = None,
        sector: Optional[str] = None,
        top_n: int = 20,
        sort_field: str = "intradaymarketcap",
        sort_asc: bool = False,
        with_pullback: bool = False,
    ) -> list[dict]:
        """Run EquityQuery-based screening and return scored results.

        Parameters
        ----------
        region : str
            Market region (e.g. 'japan', 'us', 'asean', or raw codes
            like 'jp', 'sg').
        criteria : dict, optional
            Filter criteria (max_per, max_pbr, min_dividend_yield,
            min_roe, min_revenue_growth). Takes priority over *preset*.
        preset : str, optional
            Name of a preset from ``config/screening_presets.yaml``.
            Ignored when *criteria* is provided.
        exchange : str, optional
            Exchange filter (e.g. 'JPX', 'NMS'). If omitted, region
            alone determines the scope.
        sector : str, optional
            Sector filter (e.g. 'Technology', 'Financial Services').
        top_n : int
            Maximum number of results to return.
        sort_field : str
            yf.screen() sort field.
        sort_asc : bool
            Sort ascending if True.
        with_pullback : bool
            When True, apply pullback-in-uptrend technical filter after
            value scoring.  Only stocks that pass the pullback check are
            returned, with additional technical indicator fields attached.

        Returns
        -------
        list[dict]
            Each dict contains: symbol, name, price, per, pbr,
            dividend_yield, roe, value_score, plus sector/industry/exchange.
            When *with_pullback* is True, also includes pullback_pct, rsi,
            volume_ratio, sma50, sma200, bounce_score, match_type.
            Sorted by value_score descending (or match_type then value_score
            when *with_pullback* is True).
        """
        # Resolve criteria
        if criteria is None:
            if preset is not None:
                criteria = _load_preset(preset)
            else:
                criteria = {}

        # Build the EquityQuery
        query = build_query(criteria, region=region, exchange=exchange, sector=sector)

        # Fetch more than needed to allow scoring to select the best.
        # Pullback mode needs a higher multiplier since many stocks fail the technical filter.
        # Keep pullback limit moderate to avoid excessive per-stock API calls.
        if with_pullback:
            max_results = max(top_n * 5, 250)
        else:
            max_results = top_n * 5

        # Call yahoo_client.screen_stocks()
        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=max_results,
            sort_field=sort_field,
            sort_asc=sort_asc,
        )

        if not raw_quotes:
            return []

        # Normalize quotes and calculate value scores
        results: list[dict] = []
        for quote in raw_quotes:
            normalized = self._normalize_quote(quote)

            # calculate_value_score works with our standard keys
            score = calculate_value_score(normalized)

            normalized["value_score"] = score
            results.append(normalized)

        # -----------------------------------------------------------
        # Optional shareholder return filter (KIK-378)
        # Requires get_stock_detail() for cashflow data
        # -----------------------------------------------------------
        if "min_total_shareholder_return" in criteria:
            enriched = []
            for stock in results:
                symbol = stock.get("symbol")
                if not symbol:
                    continue
                detail = self.yahoo_client.get_stock_detail(symbol)
                if detail is None:
                    continue
                sr = calculate_shareholder_return(detail)
                stock["total_shareholder_return"] = sr.get("total_return_rate")
                stock["buyback_yield"] = sr.get("buyback_yield")
                if apply_filters(stock, {"min_total_shareholder_return": criteria["min_total_shareholder_return"]}):
                    enriched.append(stock)
            results = enriched

        # -----------------------------------------------------------
        # Optional pullback-in-uptrend filter
        # -----------------------------------------------------------
        if with_pullback:
            pullback_results: list[dict] = []
            for stock in results:
                symbol = stock.get("symbol")
                if not symbol:
                    continue

                hist = self.yahoo_client.get_price_history(symbol)
                if hist is None or hist.empty:
                    continue

                tech_result = detect_pullback_in_uptrend(hist)
                if tech_result is None:
                    continue

                all_conditions = tech_result.get("all_conditions")
                bounce_score = tech_result.get("bounce_score", 0)

                if all_conditions:
                    match_type = "full"
                elif (
                    bounce_score >= 30
                    and tech_result.get("uptrend")
                    and tech_result.get("is_pullback")
                ):
                    match_type = "partial"
                else:
                    continue

                # Attach technical indicators to the stock dict
                stock["pullback_pct"] = tech_result.get("pullback_pct")
                stock["rsi"] = tech_result.get("rsi")
                stock["volume_ratio"] = tech_result.get("volume_ratio")
                stock["sma50"] = tech_result.get("sma50")
                stock["sma200"] = tech_result.get("sma200")
                stock["bounce_score"] = bounce_score
                stock["match_type"] = match_type
                pullback_results.append(stock)

            # Sort: "full" first, then "partial"; within each group by value_score desc
            pullback_results.sort(
                key=lambda r: (
                    0 if r.get("match_type") == "full" else 1,
                    -(r.get("value_score") or 0),
                ),
            )
            return pullback_results[:top_n]

        # Sort by value_score descending, take top N
        results.sort(key=lambda r: r["value_score"], reverse=True)
        return results[:top_n]


class PullbackScreener:
    """Screen stocks for pullback-in-uptrend entry opportunities.

    Three-step pipeline:
      Step 1: EquityQuery for fundamental filtering (PER<20, ROE>8%, EPS growth>5%)
      Step 2: Technical filter - detect pullback in uptrend
      Step 3: Scoring (value_score from Step 1)
    """

    # Default fundamental criteria for pullback screening
    DEFAULT_CRITERIA = {
        "max_per": 20,
        "min_roe": 0.08,
        "min_revenue_growth": 0.05,
    }

    def __init__(self, yahoo_client):
        """Initialise the screener.

        Parameters
        ----------
        yahoo_client : module or object
            Must expose ``screen_stocks()``, ``get_price_history()``,
            and ``get_stock_detail()``.
        """
        self.yahoo_client = yahoo_client

    def screen(
        self,
        region: str = "jp",
        top_n: int = 20,
        fundamental_criteria: Optional[dict] = None,
    ) -> list[dict]:
        """Run the three-step pullback screening pipeline.

        Parameters
        ----------
        region : str
            Market region code (e.g. 'jp', 'us', 'sg').
        top_n : int
            Maximum number of results to return.
        fundamental_criteria : dict, optional
            Override the default fundamental criteria.

        Returns
        -------
        list[dict]
            Screened stocks sorted by final_score descending.
        """
        criteria = fundamental_criteria if fundamental_criteria is not None else dict(self.DEFAULT_CRITERIA)

        # ---------------------------------------------------------------
        # Step 1: Fundamental filtering via EquityQuery
        # ---------------------------------------------------------------
        query = build_query(criteria, region=region)

        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=max(top_n * 5, 250),
            sort_field="intradaymarketcap",
            sort_asc=False,
        )

        if not raw_quotes:
            return []

        # Normalize quotes using QueryScreener's static method
        fundamentals: list[dict] = []
        for quote in raw_quotes:
            normalized = QueryScreener._normalize_quote(quote)
            # Also compute value_score for fallback scoring
            normalized["value_score"] = calculate_value_score(normalized)
            fundamentals.append(normalized)

        # ---------------------------------------------------------------
        # Step 2: Technical filter - pullback in uptrend
        # ---------------------------------------------------------------
        technical_passed: list[dict] = []
        for stock in fundamentals:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            hist = self.yahoo_client.get_price_history(symbol)
            if hist is None or hist.empty:
                continue

            tech_result = detect_pullback_in_uptrend(hist)
            if tech_result is None:
                continue

            all_conditions = tech_result.get("all_conditions")
            bounce_score = tech_result.get("bounce_score", 0)

            if all_conditions:
                match_type = "full"
            elif (
                bounce_score >= 30
                and tech_result.get("uptrend")
                and tech_result.get("is_pullback")
            ):
                match_type = "partial"
            else:
                continue

            # Attach technical indicators to the stock dict
            stock["pullback_pct"] = tech_result.get("pullback_pct")
            stock["rsi"] = tech_result.get("rsi")
            stock["volume_ratio"] = tech_result.get("volume_ratio")
            stock["sma50"] = tech_result.get("sma50")
            stock["sma200"] = tech_result.get("sma200")
            stock["bounce_score"] = bounce_score
            stock["match_type"] = match_type
            technical_passed.append(stock)

        if not technical_passed:
            return []

        # ---------------------------------------------------------------
        # Step 3: Scoring (value_score from Step 1)
        # ---------------------------------------------------------------
        results: list[dict] = []
        for stock in technical_passed:
            results.append({
                "symbol": stock["symbol"],
                "name": stock.get("name"),
                "price": stock.get("price"),
                "per": stock.get("per"),
                "pbr": stock.get("pbr"),
                "dividend_yield": stock.get("dividend_yield"),
                "roe": stock.get("roe"),
                # Technical
                "pullback_pct": stock.get("pullback_pct"),
                "rsi": stock.get("rsi"),
                "volume_ratio": stock.get("volume_ratio"),
                "sma50": stock.get("sma50"),
                "sma200": stock.get("sma200"),
                # Bounce / match info
                "bounce_score": stock.get("bounce_score"),
                "match_type": stock.get("match_type", "full"),
                # Score
                "final_score": stock.get("value_score", 0.0),
            })

        # Sort: "full" matches first, then "partial"; within each group by final_score descending
        results.sort(
            key=lambda r: (
                0 if r.get("match_type") == "full" else 1,
                -(r.get("final_score") or 0.0),
            ),
        )
        return results[:top_n]


class AlphaScreener:
    """Alpha signal screener: value + change quality + pullback.

    4-step pipeline:
      Step 1: EquityQuery for fundamental filtering (value preset)
      Step 2: Change quality check (alpha.py) - 3/4 conditions must pass
      Step 3: Pullback-in-uptrend technical filter (optional enrichment)
      Step 4: 2-axis scoring (value_score + change_score = 200pt max)
    """

    def __init__(self, yahoo_client):
        self.yahoo_client = yahoo_client

    def screen(
        self,
        region: str = "jp",
        top_n: int = 20,
    ) -> list[dict]:
        # Step 1: EquityQuery with value preset criteria
        criteria = _load_preset("value")
        query = build_query(criteria, region=region)

        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=max(top_n * 5, 250),
            sort_field="intradaymarketcap",
            sort_asc=False,
        )

        if not raw_quotes:
            return []

        # Normalize and score
        fundamentals = []
        for quote in raw_quotes:
            normalized = QueryScreener._normalize_quote(quote)
            normalized["value_score"] = calculate_value_score(normalized)
            fundamentals.append(normalized)

        # Step 2: Change quality check (requires get_stock_detail)
        quality_passed = []
        for stock in fundamentals:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            detail = self.yahoo_client.get_stock_detail(symbol)
            if detail is None:
                continue

            change_result = compute_change_score(detail)

            # 3/4 conditions must pass (quality_pass)
            if not change_result.get("quality_pass"):
                continue

            # Attach change score data
            stock["change_score"] = change_result["change_score"]
            stock["accruals_score"] = change_result["accruals"]["score"]
            stock["accruals_raw"] = change_result["accruals"]["raw"]
            stock["rev_accel_score"] = change_result["revenue_acceleration"]["score"]
            stock["rev_accel_raw"] = change_result["revenue_acceleration"]["raw"]
            stock["fcf_yield_score"] = change_result["fcf_yield"]["score"]
            stock["fcf_yield_raw"] = change_result["fcf_yield"]["raw"]
            stock["roe_trend_score"] = change_result["roe_trend"]["score"]
            stock["roe_trend_raw"] = change_result["roe_trend"]["raw"]
            stock["quality_passed_count"] = change_result["passed_count"]
            quality_passed.append(stock)

        if not quality_passed:
            return []

        # Step 3: Pullback check (optional enrichment, not a hard filter)
        for stock in quality_passed:
            symbol = stock["symbol"]
            try:
                hist = self.yahoo_client.get_price_history(symbol)
                if hist is not None and not hist.empty:
                    tech_result = detect_pullback_in_uptrend(hist)
                    if tech_result is not None:
                        all_conditions = tech_result.get("all_conditions")
                        bounce_score = tech_result.get("bounce_score", 0)

                        if all_conditions:
                            stock["pullback_match"] = "full"
                        elif (
                            bounce_score >= 30
                            and tech_result.get("uptrend")
                            and tech_result.get("is_pullback")
                        ):
                            stock["pullback_match"] = "partial"
                        else:
                            stock["pullback_match"] = "none"

                        stock["pullback_pct"] = tech_result.get("pullback_pct")
                        stock["rsi"] = tech_result.get("rsi")
                        stock["bounce_score"] = bounce_score
                    else:
                        stock["pullback_match"] = "none"
                else:
                    stock["pullback_match"] = "none"
            except Exception:
                stock["pullback_match"] = "none"

        # Step 4: 2-axis scoring
        results = []
        for stock in quality_passed:
            value_score = stock.get("value_score", 0)
            change_score = stock.get("change_score", 0)
            total_score = value_score + change_score  # 200pt max

            # Pullback bonus: full=+10, partial=+5
            pullback_match = stock.get("pullback_match", "none")
            if pullback_match == "full":
                total_score += 10
            elif pullback_match == "partial":
                total_score += 5

            stock["total_score"] = total_score
            results.append(stock)

        # Sort by total_score descending
        results.sort(key=lambda r: r.get("total_score", 0), reverse=True)
        return results[:top_n]


class TrendingScreener:
    """Screen stocks trending on X (Twitter) with fundamental enrichment.

    Pipeline:
      Step 1: Grok API x_search to discover trending tickers
      Step 2: yahoo_client.get_stock_info() for fundamentals
      Step 3: calculate_value_score() + classify
      Step 4: Sort by classification then score

    Classification thresholds use the standard value_score 0-100 scale
    from calculate_value_score() (PER 25pt + PBR 25pt + Dividend 20pt +
    ROE 15pt + Growth 15pt).  Trending/growth stocks tend to have higher
    PER/PBR, so their scores skew lower.  The 60/30 thresholds are
    intentionally strict to surface only clearly undervalued opportunities
    among trending names.
    """

    UNDERVALUED_THRESHOLD = 60
    FAIR_VALUE_THRESHOLD = 30
    CLASSIFICATION_NO_DATA = "話題×データ不足"

    def __init__(self, yahoo_client, grok_client_module):
        self.yahoo_client = yahoo_client
        self.grok_client = grok_client_module

    @staticmethod
    def classify(value_score: float) -> str:
        if value_score >= TrendingScreener.UNDERVALUED_THRESHOLD:
            return "話題×割安"
        elif value_score >= TrendingScreener.FAIR_VALUE_THRESHOLD:
            return "話題×適正"
        return "話題×割高"

    def screen(
        self,
        region: str = "japan",
        theme: Optional[str] = None,
        top_n: int = 20,
    ) -> tuple:
        """Run the trending stock screening pipeline.

        Returns
        -------
        tuple[list[dict], str]
            (results, market_context)
        """
        trending = self.grok_client.search_trending_stocks(
            region=region, theme=theme,
        )

        trending_stocks = trending.get("stocks", [])
        market_context = trending.get("market_context", "")

        if not trending_stocks:
            return [], market_context

        results: list[dict] = []
        for item in trending_stocks:
            ticker = item.get("ticker", "")
            if not ticker:
                continue

            info = self.yahoo_client.get_stock_info(ticker)
            if info is None:
                results.append({
                    "symbol": ticker,
                    "name": item.get("name", ""),
                    "trending_reason": item.get("reason", ""),
                    "price": None,
                    "per": None,
                    "pbr": None,
                    "dividend_yield": None,
                    "roe": None,
                    "value_score": 0.0,
                    "classification": self.CLASSIFICATION_NO_DATA,
                    "sector": None,
                })
                continue

            score = calculate_value_score(info)
            classification = self.classify(score)

            results.append({
                "symbol": info.get("symbol", ticker),
                "name": info.get("name") or item.get("name", ""),
                "trending_reason": item.get("reason", ""),
                "price": info.get("price"),
                "per": info.get("per"),
                "pbr": info.get("pbr"),
                "dividend_yield": info.get("dividend_yield"),
                "roe": info.get("roe"),
                "value_score": score,
                "classification": classification,
                "sector": info.get("sector"),
            })

        _CLASS_ORDER = {"話題×割安": 0, "話題×適正": 1, "話題×割高": 2, "話題×データ不足": 3}
        results.sort(
            key=lambda r: (
                _CLASS_ORDER.get(r.get("classification", ""), 2),
                -(r.get("value_score") or 0),
            ),
        )

        return results[:top_n], market_context
