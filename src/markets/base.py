"""Base class for market definitions."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

import yaml

EXCHANGES_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "exchanges.yaml"
)


def load_exchanges_config() -> dict:
    """Load the exchanges.yaml configuration file.

    Returns the full ``regions`` dict keyed by region code (e.g. 'jp', 'us').
    """
    with open(EXCHANGES_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("regions", {})


class Market(ABC):
    """Abstract base class representing a stock market."""

    name: str = "Market"

    @abstractmethod
    def format_ticker(self, code: str) -> str:
        """Convert a user-supplied code into a yfinance-compatible ticker symbol.

        Subclasses must implement this to add the appropriate exchange suffix.
        """

    @abstractmethod
    def get_default_symbols(self) -> list[str]:
        """Return a list of default ticker symbols (already formatted) for this market.

        This is kept as a fallback for when EquityQuery is not available or
        when the caller explicitly supplies a symbol list.
        """

    @abstractmethod
    def get_region(self) -> Union[str, list[str]]:
        """Return the yfinance EquityQuery region code(s) for this market.

        Single-region markets (e.g. Japan, US) return a ``str``.
        Multi-region markets (e.g. ASEAN) return a ``list[str]``.
        """

    @abstractmethod
    def get_exchanges(self) -> list[str]:
        """Return the yfinance EquityQuery exchange code(s) for this market.

        Examples: ``['JPX']``, ``['NMS', 'NYQ']``, ``['SES', 'SET', 'KLS', 'JKT', 'PHP']``.
        """

    def get_thresholds(self) -> dict:
        """Return default thresholds for value-stock screening.

        Subclasses may override to customise per-market criteria.
        """
        return {
            "per_max": 15.0,
            "pbr_max": 1.0,
            "dividend_yield_min": 0.03,  # 3%
            "roe_min": 0.08,             # 8%
        }

    def get_equity_query(self) -> dict:
        """Return a base EquityQuery filter dict for this market.

        The returned dict contains ``region`` and ``exchange`` keys suitable
        for use with ``yfinance.EquityQuery``.  Subclasses may override to
        add additional filters.

        Returns
        -------
        dict
            ``{"region": ..., "exchanges": [...]}`` where *region* is a str
            or list[str] and *exchanges* is a list of exchange codes.
        """
        return {
            "region": self.get_region(),
            "exchanges": self.get_exchanges(),
        }
