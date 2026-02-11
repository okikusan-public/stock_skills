"""Volatility calculation utilities."""

import numpy as np
from typing import Optional

DEFAULT_RF = 0.005  # 0.5% Japan default


def calculate_hv(close_prices: list[float], window: int = 30) -> Optional[float]:
    """Annualized historical volatility from close prices.
    Returns None if insufficient data (need window+1 prices).
    Uses log returns, annualized with sqrt(252).
    """
    if len(close_prices) < window + 1:
        return None
    prices = np.array(close_prices[-(window + 1):], dtype=np.float64)
    if np.any(prices <= 0):
        return None
    log_returns = np.diff(np.log(prices))
    std = np.std(log_returns, ddof=1)
    return float(std * np.sqrt(252))


def calculate_upside_downside_vol(
    close_prices: list[float], window: int = 30
) -> tuple[Optional[float], Optional[float]]:
    """Separate upside and downside annualized volatility.
    Returns (upside_vol, downside_vol).
    """
    if len(close_prices) < window + 1:
        return (None, None)
    prices = np.array(close_prices[-(window + 1):], dtype=np.float64)
    if np.any(prices <= 0):
        return (None, None)
    log_returns = np.diff(np.log(prices))

    up_returns = log_returns[log_returns > 0]
    down_returns = log_returns[log_returns < 0]

    if len(up_returns) < 2:
        upside_vol = None
    else:
        upside_vol = float(np.std(up_returns, ddof=1) * np.sqrt(252))

    if len(down_returns) < 2:
        downside_vol = None
    else:
        downside_vol = float(np.std(down_returns, ddof=1) * np.sqrt(252))

    return (upside_vol, downside_vol)
