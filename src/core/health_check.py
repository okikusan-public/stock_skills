"""Portfolio health check engine (KIK-356).

Checks whether the investment thesis for each holding is still valid.
Uses alpha signals (change score) and technical indicators to generate
a 3-level alert system.

Alert levels:
  - early_warning: SMA50 break / RSI drop / 1 indicator deterioration
  - caution: SMA50 approaching SMA200 + indicator deterioration
  - exit: dead cross / multiple indicator deterioration / trend collapse
"""

import math

import numpy as np
import pandas as pd
from typing import Optional

from src.core.common import is_cash as _is_cash, is_etf as _is_etf

# Alert level constants
ALERT_NONE = "none"
ALERT_EARLY_WARNING = "early_warning"
ALERT_CAUTION = "caution"
ALERT_EXIT = "exit"

# Technical thresholds
SMA_APPROACHING_GAP = 0.02  # SMA50 within 2% of SMA200
RSI_PREV_THRESHOLD = 50  # Previous RSI level for drop detection
RSI_DROP_THRESHOLD = 40  # Current RSI level indicating a drop


def check_trend_health(hist: Optional[pd.DataFrame]) -> dict:
    """Analyze trend health from price history.

    Parameters
    ----------
    hist : pd.DataFrame or None
        DataFrame with Close and Volume columns.

    Returns
    -------
    dict
        Trend analysis with keys: trend, price_above_sma50,
        price_above_sma200, sma50_above_sma200, dead_cross,
        sma50_approaching_sma200, rsi, rsi_drop, current_price,
        sma50, sma200.
    """
    default = {
        "trend": "不明",
        "price_above_sma50": False,
        "price_above_sma200": False,
        "sma50_above_sma200": False,
        "dead_cross": False,
        "sma50_approaching_sma200": False,
        "rsi": float("nan"),
        "rsi_drop": False,
        "current_price": float("nan"),
        "sma50": float("nan"),
        "sma200": float("nan"),
        "cross_signal": "none",
        "days_since_cross": None,
        "cross_date": None,
    }

    if hist is None or not isinstance(hist, pd.DataFrame):
        return default
    if "Close" not in hist.columns or len(hist) < 200:
        return default

    close = hist["Close"]

    from src.core.screening.technicals import compute_rsi

    sma50 = close.rolling(window=50).mean()
    sma200 = close.rolling(window=200).mean()
    rsi_series = compute_rsi(close, period=14)

    current_price = float(close.iloc[-1])
    current_sma50 = float(sma50.iloc[-1])
    current_sma200 = float(sma200.iloc[-1])
    current_rsi = float(rsi_series.iloc[-1])

    price_above_sma50 = current_price > current_sma50
    price_above_sma200 = current_price > current_sma200
    sma50_above_sma200 = current_sma50 > current_sma200
    dead_cross = not sma50_above_sma200

    # --- Cross event detection (lookback 60 trading days) ---
    _CROSS_LOOKBACK = 60
    cross_signal = "none"
    days_since_cross = None
    cross_date = None

    max_scan = min(_CROSS_LOOKBACK, len(sma50) - 201)
    for i in range(max(0, max_scan)):
        idx = -1 - i
        prev_idx = idx - 1
        cur_above = sma50.iloc[idx] > sma200.iloc[idx]
        prev_above = sma50.iloc[prev_idx] > sma200.iloc[prev_idx]

        if cur_above and not prev_above:
            cross_signal = "golden_cross"
            days_since_cross = i
            idx_val = hist.index[idx]
            cross_date = str(idx_val.date()) if hasattr(idx_val, "date") else str(idx_val)
            break
        elif not cur_above and prev_above:
            cross_signal = "death_cross"
            days_since_cross = i
            idx_val = hist.index[idx]
            cross_date = str(idx_val.date()) if hasattr(idx_val, "date") else str(idx_val)
            break

    # SMA50 approaching SMA200 (gap < 2%)
    sma_gap = (
        abs(current_sma50 - current_sma200) / current_sma200
        if current_sma200 > 0
        else 0
    )
    sma50_approaching = sma_gap < SMA_APPROACHING_GAP

    # RSI drop: was > 50 five days ago and now < 40
    rsi_drop = False
    if len(rsi_series) >= 6:
        prev_rsi = float(rsi_series.iloc[-6])
        if not np.isnan(prev_rsi) and prev_rsi > RSI_PREV_THRESHOLD and current_rsi < RSI_DROP_THRESHOLD:
            rsi_drop = True

    # Trend determination
    if price_above_sma50 and sma50_above_sma200:
        trend = "上昇"
    elif sma50_approaching or (not price_above_sma50 and price_above_sma200):
        trend = "横ばい"
    else:
        trend = "下降"

    return {
        "trend": trend,
        "price_above_sma50": price_above_sma50,
        "price_above_sma200": price_above_sma200,
        "sma50_above_sma200": sma50_above_sma200,
        "dead_cross": dead_cross,
        "sma50_approaching_sma200": sma50_approaching,
        "rsi": round(current_rsi, 2),
        "rsi_drop": rsi_drop,
        "current_price": round(current_price, 2),
        "sma50": round(current_sma50, 2),
        "sma200": round(current_sma200, 2),
        "cross_signal": cross_signal,
        "days_since_cross": days_since_cross,
        "cross_date": cross_date,
    }


