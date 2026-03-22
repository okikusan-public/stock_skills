"""Market dashboard — quantitative market overview (KIK-567).

Provides Fear & Greed score, VIX history/phase, yield curve analysis.
Uses yfinance only (no Grok API required).
"""

import time
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Fear & Greed Score (6-indicator composite)
# ---------------------------------------------------------------------------

def compute_fear_greed(client=None) -> dict:
    """Compute a Fear & Greed score from 6 market indicators.

    Indicators (each 0-100, higher = more greedy):
    1. VIX level (inverted: low VIX = greed)
    2. S&P500 RSI(14)
    3. S&P500 distance from SMA50
    4. S&P500 distance from SMA200
    5. S&P500 distance from 52-week high
    6. S&P500 volume ratio (current vs 20-day avg)

    Returns {score, label, indicators: [{name, value, signal}]}
    """
    if client is None:
        from src.data import yahoo_client as client  # noqa: N811

    indicators = []

    try:
        # S&P500 data
        sp_hist = client.get_price_history("^GSPC", period="1y")
        if sp_hist is not None and not sp_hist.empty:
            closes = sp_hist["Close"].dropna()

            # 1. RSI(14)
            rsi = _compute_rsi(closes, 14)
            if rsi is not None:
                # RSI 30=0(fear), 50=50, 70=100(greed)
                rsi_score = max(0, min(100, (rsi - 30) / 40 * 100))
                indicators.append({
                    "name": "S&P500 RSI(14)",
                    "value": round(rsi, 1),
                    "score": round(rsi_score, 1),
                    "signal": "Fear" if rsi < 40 else "Greed" if rsi > 60 else "Neutral",
                })

            # 2. SMA50 distance
            if len(closes) >= 50:
                sma50 = closes.rolling(50).mean().iloc[-1]
                dist50 = (closes.iloc[-1] - sma50) / sma50 * 100
                # -5%=0(fear), 0=50, +5%=100(greed)
                sma50_score = max(0, min(100, (dist50 + 5) / 10 * 100))
                indicators.append({
                    "name": "SMA50乖離率",
                    "value": f"{dist50:+.1f}%",
                    "score": round(sma50_score, 1),
                    "signal": "Fear" if dist50 < -2 else "Greed" if dist50 > 2 else "Neutral",
                })

            # 3. SMA200 distance
            if len(closes) >= 200:
                sma200 = closes.rolling(200).mean().iloc[-1]
                dist200 = (closes.iloc[-1] - sma200) / sma200 * 100
                sma200_score = max(0, min(100, (dist200 + 10) / 20 * 100))
                indicators.append({
                    "name": "SMA200乖離率",
                    "value": f"{dist200:+.1f}%",
                    "score": round(sma200_score, 1),
                    "signal": "Fear" if dist200 < -5 else "Greed" if dist200 > 5 else "Neutral",
                })

            # 4. 52-week high distance
            high_52w = closes.max()
            if high_52w > 0:
                dist_high = (closes.iloc[-1] - high_52w) / high_52w * 100
                # 0%=100(greed), -20%=0(fear)
                high_score = max(0, min(100, (dist_high + 20) / 20 * 100))
                indicators.append({
                    "name": "52週高値距離",
                    "value": f"{dist_high:+.1f}%",
                    "score": round(high_score, 1),
                    "signal": "Fear" if dist_high < -10 else "Greed" if dist_high > -3 else "Neutral",
                })

            # 5. Volume ratio
            if "Volume" in sp_hist.columns:
                vols = sp_hist["Volume"].dropna()
                if len(vols) >= 20:
                    avg_vol = vols.rolling(20).mean().iloc[-1]
                    if avg_vol > 0:
                        vol_ratio = vols.iloc[-1] / avg_vol
                        # High volume during decline = fear, low volume = neutral
                        # Simple: ratio > 1.5 during decline = fear
                        vol_score = max(0, min(100, 50 + (1 - vol_ratio) * 50))
                        indicators.append({
                            "name": "出来高比率",
                            "value": f"{vol_ratio:.2f}x",
                            "score": round(vol_score, 1),
                            "signal": "Fear" if vol_ratio > 1.3 else "Neutral",
                        })
    except Exception:
        pass

    # 6. VIX level
    try:
        vix_hist = client.get_price_history("^VIX", period="1mo")
        if vix_hist is not None and not vix_hist.empty:
            vix = float(vix_hist["Close"].dropna().iloc[-1])
            # VIX 10=100(greed), 20=50, 30=0(fear)
            vix_score = max(0, min(100, (30 - vix) / 20 * 100))
            indicators.append({
                "name": "VIX",
                "value": round(vix, 1),
                "score": round(vix_score, 1),
                "signal": "Fear" if vix > 25 else "Greed" if vix < 15 else "Neutral",
            })
    except Exception:
        pass

    if not indicators:
        return {"score": 50, "label": "Neutral", "indicators": []}

    avg_score = sum(i["score"] for i in indicators) / len(indicators)
    label = _fg_label(avg_score)

    return {
        "score": round(avg_score, 1),
        "label": label,
        "indicators": indicators,
    }


