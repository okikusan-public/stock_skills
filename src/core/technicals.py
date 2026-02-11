"""Technical indicators for pullback-in-uptrend screening (KIK-332)."""

import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI using Wilder's smoothing method (exponential moving average)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # Wilder's smoothing: alpha = 1/period
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_bollinger_bands(
    close: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, middle, lower) Bollinger Bands."""
    middle = close.rolling(window=period).mean()
    rolling_std = close.rolling(window=period).std()
    upper = middle + std_dev * rolling_std
    lower = middle - std_dev * rolling_std
    return upper, middle, lower


def detect_pullback_in_uptrend(hist: pd.DataFrame) -> dict:
    """Detect pullback buying opportunity in an uptrend.

    Parameters
    ----------
    hist : pd.DataFrame
        DataFrame from yfinance ticker.history() with Close and Volume columns.

    Returns
    -------
    dict
        Pullback analysis results with keys: uptrend, is_pullback, pullback_pct,
        bounce_signal, bounce_score, bounce_details, rsi, volume_ratio, sma50,
        sma200, current_price, recent_high, all_conditions.
    """
    # Default result for insufficient data
    default = {
        "uptrend": False,
        "is_pullback": False,
        "pullback_pct": 0.0,
        "bounce_signal": False,
        "bounce_score": 0.0,
        "bounce_details": {
            "rsi_reversal": False,
            "rsi_depth_bonus": False,
            "bb_proximity": False,
            "volume_surge": False,
            "price_reversal": False,
            "lookback_day": 0,
        },
        "rsi": float("nan"),
        "volume_ratio": float("nan"),
        "sma50": float("nan"),
        "sma200": float("nan"),
        "current_price": float("nan"),
        "recent_high": float("nan"),
        "all_conditions": False,
    }

    close = hist["Close"]
    volume = hist["Volume"]

    # 200-day MA needs ~200 data points
    if len(close) < 200:
        return default

    # Moving averages
    sma50 = close.rolling(window=50).mean()
    sma200 = close.rolling(window=200).mean()

    current_price = float(close.iloc[-1])
    current_sma50 = float(sma50.iloc[-1])
    current_sma200 = float(sma200.iloc[-1])

    # RSI
    rsi_series = compute_rsi(close, period=14)
    current_rsi = float(rsi_series.iloc[-1])
    prev_rsi = float(rsi_series.iloc[-2]) if len(rsi_series) >= 2 else float("nan")

    # Volume ratio: 5-day avg / 20-day avg
    vol_5 = volume.rolling(window=5).mean().iloc[-1]
    vol_20 = volume.rolling(window=20).mean().iloc[-1]
    volume_ratio = float(vol_5 / vol_20) if vol_20 > 0 else float("nan")

    # Recent 60-day high
    recent_high = float(close.iloc[-60:].max())

    # Pullback percentage from recent high
    pullback_pct = (current_price - recent_high) / recent_high if recent_high > 0 else 0.0

    # --- Condition 1: Uptrend ---
    uptrend = (current_price > current_sma200) and (current_sma50 > current_sma200)

    # --- Condition 2: Pullback depth ---
    is_pullback = (
        (-0.20 <= pullback_pct <= -0.05)
        and (current_price > current_sma200)
    )

    # --- Condition 3: Bounce signal (score-based with lookback) ---
    _, _, lower_band = compute_bollinger_bands(close, period=20, std_dev=2.0)

    lookback = 5  # Check last 5 trading days for bounce signals
    bounce_score = 0.0
    bounce_details: dict = {
        "rsi_reversal": False,
        "rsi_depth_bonus": False,
        "bb_proximity": False,
        "volume_surge": False,
        "price_reversal": False,
        "lookback_day": 0,
    }

    for offset in range(lookback):
        idx = -1 - offset
        if abs(idx) >= len(close) or abs(idx) >= len(rsi_series):
            break

        day_rsi = float(rsi_series.iloc[idx])
        day_prev_rsi = float(rsi_series.iloc[idx - 1]) if abs(idx - 1) < len(rsi_series) else float("nan")
        day_close = float(close.iloc[idx])
        day_prev_close = float(close.iloc[idx - 1]) if abs(idx - 1) < len(close) else float("nan")
        day_lower = float(lower_band.iloc[idx]) if abs(idx) < len(lower_band) and not np.isnan(lower_band.iloc[idx]) else float("nan")

        # Volume ratio for this specific day
        if abs(idx) < len(volume):
            day_vol_5 = volume.iloc[max(0, len(volume) + idx - 4) : len(volume) + idx + 1].mean()
            day_vol_20 = volume.iloc[max(0, len(volume) + idx - 19) : len(volume) + idx + 1].mean()
            day_volume_ratio = float(day_vol_5 / day_vol_20) if day_vol_20 > 0 else float("nan")
        else:
            day_volume_ratio = float("nan")

        day_score = 0.0
        day_details: dict = {
            "rsi_reversal": False,
            "rsi_depth_bonus": False,
            "bb_proximity": False,
            "volume_surge": False,
            "price_reversal": False,
        }

        # RSI reversal: RSI in 25-50 zone and turning up (40 pts)
        if (
            25.0 <= day_rsi <= 50.0
            and not np.isnan(day_prev_rsi)
            and day_rsi > day_prev_rsi
        ):
            day_score += 40.0
            day_details["rsi_reversal"] = True

        # RSI depth bonus: deep correction RSI 25-35 (15 pts)
        if 25.0 <= day_rsi <= 35.0:
            day_score += 15.0
            day_details["rsi_depth_bonus"] = True

        # BB lower proximity: price within 1.02x of lower band (25 pts)
        if not np.isnan(day_lower) and day_lower > 0 and day_close <= day_lower * 1.02:
            day_score += 25.0
            day_details["bb_proximity"] = True

        # Volume surge bonus: volume_ratio > 1.2 (10 pts)
        if not np.isnan(day_volume_ratio) and day_volume_ratio > 1.2:
            day_score += 10.0
            day_details["volume_surge"] = True

        # Price reversal: close > previous close (10 pts)
        if not np.isnan(day_prev_close) and day_close > day_prev_close:
            day_score += 10.0
            day_details["price_reversal"] = True

        if day_score > bounce_score:
            bounce_score = day_score
            bounce_details = {**day_details, "lookback_day": offset}

    bounce_signal = bounce_score >= 40.0

    all_conditions = uptrend and is_pullback and bounce_signal

    return {
        "uptrend": uptrend,
        "is_pullback": is_pullback,
        "pullback_pct": round(pullback_pct, 4),
        "bounce_signal": bounce_signal,
        "bounce_score": round(bounce_score, 2),
        "bounce_details": bounce_details,
        "rsi": round(current_rsi, 2),
        "volume_ratio": round(volume_ratio, 4) if not np.isnan(volume_ratio) else float("nan"),
        "sma50": round(current_sma50, 2),
        "sma200": round(current_sma200, 2),
        "current_price": round(current_price, 2),
        "recent_high": round(recent_high, 2),
        "all_conditions": all_conditions,
    }
