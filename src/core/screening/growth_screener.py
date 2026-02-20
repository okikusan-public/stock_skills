"""GrowthScreener: pure growth (no value constraint) screening."""

from typing import Optional

from src.core.screening.query_builder import build_query, load_preset
from src.core.screening.query_screener import QueryScreener


class GrowthScreener:
    """Screen stocks for pure growth (no value constraint).

    Two-step pipeline:
      Step 1: EquityQuery for growth filtering (ROE, revenue growth, EPS growth, market cap)
      Step 2: Fetch stock detail for EPS growth rate, sort by EPS growth descending
    """

    def __init__(self, yahoo_client):
        """Initialise the screener.

        Parameters
        ----------
        yahoo_client : module or object
            Must expose ``screen_stocks()`` and ``get_stock_detail()``.
        """
        self.yahoo_client = yahoo_client

    def screen(
        self,
        region: str = "jp",
        top_n: int = 20,
        sector: Optional[str] = None,
    ) -> list[dict]:
        """Run the two-step growth screening pipeline.

        Parameters
        ----------
        region : str
            Market region code (e.g. 'jp', 'us', 'sg').
        top_n : int
            Maximum number of results to return.
        sector : str, optional
            Sector filter (e.g. 'Technology').

        Returns
        -------
        list[dict]
            Screened stocks sorted by eps_growth descending.
        """
        criteria = load_preset("growth")

        # Step 1: EquityQuery for growth-filtered stocks (sorted by market cap)
        query = build_query(criteria, region=region, sector=sector)

        # Fetch enough candidates for detail enrichment
        fetch_size = max(top_n * 3, 60)
        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=250,
            max_results=fetch_size,
            sort_field="intradaymarketcap",
            sort_asc=False,
        )

        if not raw_quotes:
            return []

        # Normalize quotes
        fundamentals: list[dict] = []
        for quote in raw_quotes:
            normalized = QueryScreener._normalize_quote(quote)
            fundamentals.append(normalized)

        # Step 2: Fetch stock detail for EPS growth, sort by growth
        results: list[dict] = []
        for stock in fundamentals:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            detail = self.yahoo_client.get_stock_detail(symbol)
            if detail is None:
                continue

            eps_growth = detail.get("eps_growth")
            if eps_growth is None or eps_growth <= 0:
                continue

            rev_growth = stock.get("revenue_growth") or detail.get("revenue_growth")

            results.append({
                "symbol": symbol,
                "name": stock.get("name"),
                "sector": stock.get("sector"),
                "price": stock.get("price"),
                "per": stock.get("per"),
                "forward_per": stock.get("forward_per"),
                "pbr": stock.get("pbr"),
                "roe": stock.get("roe"),
                "eps_growth": eps_growth,
                "revenue_growth": rev_growth,
                "market_cap": stock.get("market_cap"),
            })

        # Sort by EPS growth descending
        results.sort(key=lambda r: r.get("eps_growth", 0), reverse=True)
        return results[:top_n]