def check_change_quality(stock_detail: dict) -> dict:
    """Evaluate change quality (alpha signal) of a holding.

    Reuses alpha.py's compute_change_score() to assess whether the
    original investment thesis (fundamental improvement) is still valid.

    Parameters
    ----------
    stock_detail : dict
        From yahoo_client.get_stock_detail().

    Returns
    -------
    dict
        Keys: change_score, quality_pass, passed_count, indicators,
        earnings_penalty, quality_label.
    """
    if _is_etf(stock_detail):
        return {
            "change_score": 0,
            "quality_pass": False,
            "passed_count": 0,
            "indicators": {},
            "earnings_penalty": 0,
            "quality_label": "対象外",
            "is_etf": True,
        }

    from src.core.screening.alpha import compute_change_score

    result = compute_change_score(stock_detail)

    passed_count = result["passed_count"]

    if passed_count >= 3:
        quality_label = "良好"
    elif passed_count == 2:
        quality_label = "1指標↓"
    else:
        quality_label = "複数悪化"

    return {
        "change_score": result["change_score"],
        "quality_pass": result["quality_pass"],
        "passed_count": passed_count,
        "indicators": {
            "accruals": result["accruals"],
            "revenue_acceleration": result["revenue_acceleration"],
            "fcf_yield": result["fcf_yield"],
            "roe_trend": result["roe_trend"],
        },
        "earnings_penalty": result.get("earnings_penalty", 0),
        "quality_label": quality_label,
        "is_etf": False,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _finite_or_none(v):
    """Return v if finite number, else None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Long-term investment suitability thresholds (KIK-371)
# ---------------------------------------------------------------------------
_LT_ROE_HIGH = 0.15
_LT_ROE_LOW = 0.10
_LT_EPS_GROWTH_HIGH = 0.10
_LT_DIVIDEND_HIGH = 0.02
_LT_PER_OVERVALUED = 40
_LT_PER_SAFE = 25


def check_long_term_suitability(stock_detail: dict) -> dict:
    """Evaluate long-term holding suitability from fundamental data.

    Classifies a holding based on ROE, EPS growth, dividend yield, and PER.

    Parameters
    ----------
    stock_detail : dict
        From yahoo_client.get_stock_detail(). Expected keys:
        roe, eps_growth, dividend_yield, per.

    Returns
    -------
    dict
        Keys: label, roe_status, eps_growth_status, dividend_status,
        per_risk, score, summary.
    """
    symbol = stock_detail.get("symbol", "")

    if _is_cash(symbol):
        return {
            "label": "対象外",
            "roe_status": "n/a",
            "eps_growth_status": "n/a",
            "dividend_status": "n/a",
            "per_risk": "n/a",
            "score": 0,
            "summary": "-",
        }

    if _is_etf(stock_detail):
        return {
            "label": "対象外",
            "roe_status": "n/a",
            "eps_growth_status": "n/a",
            "dividend_status": "n/a",
            "per_risk": "n/a",
            "score": 0,
            "summary": "ETF",
        }

    roe = _finite_or_none(stock_detail.get("roe"))
    eps_growth = _finite_or_none(stock_detail.get("eps_growth"))
    dividend_yield = _finite_or_none(stock_detail.get("dividend_yield"))
    per = _finite_or_none(stock_detail.get("per"))

    # --- ROE classification ---
    if roe is None:
        roe_status = "unknown"
        roe_score = 0
    elif roe >= _LT_ROE_HIGH:
        roe_status = "high"
        roe_score = 2
    elif roe >= _LT_ROE_LOW:
        roe_status = "medium"
        roe_score = 1
    else:
        roe_status = "low"
        roe_score = 0

    # --- EPS Growth classification ---
    if eps_growth is None:
        eps_growth_status = "unknown"
        eps_score = 0
    elif eps_growth >= _LT_EPS_GROWTH_HIGH:
        eps_growth_status = "growing"
        eps_score = 2
    elif eps_growth >= 0:
        eps_growth_status = "flat"
        eps_score = 1
    else:
        eps_growth_status = "declining"
        eps_score = 0

    # --- Dividend classification ---
    if dividend_yield is None:
        dividend_status = "unknown"
        div_score = 0
    elif dividend_yield >= _LT_DIVIDEND_HIGH:
        dividend_status = "high"
        div_score = 1
    elif dividend_yield > 0:
        dividend_status = "medium"
        div_score = 0.5
    else:
        dividend_status = "low"
        div_score = 0

    # --- PER risk classification ---
    if per is None:
        per_risk = "unknown"
        per_score = 0
    elif per > _LT_PER_OVERVALUED:
        per_risk = "overvalued"
        per_score = -1
    elif per <= _LT_PER_SAFE:
        per_risk = "safe"
        per_score = 1
    else:
        per_risk = "moderate"
        per_score = 0

    total_score = roe_score + eps_score + div_score + per_score

    # --- Label determination ---
    if (roe_status == "high" and eps_growth_status == "growing"
            and dividend_status == "high"
            and per_risk not in ("overvalued", "unknown")):
        label = "長期向き"
    elif per_risk == "overvalued" or roe_status == "low":
        label = "短期向き"
    else:
        label = "要検討"

    # --- Summary string ---
    parts = []
    if roe_status == "high":
        parts.append("高ROE")
    elif roe_status == "low":
        parts.append("低ROE")
    if eps_growth_status == "growing":
        parts.append("EPS成長")
    elif eps_growth_status == "declining":
        parts.append("EPS減少")
    if dividend_status == "high":
        parts.append("高配当")
    if per_risk == "overvalued":
        parts.append("割高PER")
    # Count unknown fields for summary
    unknown_count = sum(1 for s in [roe_status, eps_growth_status, dividend_status, per_risk] if s == "unknown")
    if unknown_count > 0:
        parts.append(f"データ不足({unknown_count}項目)")

    summary = "・".join(parts) if parts else "データ不足"

    return {
        "label": label,
        "roe_status": roe_status,
        "eps_growth_status": eps_growth_status,
        "dividend_status": dividend_status,
        "per_risk": per_risk,
        "score": total_score,
        "summary": summary,
    }


# Value trap detection extracted to src/core/value_trap.py (KIK-392)
from src.core.value_trap import detect_value_trap as _detect_value_trap  # noqa: F401


def compute_alert_level(trend_health: dict, change_quality: dict, stock_detail=None) -> dict:
    """Compute 3-level alert from trend and change quality.

    Level priority: exit > caution > early_warning > none.

    Returns
    -------
    dict
        Keys: level, emoji, label, reasons.
    """
    reasons: list[str] = []
    level = ALERT_NONE

    trend = trend_health.get("trend", "不明")
    quality_label = change_quality.get("quality_label", "良好")
    dead_cross = trend_health.get("dead_cross", False)
    rsi_drop = trend_health.get("rsi_drop", False)
    price_above_sma50 = trend_health.get("price_above_sma50", True)
    sma50_approaching = trend_health.get("sma50_approaching_sma200", False)
    cross_signal = trend_health.get("cross_signal", "none")
    days_since_cross = trend_health.get("days_since_cross")
    cross_date = trend_health.get("cross_date")

    if quality_label == "対象外":
        # ETF: evaluate technical conditions only (no quality data)
        if not price_above_sma50:
            level = ALERT_EARLY_WARNING
            sma50_val = trend_health.get("sma50", 0)
            price_val = trend_health.get("current_price", 0)
            reasons.append(f"SMA50を下回り（現在{price_val}、SMA50={sma50_val}）")
        if dead_cross:
            level = ALERT_CAUTION
            reasons.append("デッドクロス")
        if rsi_drop:
            if level == ALERT_NONE:
                level = ALERT_EARLY_WARNING
            rsi_val = trend_health.get("rsi", 0)
            reasons.append(f"RSI急低下（{rsi_val}）")
    else:
        # --- EXIT ---
        # KIK-357: EXIT requires technical collapse AND fundamental deterioration.
        # Dead cross + good fundamentals = CAUTION (not EXIT).
        if dead_cross and quality_label == "複数悪化":
            level = ALERT_EXIT
            reasons.append("デッドクロス + 変化スコア複数悪化")
        elif dead_cross and trend == "下降":
            if quality_label == "良好":
                level = ALERT_CAUTION
                reasons.append("デッドクロス（ファンダメンタル良好のためCAUTION）")
            else:
                # quality_label is "1指標↓" — technical + fundamental confirm
                level = ALERT_EXIT
                reasons.append("トレンド崩壊（デッドクロス + ファンダ悪化）")

        # --- CAUTION ---
        elif sma50_approaching and quality_label in ("1指標↓", "複数悪化"):
            level = ALERT_CAUTION
            if quality_label == "複数悪化":
                reasons.append("変化スコア複数悪化")
            else:
                reasons.append("変化スコア1指標悪化")
            reasons.append("SMA50がSMA200に接近")
        elif quality_label == "複数悪化":
            level = ALERT_CAUTION
            reasons.append("変化スコア複数悪化")

        # --- EARLY WARNING ---
        elif not price_above_sma50:
            level = ALERT_EARLY_WARNING
            sma50_val = trend_health.get("sma50", 0)
            price_val = trend_health.get("current_price", 0)
            reasons.append(f"SMA50を下回り（現在{price_val}、SMA50={sma50_val}）")
        elif rsi_drop:
            level = ALERT_EARLY_WARNING
            rsi_val = trend_health.get("rsi", 0)
            reasons.append(f"RSI急低下（{rsi_val}）")
        elif quality_label == "1指標↓":
            level = ALERT_EARLY_WARNING
            reasons.append("変化スコア1指標悪化")

    # Recent death cross event: add date context to reasons
    if cross_signal == "death_cross" and days_since_cross is not None and days_since_cross <= 10:
        reasons.append(f"デッドクロス発生（{days_since_cross}日前、{cross_date}）")

    # Recent golden cross: positive signal -> early warning if no other alert
    if cross_signal == "golden_cross" and days_since_cross is not None and days_since_cross <= 20:
        if level == ALERT_NONE:
            level = ALERT_EARLY_WARNING
        reasons.append(
            f"ゴールデンクロス発生（{days_since_cross}日前、{cross_date}）"
            "- 上昇トレンド転換の可能性"
        )

    # Value trap detection (KIK-381)
    value_trap = _detect_value_trap(stock_detail)
    if value_trap["is_trap"]:
        for reason in value_trap["reasons"]:
            if reason not in reasons:
                reasons.append(reason)
        # Escalate to at least EARLY_WARNING
        if level == ALERT_NONE:
            level = ALERT_EARLY_WARNING

    level_map = {
        ALERT_NONE: ("", "なし"),
        ALERT_EARLY_WARNING: ("\u26a1", "早期警告"),
        ALERT_CAUTION: ("\u26a0", "注意"),
        ALERT_EXIT: ("\U0001f6a8", "撤退"),
    }
    emoji, label = level_map[level]

    return {
        "level": level,
        "emoji": emoji,
        "label": label,
        "reasons": reasons,
    }


def run_health_check(csv_path: str, client) -> dict:
    """Run health check on all portfolio holdings.

    For each holding:
    1. Fetch 1-year price history -> trend health (SMA, RSI)
    2. Fetch stock detail -> change quality (alpha score)
    3. Compute alert level

    Parameters
    ----------
    csv_path : str
        Path to portfolio CSV.
    client
        yahoo_client module (get_price_history, get_stock_detail).

    Returns
    -------
    dict
        Keys: positions, alerts (non-none only), summary.
    """
    from src.core.portfolio.portfolio_manager import get_snapshot

    snapshot = get_snapshot(csv_path, client)
    positions = snapshot.get("positions", [])

    empty_summary = {
        "total": 0,
        "healthy": 0,
        "early_warning": 0,
        "caution": 0,
        "exit": 0,
    }

    if not positions:
        return {"positions": [], "alerts": [], "summary": empty_summary}

    results: list[dict] = []
    alerts: list[dict] = []
    counts = {"healthy": 0, "early_warning": 0, "caution": 0, "exit": 0}

    for pos in positions:
        symbol = pos["symbol"]

        # Skip cash positions (e.g., JPY.CASH, USD.CASH)
        if _is_cash(symbol):
            continue

        # 1. Trend analysis
        hist = client.get_price_history(symbol, period="1y")
        trend_health = check_trend_health(hist)

        # 2. Change quality
        stock_detail = client.get_stock_detail(symbol)
        if stock_detail is None:
            stock_detail = {}
        change_quality = check_change_quality(stock_detail)

        # 3. Alert level
        alert = compute_alert_level(trend_health, change_quality, stock_detail=stock_detail)

        # 4. Long-term suitability (KIK-371)
        long_term = check_long_term_suitability(stock_detail)

        # 5. Value trap detection (KIK-381)
        value_trap = _detect_value_trap(stock_detail)

        result = {
            "symbol": symbol,
            "name": pos.get("name") or pos.get("memo", ""),
            "pnl_pct": pos.get("pnl_pct", 0),
            "trend_health": trend_health,
            "change_quality": change_quality,
            "alert": alert,
            "long_term": long_term,
            "value_trap": value_trap,
        }
        results.append(result)

        if alert["level"] != ALERT_NONE:
            alerts.append(result)
            counts[alert["level"]] = counts.get(alert["level"], 0) + 1
        else:
            counts["healthy"] += 1

    return {
        "positions": results,
        "alerts": alerts,
        "summary": {
            "total": len(results),
            **counts,
        },
    }
