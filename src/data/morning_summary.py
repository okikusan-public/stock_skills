"""Morning summary: anomaly detection for portfolio (KIK-717).

Detects exit-rule hits, RSI extremes, upcoming earnings, and VIX spikes.
Pure data functions — no judgment, no recommendations.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np

from src.data.common import safe_float


# ---------------------------------------------------------------------------
# Alert types and thresholds
# ---------------------------------------------------------------------------

ALERT_THRESHOLDS = {
    "exit_rule_pct": -15.0,       # exit-rule default (%)
    "hard_stop_pct": -20.0,       # hard stop loss (%)
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "earnings_days": 7,           # days before earnings to alert
    "vix_elevated": 25,
}


def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    """Calculate RSI(14) from close prices."""
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def detect_alerts(
    positions: list[dict],
    infos: dict[str, dict],
    histories: dict[str, list[float]],
    vix_price: float | None = None,
    prev_alerts: list[dict] | None = None,
) -> list[dict]:
    """Detect anomalies across portfolio holdings.

    Parameters
    ----------
    positions : list[dict]
        Portfolio from load_portfolio().
    infos : dict[str, dict]
        {symbol: get_stock_info() result}.
    histories : dict[str, list[float]]
        {symbol: list of close prices (latest last)}.
    vix_price : float | None
        Current VIX value.
    prev_alerts : list[dict] | None
        Previous day's alerts for state-change filtering.

    Returns
    -------
    list[dict]
        List of alert dicts with keys: symbol, type, severity, message, value.
    """
    alerts = []
    today = date.today().isoformat()
    thr = ALERT_THRESHOLDS
    prev_symbols_types = set()
    if prev_alerts:
        prev_symbols_types = {(a["symbol"], a["type"]) for a in prev_alerts}

    for pos in positions:
        sym = pos["symbol"]
        info = infos.get(sym)
        if not info:
            continue

        price = safe_float(info.get("price"))
        cost = safe_float(pos.get("cost_price"))

        # 1. Exit-rule: P&L threshold
        if price > 0 and cost > 0:
            pnl_pct = (price - cost) / cost * 100
            if pnl_pct <= thr["hard_stop_pct"]:
                alerts.append({
                    "symbol": sym, "type": "hard_stop",
                    "severity": "CRITICAL",
                    "message": f"損益{pnl_pct:+.1f}% → 損切りライン(-20%)到達",
                    "value": pnl_pct,
                })
            elif pnl_pct <= thr["exit_rule_pct"]:
                alerts.append({
                    "symbol": sym, "type": "exit_rule",
                    "severity": "CRITICAL",
                    "message": f"損益{pnl_pct:+.1f}% → exit-rule(-15%)到達",
                    "value": pnl_pct,
                })

        # 2. RSI extremes
        closes = histories.get(sym, [])
        rsi = _calc_rsi(closes)
        if rsi is not None:
            if rsi >= thr["rsi_overbought"]:
                alerts.append({
                    "symbol": sym, "type": "rsi_high",
                    "severity": "INFO",
                    "message": f"RSI {rsi:.1f} → 買われすぎ圏",
                    "value": rsi,
                })
            elif rsi <= thr["rsi_oversold"]:
                alerts.append({
                    "symbol": sym, "type": "rsi_low",
                    "severity": "INFO",
                    "message": f"RSI {rsi:.1f} → 売られすぎ圏",
                    "value": rsi,
                })

        # 3. Upcoming earnings
        next_earnings = pos.get("next_earnings") or ""
        if next_earnings:
            try:
                earn_date = datetime.strptime(next_earnings, "%Y-%m-%d").date()
                days_until = (earn_date - date.today()).days
                if 0 <= days_until <= thr["earnings_days"]:
                    alerts.append({
                        "symbol": sym, "type": "earnings_soon",
                        "severity": "INFO",
                        "message": f"決算{next_earnings}（残{days_until}日）",
                        "value": days_until,
                    })
            except ValueError:
                pass

    # 4. VIX
    if vix_price is not None and vix_price >= thr["vix_elevated"]:
        alerts.append({
            "symbol": "^VIX", "type": "vix_high",
            "severity": "CRITICAL" if vix_price >= 30 else "INFO",
            "message": f"VIX {vix_price:.1f} → {'急騰' if vix_price >= 30 else '警戒水準'}",
            "value": vix_price,
        })

    # 5. State-change filter: remove alerts that existed yesterday with same symbol+type
    if prev_alerts:
        alerts = [a for a in alerts
                  if (a["symbol"], a["type"]) not in prev_symbols_types]

    # Sort by severity (CRITICAL first)
    severity_order = {"CRITICAL": 0, "INFO": 1}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 2))

    return alerts


def format_morning_summary(alerts: list[dict], pf_total: float | None = None) -> str:
    """Format alerts into a human-readable morning summary.

    Parameters
    ----------
    alerts : list[dict]
        Output of detect_alerts().
    pf_total : float | None
        PF total value for context.

    Returns
    -------
    str
        Formatted summary string.
    """
    today_str = date.today().strftime("%m/%d")
    weekday = ["月", "火", "水", "木", "金", "土", "日"][date.today().weekday()]

    if not alerts:
        return f"■ 朝サマリー（{today_str} {weekday}）\n☀️ 異常なし"

    lines = [f"■ 朝サマリー（{today_str} {weekday}）"]

    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    info = [a for a in alerts if a["severity"] == "INFO"]

    total_count = len(alerts)
    lines.append(f"⚠️ {total_count}件の注意")
    lines.append("")

    for a in critical[:3]:
        sym_display = a["symbol"]
        lines.append(f"🔴 {sym_display}: {a['message']}")

    for a in info[:5]:
        sym_display = a["symbol"]
        lines.append(f"🟡 {sym_display}: {a['message']}")

    if len(alerts) > 8:
        lines.append(f"  ...他{len(alerts) - 8}件")

    # Suggest deepdive for most critical
    if critical:
        first = critical[0]
        if first["type"] in ("hard_stop", "exit_rule"):
            lines.append(f"\n→「{first['symbol']}を売るべきか」で詳細分析")
        elif first["type"] == "vix_high":
            lines.append(f"\n→「リスク判定して」で市況確認")
    elif info:
        first = info[0]
        if first["type"] == "earnings_soon":
            lines.append(f"\n→「{first['symbol']}の決算前チェック」で確認")

    return "\n".join(lines)