def _fg_label(score: float) -> str:
    if score <= 20:
        return "Extreme Fear"
    if score <= 40:
        return "Fear"
    if score <= 60:
        return "Neutral"
    if score <= 80:
        return "Greed"
    return "Extreme Greed"


def _compute_rsi(closes, period: int = 14) -> Optional[float]:
    """Compute RSI from a pandas Series of close prices."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# VIX History + Phase
# ---------------------------------------------------------------------------

def get_vix_history(client=None, period: str = "1mo") -> dict:
    """Get VIX history with phase classification.

    Phase: Low(<15), Normal(15-20), Elevated(20-25), High(25-30), Crisis(>30)

    Returns {current, phase, history: [{date, close}], trend}
    """
    if client is None:
        from src.data import yahoo_client as client  # noqa: N811

    try:
        hist = client.get_price_history("^VIX", period=period)
        if hist is None or hist.empty:
            return {"current": None, "phase": "Unknown", "history": [], "trend": "不明"}

        closes = hist["Close"].dropna()
        current = float(closes.iloc[-1])
        phase = _vix_phase(current)

        # Trend
        if len(closes) >= 5:
            recent_avg = closes.iloc[-5:].mean()
            older_avg = closes.iloc[:5].mean() if len(closes) >= 10 else closes.iloc[0]
            if recent_avg > older_avg * 1.1:
                trend = "上昇"
            elif recent_avg < older_avg * 0.9:
                trend = "低下"
            else:
                trend = "横ばい"
        else:
            trend = "不明"

        # Weekly samples for table
        history = []
        step = max(1, len(closes) // 5)
        for i in range(0, len(closes), step):
            dt = closes.index[i]
            history.append({
                "date": dt.strftime("%m/%d") if hasattr(dt, "strftime") else str(dt)[:5],
                "close": round(float(closes.iloc[i]), 2),
            })
        # Always include latest
        if history and history[-1]["close"] != round(current, 2):
            dt = closes.index[-1]
            history.append({
                "date": dt.strftime("%m/%d") if hasattr(dt, "strftime") else "now",
                "close": round(current, 2),
            })

        return {
            "current": round(current, 2),
            "phase": phase,
            "history": history,
            "trend": trend,
        }
    except Exception:
        return {"current": None, "phase": "Unknown", "history": [], "trend": "不明"}


def _vix_phase(vix: float) -> str:
    if vix < 15:
        return "Low (楽観)"
    if vix < 20:
        return "Normal (通常)"
    if vix < 25:
        return "Elevated (警戒)"
    if vix < 30:
        return "High (恐怖)"
    return "Crisis (パニック)"


# ---------------------------------------------------------------------------
# Yield Curve
# ---------------------------------------------------------------------------

_YIELD_TICKERS = {
    "3M": "^IRX",
    "5Y": "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}


def get_yield_curve(client=None) -> dict:
    """Get US Treasury yield curve with spread analysis.

    Returns {yields: {tenor: rate}, spread_10y_3m, spread_10y_2y,
             curve_status, history_10y: [{date, rate}]}
    """
    if client is None:
        from src.data import yahoo_client as client  # noqa: N811

    yields = {}
    for tenor, symbol in _YIELD_TICKERS.items():
        try:
            time.sleep(0.5)
            hist = client.get_price_history(symbol, period="5d")
            if hist is not None and not hist.empty:
                rate = float(hist["Close"].dropna().iloc[-1])
                yields[tenor] = round(rate, 3)
        except Exception:
            continue

    # Spreads
    rate_3m = yields.get("3M")
    rate_10y = yields.get("10Y")
    spread_10y_3m = round(rate_10y - rate_3m, 3) if rate_10y and rate_3m else None

    # Curve status
    if spread_10y_3m is not None:
        if spread_10y_3m < 0:
            curve_status = "逆イールド（景気後退シグナル）"
        elif spread_10y_3m < 0.5:
            curve_status = "フラット（警戒）"
        else:
            curve_status = "順イールド（通常）"
    else:
        curve_status = "不明"

    # 10Y history (1 month)
    history_10y = []
    try:
        hist = client.get_price_history("^TNX", period="1mo")
        if hist is not None and not hist.empty:
            closes = hist["Close"].dropna()
            step = max(1, len(closes) // 5)
            for i in range(0, len(closes), step):
                dt = closes.index[i]
                history_10y.append({
                    "date": dt.strftime("%m/%d") if hasattr(dt, "strftime") else str(dt)[:5],
                    "rate": round(float(closes.iloc[i]), 3),
                })
    except Exception:
        pass

    return {
        "yields": yields,
        "spread_10y_3m": spread_10y_3m,
        "curve_status": curve_status,
        "history_10y": history_10y,
    }
