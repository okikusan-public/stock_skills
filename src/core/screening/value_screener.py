"""ValueScreener: legacy symbol-list-based value screening."""

import warnings
from typing import Optional

from src.core.screening.filters import apply_filters
from src.core.screening.indicators import calculate_value_score
from src.core.screening.query_builder import load_preset


class ValueScreener:
    """Screen stocks for value investment opportunities.

    .. deprecated::
        ValueScreener は非推奨です。QueryScreener を使用してください。
        ``--mode legacy`` は将来削除予定です。
    """

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
        warnings.warn(
            "ValueScreener は非推奨です。QueryScreener を使用してください。"
            " (--mode legacy は将来削除予定)",
            DeprecationWarning,
            stacklevel=2,
        )
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
                criteria = load_preset(preset)
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
                "dividend_yield_trailing": data.get("dividend_yield_trailing"),
                "roe": data.get("roe"),
                "value_score": score,
            })

        # Sort by value_score descending, take top N
        results.sort(key=lambda r: r["value_score"], reverse=True)
        return results[:top_n]
