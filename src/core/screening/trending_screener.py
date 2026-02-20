"""TrendingScreener: X (Twitter) trending stocks with fundamental enrichment."""

from typing import Optional

from src.core.screening.indicators import calculate_value_score


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
                    "dividend_yield_trailing": None,
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
                "dividend_yield_trailing": info.get("dividend_yield_trailing"),
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
