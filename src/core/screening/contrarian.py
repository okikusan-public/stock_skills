"""Contrarian signal: detect oversold stocks with solid fundamentals (KIK-504, KIK-519).

Scores stocks on three or four axes:
  1. Technical contrarian (40pt / 30pt with sentiment): RSI oversold, SMA200 deviation, BB breach, volume surge
  2. Valuation contrarian (30pt / 25pt with sentiment): low PER/PBR with healthy earnings (inverse of value trap)
  3. Fundamental divergence (30pt / 25pt with sentiment): strong FCF/ROE/dividend despite price drop
  4. Sentiment contrarian (20pt, optional): negative X sentiment as contrarian signal (KIK-519)

Without Grok: 40+30+30 = 100pt.  With Grok: 30+25+25+20 = 100pt.
Grade: A(>=70) B(>=50) C(>=30) D(<30).
"""

import numpy as np
import pandas as pd

from src.core.common import finite_or_none
from src.core.screening.technicals import compute_rsi, compute_bollinger_bands


# ---------------------------------------------------------------------------
# 1. Technical contrarian -- 40 pts
# ---------------------------------------------------------------------------

def compute_technical_contrarian(hist: pd.DataFrame) -> dict:
    """Technical contrarian score (40pt max).

    Sub-signals:
    - RSI oversold: 0-15pt
    - SMA200 deviation (downside): 0-10pt
    - Bollinger Band lower breach: 0-10pt
    - Volume surge (selling climax): 0-5pt
    """
    default = {
        "score": 0.0,
        "rsi": None,
        "sma200_deviation": None,
        "bb_position": None,
        "volume_surge": None,
        "details": {},
    }

    if hist is None or not isinstance(hist, pd.DataFrame):
        return default
    if "Close" not in hist.columns or len(hist) < 200:
        return default

    close = hist["Close"]
    current_price = float(close.iloc[-1])

    # RSI
    rsi_series = compute_rsi(close, period=14)
    current_rsi = float(rsi_series.iloc[-1])
    if np.isnan(current_rsi):
        return default

    # SMA200
    sma200 = close.rolling(window=200).mean()
    current_sma200 = float(sma200.iloc[-1])
    sma200_dev = (current_price - current_sma200) / current_sma200 if current_sma200 > 0 else 0.0

    # Bollinger Bands
    _, _, lower_band = compute_bollinger_bands(close, period=20, std_dev=2.0)
    current_lower = float(lower_band.iloc[-1]) if not np.isnan(lower_band.iloc[-1]) else None

    # Volume ratio (5-day / 20-day)
    if "Volume" in hist.columns and len(hist) >= 20:
        volume = hist["Volume"]
        vol_5 = float(volume.iloc[-5:].mean())
        vol_20 = float(volume.iloc[-20:].mean())
        vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 0.0
    else:
        vol_ratio = 0.0

    # --- RSI score (0-15pt) ---
    if current_rsi < 20:
        rsi_score = 15.0
    elif current_rsi < 25:
        rsi_score = 12.0
    elif current_rsi < 30:
        rsi_score = 8.0
    elif current_rsi < 35:
        rsi_score = 4.0
    else:
        rsi_score = 0.0

    # --- SMA200 deviation score (0-10pt) ---
    if sma200_dev < -0.20:
        sma_score = 10.0
    elif sma200_dev < -0.15:
        sma_score = 8.0
    elif sma200_dev < -0.10:
        sma_score = 5.0
    elif sma200_dev < -0.05:
        sma_score = 2.0
    else:
        sma_score = 0.0

    # --- Bollinger Band score (0-10pt) ---
    bb_score = 0.0
    bb_pos = None
    if current_lower is not None and current_lower > 0:
        bb_pos = current_price / current_lower
        if current_price < current_lower:
            bb_score = 10.0
        elif current_price < current_lower * 1.02:
            bb_score = 6.0
        elif current_price < current_lower * 1.05:
            bb_score = 3.0

    # --- Volume surge score (0-5pt) ---
    if vol_ratio > 2.0:
        vol_score = 5.0
    elif vol_ratio > 1.5:
        vol_score = 3.0
    elif vol_ratio > 1.2:
        vol_score = 1.0
    else:
        vol_score = 0.0

    total = rsi_score + sma_score + bb_score + vol_score

    return {
        "score": total,
        "rsi": round(current_rsi, 2),
        "sma200_deviation": round(sma200_dev, 4),
        "bb_position": round(bb_pos, 4) if bb_pos is not None else None,
        "volume_surge": round(vol_ratio, 2),
        "details": {
            "rsi_score": rsi_score,
            "sma_score": sma_score,
            "bb_score": bb_score,
            "vol_score": vol_score,
        },
    }


