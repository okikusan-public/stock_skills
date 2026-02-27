"""Market regime detection for adjustment advisor (KIK-496).

Classifies the current market environment into one of four regimes
(bull / bear / crash / neutral) using SMA50/SMA200 cross, RSI, and
drawdown from the 52-week high.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core.screening.technicals import compute_rsi


@dataclass
class MarketRegime:
    """Current market regime assessment."""

    regime: str  # "bull" | "bear" | "crash" | "neutral"
    sma50_above_200: bool
    rsi: float | None
    drawdown: float | None
    index_symbol: str


# Drawdown threshold for crash detection
_CRASH_DRAWDOWN = -0.20
# RSI thresholds
_BEAR_RSI_UPPER = 40
_BULL_RSI_LOWER = 50


def detect_regime(client, index_symbol: str = "^N225") -> MarketRegime:
    """Detect market regime from index price data.

    Parameters
    ----------
    client
        yahoo_client module with get_price_history().
    index_symbol : str
        Market index symbol (default: Nikkei 225).

    Returns
    -------
    MarketRegime
    """
    try:
        hist = client.get_price_history(index_symbol, period="1y")
    except Exception:
        return MarketRegime(
            regime="neutral",
            sma50_above_200=False,
            rsi=None,
            drawdown=None,
            index_symbol=index_symbol,
        )

    if hist is None or not isinstance(hist, pd.DataFrame):
        return MarketRegime(
            regime="neutral",
            sma50_above_200=False,
            rsi=None,
            drawdown=None,
            index_symbol=index_symbol,
        )

    if "Close" not in hist.columns or len(hist) < 200:
        return MarketRegime(
            regime="neutral",
            sma50_above_200=False,
            rsi=None,
            drawdown=None,
            index_symbol=index_symbol,
        )

    close = hist["Close"]
    sma50 = close.rolling(window=50).mean()
    sma200 = close.rolling(window=200).mean()
    rsi_series = compute_rsi(close, period=14)

    current_sma50 = float(sma50.iloc[-1])
    current_sma200 = float(sma200.iloc[-1])
    current_rsi = float(rsi_series.iloc[-1])
    sma50_above_200 = current_sma50 > current_sma200

    # Drawdown from 52-week high
    high_52w = float(close.max())
    current_price = float(close.iloc[-1])
    drawdown = (current_price - high_52w) / high_52w if high_52w > 0 else 0.0

    # Regime classification (crash takes priority)
    if drawdown <= _CRASH_DRAWDOWN:
        regime = "crash"
    elif not sma50_above_200 and current_rsi < _BEAR_RSI_UPPER:
        regime = "bear"
    elif sma50_above_200 and current_rsi > _BULL_RSI_LOWER:
        regime = "bull"
    else:
        regime = "neutral"

    return MarketRegime(
        regime=regime,
        sma50_above_200=sma50_above_200,
        rsi=round(current_rsi, 2),
        drawdown=round(drawdown, 4),
        index_symbol=index_symbol,
    )


# Index symbol mapping by region suffix
_INDEX_MAP = {
    ".T": "^N225",
    ".SI": "^STI",
    ".BK": "^SET.BK",
    ".KL": "^KLSE",
    ".JK": "^JKSE",
    ".HK": "^HSI",
    ".KS": "^KS11",
    ".TW": "^TWII",
    ".SS": "000001.SS",
    ".SZ": "399001.SZ",
    ".L": "^FTSE",
    ".DE": "^GDAXI",
    ".PA": "^FCHI",
    ".TO": "^GSPTSE",
    ".AX": "^AXJO",
    ".SA": "^BVSP",
    ".BO": "^BSESN",
    ".NS": "^NSEI",
}


def get_default_index_symbol(positions: list[dict]) -> str:
    """Infer the primary market index from portfolio positions.

    Counts region suffixes across all positions and returns the index
    symbol for the most common region. Defaults to ^N225 (Nikkei).
    """
    if not positions:
        return "^N225"

    suffix_counts: dict[str, int] = {}
    for pos in positions:
        symbol = pos.get("symbol", "")
        # Find the last dot-suffix
        dot_idx = symbol.rfind(".")
        if dot_idx > 0:
            suffix = symbol[dot_idx:]
            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
        else:
            # No suffix = US stock
            suffix_counts["US"] = suffix_counts.get("US", 0) + 1

    if not suffix_counts:
        return "^N225"

    top_suffix = max(suffix_counts, key=suffix_counts.get)

    if top_suffix == "US":
        return "^GSPC"

    return _INDEX_MAP.get(top_suffix, "^N225")
