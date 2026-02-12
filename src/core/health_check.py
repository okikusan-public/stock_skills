"""Portfolio health check engine (KIK-356).

Checks whether the investment thesis for each holding is still valid.
Uses alpha signals (change score) and technical indicators to generate
a 3-level alert system.

Alert levels:
  - early_warning: SMA50 break / RSI drop / 1 indicator deterioration
  - caution: SMA50 approaching SMA200 + indicator deterioration
  - exit: dead cross / multiple indicator deterioration / trend collapse
"""

import numpy as np
import pandas as pd
from typing import Optional

# Alert level constants
ALERT_NONE = "none"
ALERT_EARLY_WARNING = "early_warning"
ALERT_CAUTION = "caution"
ALERT_EXIT = "exit"


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
    }

    if hist is None or not isinstance(hist, pd.DataFrame):
        return default
    if "Close" not in hist.columns or len(hist) < 200:
        return default

    close = hist["Close"]

    from src.core.technicals import compute_rsi

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

    # SMA50 approaching SMA200 (gap < 2%)
    sma_gap = (
        abs(current_sma50 - current_sma200) / current_sma200
        if current_sma200 > 0
        else 0
    )
    sma50_approaching = sma_gap < 0.02

    # RSI drop: was > 50 five days ago and now < 40
    rsi_drop = False
    if len(rsi_series) >= 6:
        prev_rsi = float(rsi_series.iloc[-6])
        if not np.isnan(prev_rsi) and prev_rsi > 50 and current_rsi < 40:
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
    }


def _is_etf(stock_detail: dict) -> bool:
    """Return True if stock_detail looks like an ETF (lacks fundamental data)."""
    if stock_detail.get("quoteType") == "ETF":
        return True
    info = stock_detail.get("info", stock_detail)
    has_sector = info.get("sector") is not None
    has_net_income = stock_detail.get("net_income_stmt") is not None
    has_operating_cf = stock_detail.get("operating_cashflow") is not None
    has_revenue_hist = stock_detail.get("revenue_history") is not None
    if not has_sector and not has_net_income and not has_operating_cf and not has_revenue_hist:
        return True
    return False


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

    from src.core.alpha import compute_change_score

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


def compute_alert_level(trend_health: dict, change_quality: dict) -> dict:
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
    from src.core.portfolio_manager import get_snapshot

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

        # 1. Trend analysis
        hist = client.get_price_history(symbol, period="1y")
        trend_health = check_trend_health(hist)

        # 2. Change quality
        stock_detail = client.get_stock_detail(symbol)
        if stock_detail is None:
            stock_detail = {}
        change_quality = check_change_quality(stock_detail)

        # 3. Alert level
        alert = compute_alert_level(trend_health, change_quality)

        result = {
            "symbol": symbol,
            "name": pos.get("name") or pos.get("memo", ""),
            "pnl_pct": pos.get("pnl_pct", 0),
            "trend_health": trend_health,
            "change_quality": change_quality,
            "alert": alert,
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