# ---------------------------------------------------------------------------
# 2. Valuation contrarian -- 30 pts
# ---------------------------------------------------------------------------

def compute_valuation_contrarian(stock_data: dict) -> dict:
    """Valuation contrarian score (30pt max).

    Inverse of value trap logic:
    - Value trap: low PER + deteriorating earnings = trap
    - Contrarian: low PER + stable/growing earnings = opportunity

    Sub-signals:
    - PER contrarian (low PER + eps_growth >= 0): 0-15pt
    - PBR contrarian (low PBR + ROE > 5%): 0-15pt
    """
    per = finite_or_none(stock_data.get("per"))
    pbr = finite_or_none(stock_data.get("pbr"))
    roe = finite_or_none(stock_data.get("roe"))
    eps_growth = finite_or_none(stock_data.get("eps_growth"))

    # --- PER contrarian (0-15pt) ---
    per_score = 0.0
    if per is not None and per > 0:
        if eps_growth is not None and eps_growth >= 0:
            if per < 8:
                per_score = 15.0
            elif per < 10:
                per_score = 12.0
            elif per < 12 and eps_growth > 0:
                per_score = 8.0
        if per_score == 0.0 and per < 15:
            per_score = 4.0

    # --- PBR contrarian (0-15pt) ---
    pbr_score = 0.0
    if pbr is not None and pbr > 0:
        if roe is not None and roe > 0.05:
            if pbr < 0.5:
                pbr_score = 15.0
            elif pbr < 0.8:
                pbr_score = 12.0
            elif pbr < 1.0 and roe > 0.08:
                pbr_score = 8.0
        if pbr_score == 0.0 and pbr < 1.5:
            pbr_score = 4.0

    total = per_score + pbr_score

    return {
        "score": total,
        "per_signal": per_score,
        "pbr_signal": pbr_score,
        "details": {
            "per": per,
            "pbr": pbr,
            "roe": roe,
            "eps_growth": eps_growth,
        },
    }


# ---------------------------------------------------------------------------
# 3. Fundamental divergence -- 30 pts
# ---------------------------------------------------------------------------

def compute_fundamental_divergence(stock_data: dict) -> dict:
    """Fundamental divergence score (30pt max).

    Detects "price down but fundamentals solid":
    - FCF yield (cash generation power): 0-10pt
    - ROE maintenance (profitability intact): 0-10pt
    - Dividend/return maintenance (management confidence): 0-10pt
    """
    fcf = finite_or_none(stock_data.get("fcf"))
    market_cap = finite_or_none(stock_data.get("market_cap"))
    roe = finite_or_none(stock_data.get("roe"))
    div_yield = finite_or_none(
        stock_data.get("dividend_yield_trailing")
        or stock_data.get("dividend_yield")
    )

    # --- FCF yield score (0-10pt) ---
    fcf_score = 0.0
    fcf_yield = None
    if fcf is not None and market_cap is not None and market_cap > 0:
        fcf_yield = fcf / market_cap
        if fcf_yield > 0.10:
            fcf_score = 10.0
        elif fcf_yield > 0.07:
            fcf_score = 8.0
        elif fcf_yield > 0.05:
            fcf_score = 5.0
        elif fcf_yield > 0.03:
            fcf_score = 2.0

    # --- ROE score (0-10pt) ---
    roe_score = 0.0
    if roe is not None:
        if roe > 0.15:
            roe_score = 10.0
        elif roe > 0.10:
            roe_score = 8.0
        elif roe > 0.08:
            roe_score = 5.0
        elif roe > 0.05:
            roe_score = 2.0

    # --- Return score (0-10pt) ---
    return_score = 0.0
    if div_yield is not None:
        if div_yield > 0.05:
            return_score = 10.0
        elif div_yield > 0.03:
            return_score = 8.0
        elif div_yield > 0.02:
            return_score = 5.0
        elif div_yield > 0.01:
            return_score = 2.0

    total = fcf_score + roe_score + return_score

    return {
        "score": total,
        "fcf_signal": fcf_score,
        "roe_signal": roe_score,
        "return_signal": return_score,
        "details": {
            "fcf_yield": round(fcf_yield, 4) if fcf_yield is not None else None,
            "roe": roe,
            "dividend_yield": div_yield,
        },
    }


