"""QueryScreener: EquityQuery-based value screening across 60+ regions."""

from typing import Optional

from src.core.screening.filters import apply_filters
from src.core.screening.indicators import (
    calculate_value_score,
    calculate_shareholder_return,
    calculate_shareholder_return_history,
    assess_return_stability,
)
from src.core.screening.query_builder import build_query, load_preset
from src.core.screening.technicals import detect_pullback_in_uptrend


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

        # Trailing dividend yield (actual, ratio form from yfinance)
        raw_div_trailing = quote.get("trailingAnnualDividendYield")
        if raw_div_trailing is not None and raw_div_trailing > 0.15:
            raw_div_trailing = None

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
            "dividend_yield_trailing": raw_div_trailing,
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
                criteria = load_preset(preset)
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
                # KIK-383: Return stability assessment
                sr_hist = calculate_shareholder_return_history(detail)
                stability = assess_return_stability(sr_hist)
                stock["return_stability"] = stability.get("stability")
                stock["return_stability_label"] = stability.get("label")
                stock["return_avg_rate"] = stability.get("avg_rate")
                stock["return_stability_reason"] = stability.get("reason")
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
