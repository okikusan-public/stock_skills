"""Value stock screening engine."""

from pathlib import Path
from typing import Optional

import yaml

from src.core.filters import apply_filters
from src.core.indicators import calculate_value_score
from src.core.query_builder import build_query
from src.core.sharpe import compute_full_sharpe_score

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


class SharpeScreener:
    """Screen stocks using the Sharpe Ratio optimization framework."""

    def __init__(self, yahoo_client, market):
        self.yahoo_client = yahoo_client
        self.market = market

    def screen(
        self,
        symbols: Optional[list[str]] = None,
        top_n: int = 20,
    ) -> list[dict]:
        """Run SR screening. Stocks with fewer than 3 conditions are excluded."""
        if symbols is None:
            symbols = self.market.get_default_symbols()

        thresholds = self.market.get_thresholds()
        # SR framework uses its own thresholds (KIK-330 spec)
        thresholds["hv30_max"] = 0.25
        thresholds["per_max"] = 15.0
        thresholds["pbr_max"] = 1.5
        rf = thresholds.get("rf", 0.005)

        results: list[dict] = []

        for symbol in symbols:
            detail = self.yahoo_client.get_stock_detail(symbol)
            if detail is None:
                continue

            sr_result = compute_full_sharpe_score(detail, thresholds, rf=rf)
            if sr_result is None:
                continue

            results.append({
                "symbol": detail.get("symbol", symbol),
                "name": detail.get("name"),
                "price": detail.get("price"),
                "per": detail.get("per"),
                "pbr": detail.get("pbr"),
                "dividend_yield": detail.get("dividend_yield"),
                "roe": detail.get("roe"),
                "eps_growth": detail.get("eps_growth"),
                "hv30": sr_result["hv30"],
                "expected_return": sr_result["expected_return"],
                "adjusted_sr": sr_result["adjusted_sr"],
                "conditions_passed": sr_result["conditions_passed"],
                "condition_details": sr_result["condition_details"],
                "final_score": sr_result["final_score"],
            })

        results.sort(key=lambda r: r["final_score"], reverse=True)
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
        # dividendYield from screen results may be a percentage or ratio
        raw_div = quote.get("dividendYield")
        if raw_div is not None:
            # Yahoo screen sometimes returns as ratio (0.035), sometimes
            # as percentage (3.5).  Normalise: if > 1, divide by 100.
            if raw_div > 1:
                raw_div = raw_div / 100.0

        # returnOnEquity similarly may need normalisation
        raw_roe = quote.get("returnOnEquity")
        if raw_roe is not None and raw_roe > 1:
            raw_roe = raw_roe / 100.0

        # revenueGrowth / earningsGrowth may be percentages
        raw_rev_growth = quote.get("revenueGrowth")
        if raw_rev_growth is not None and abs(raw_rev_growth) > 5:
            raw_rev_growth = raw_rev_growth / 100.0

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
            "per": quote.get("trailingPE"),
            "forward_per": quote.get("forwardPE"),
            "pbr": quote.get("priceToBook"),
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

        Returns
        -------
        list[dict]
            Each dict contains: symbol, name, price, per, pbr,
            dividend_yield, roe, value_score, plus sector/industry/exchange.
            Sorted by value_score descending.
        """
        # Resolve criteria
        if criteria is None:
            if preset is not None:
                criteria = _load_preset(preset)
            else:
                criteria = {}

        # Build the EquityQuery
        query = build_query(criteria, region=region, exchange=exchange, sector=sector)

        # Request up to 250 (yf.screen max); we score and truncate later
        request_size = min(max(top_n, 50), 250)

        # Call yahoo_client.screen_stocks()
        raw_quotes = self.yahoo_client.screen_stocks(
            query,
            size=request_size,
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

        # Sort by value_score descending, take top N
        results.sort(key=lambda r: r["value_score"], reverse=True)
        return results[:top_n]