# ---------------------------------------------------------------------------
# 4. Sentiment contrarian -- 20 pts (optional, requires Grok API, KIK-519)
# ---------------------------------------------------------------------------

def compute_sentiment_contrarian(sentiment_score: float | None) -> dict:
    """Sentiment contrarian score (20pt max, KIK-519).

    Uses Grok X-sentiment score (-1 to 1).
    Negative sentiment + solid fundamentals = contrarian opportunity.

    Score mapping:
    - sentiment < -0.5 → 20pt (very negative — strong contrarian signal)
    - sentiment < -0.3 → 15pt (negative)
    - sentiment < -0.1 → 10pt (slightly negative)
    - sentiment < 0.1  → 5pt  (neutral)
    - sentiment >= 0.1 → 0pt  (positive — no contrarian signal)
    """
    default = {
        "score": 0.0,
        "sentiment_score": sentiment_score,
        "details": {},
    }

    if sentiment_score is None:
        return default

    if sentiment_score < -0.5:
        score = 20.0
    elif sentiment_score < -0.3:
        score = 15.0
    elif sentiment_score < -0.1:
        score = 10.0
    elif sentiment_score < 0.1:
        score = 5.0
    else:
        score = 0.0

    return {
        "score": score,
        "sentiment_score": sentiment_score,
        "details": {
            "raw_score": sentiment_score,
            "contrarian_pts": score,
        },
    }


# ---------------------------------------------------------------------------
# Composite contrarian score
# ---------------------------------------------------------------------------

# Weight constants for 4-axis mode (KIK-519)
_W_TECH_4AXIS = 30
_W_VAL_4AXIS = 25
_W_FUND_4AXIS = 25
_W_SENT_4AXIS = 20

# Original max scores per axis (for normalization)
_MAX_TECH = 40.0
_MAX_VAL = 30.0
_MAX_FUND = 30.0
_MAX_SENT = 20.0


def compute_contrarian_score(
    hist: pd.DataFrame | None,
    stock_data: dict,
    sentiment_score: float | None = None,
) -> dict:
    """Composite contrarian score (0-100pt).

    Without Grok: Technical 40pt + Valuation 30pt + Fundamental 30pt = 100pt.
    With Grok:    Technical 30pt + Valuation 25pt + Fundamental 25pt + Sentiment 20pt = 100pt.

    Parameters
    ----------
    sentiment_score : float or None
        Grok X-sentiment score (-1 to 1). When provided, enables 4-axis scoring.

    Returns dict with:
        contrarian_score, technical, valuation, fundamental,
        sentiment (only when sentiment_score is provided),
        grade ("A"/"B"/"C"/"D"), is_contrarian (score >= 50).
    """
    tech = compute_technical_contrarian(hist)
    val = compute_valuation_contrarian(stock_data)
    fund = compute_fundamental_divergence(stock_data)

    if sentiment_score is not None:
        sent = compute_sentiment_contrarian(sentiment_score)
        # 4-axis: normalize each axis to new weight
        scaled_tech = (tech["score"] / _MAX_TECH) * _W_TECH_4AXIS if tech["score"] > 0 else 0
        scaled_val = (val["score"] / _MAX_VAL) * _W_VAL_4AXIS if val["score"] > 0 else 0
        scaled_fund = (fund["score"] / _MAX_FUND) * _W_FUND_4AXIS if fund["score"] > 0 else 0
        scaled_sent = (sent["score"] / _MAX_SENT) * _W_SENT_4AXIS if sent["score"] > 0 else 0
        total = scaled_tech + scaled_val + scaled_fund + scaled_sent
    else:
        sent = None
        # 3-axis: original weights (40 + 30 + 30 = 100)
        total = tech["score"] + val["score"] + fund["score"]

    total = min(total, 100.0)

    if total >= 70:
        grade = "A"
    elif total >= 50:
        grade = "B"
    elif total >= 30:
        grade = "C"
    else:
        grade = "D"

    result = {
        "contrarian_score": round(total, 1),
        "technical": tech,
        "valuation": val,
        "fundamental": fund,
        "grade": grade,
        "is_contrarian": total >= 50,
    }
    if sent is not None:
        result["sentiment"] = sent

    return result
