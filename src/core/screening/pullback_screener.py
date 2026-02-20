"""PullbackScreener: pullback-in-uptrend entry opportunity screening."""

from typing import Optional

from src.core.screening.indicators import calculate_value_score
from src.core.screening.query_builder import build_query
from src.core.screening.query_screener import QueryScreener
from src.core.screening.technicals import detect_pullback_in_uptrend


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
                "dividend_yield_trailing": stock.get("dividend_yield_trailing"),
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
