#!/usr/bin/env python3
"""Market quantitative dashboard — VIX, Fear & Greed, Yield Curve (KIK-567).

Usage:
    python3 scripts/market_dashboard.py

Uses yfinance only. No Grok API required.
For qualitative analysis, use: /market-research market
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.yahoo_client.macro import get_macro_indicators
from src.core.market_dashboard import (
    compute_fear_greed,
    get_vix_history,
    get_yield_curve,
)


def _fmt_change(val, is_point: bool = False) -> str:
    if val is None:
        return "-"
    if is_point:
        return f"{val:+.2f}pt"
    return f"{val * 100:+.1f}%"


def _fmt_price(val) -> str:
    if val is None:
        return "-"
    if val >= 1000:
        return f"{val:,.0f}"
    if val >= 100:
        return f"{val:.1f}"
    return f"{val:.2f}"


def main():
    today = date.today().isoformat()
    print(f"## 市況ダッシュボード ({today})")
    print()

    # --- Macro indicators ---
    print("### 主要指標")
    print()
    print("| 指標 | 値 | 日次変動 | 週次変動 |")
    print("|:---|---:|---:|---:|")

    indicators = get_macro_indicators()
    for ind in indicators:
        name = ind["name"]
        price = _fmt_price(ind["price"])
        daily = _fmt_change(ind["daily_change"], ind.get("is_point_diff", False))
        weekly = _fmt_change(ind["weekly_change"], ind.get("is_point_diff", False))
        print(f"| {name} | {price} | {daily} | {weekly} |")
    print()

    # --- Fear & Greed ---
    print("### Fear & Greed スコア")
    print()
    fg = compute_fear_greed()
    fg_emoji = {
        "Extreme Fear": "😱",
        "Fear": "😰",
        "Neutral": "😐",
        "Greed": "😊",
        "Extreme Greed": "🤑",
    }
    emoji = fg_emoji.get(fg["label"], "")
    print(f"**{fg['score']:.0f} / 100** — {emoji} {fg['label']}")
    print()
    if fg["indicators"]:
        print("| 指標 | 値 | スコア | シグナル |")
        print("|:---|---:|---:|:---|")
        for ind in fg["indicators"]:
            print(f"| {ind['name']} | {ind['value']} | {ind['score']:.0f} | {ind['signal']} |")
        print()

    # --- VIX History ---
    print("### VIX推移（1ヶ月）")
    print()
    vix = get_vix_history()
    if vix["current"] is not None:
        print(f"現在: **{vix['current']}** — {vix['phase']}（トレンド: {vix['trend']}）")
        print()
        if vix["history"]:
            print("| 日付 | VIX |")
            print("|:---|---:|")
            for h in vix["history"]:
                print(f"| {h['date']} | {h['close']} |")
            print()
    else:
        print("VIXデータ取得不可")
        print()

    # --- Yield Curve ---
    print("### 金利・イールドカーブ")
    print()
    yc = get_yield_curve()
    if yc["yields"]:
        print("| テナー | 利回り |")
        print("|:---|---:|")
        for tenor in ["3M", "5Y", "10Y", "30Y"]:
            rate = yc["yields"].get(tenor, "-")
            print(f"| 米{tenor} | {rate}% |" if isinstance(rate, float) else f"| 米{tenor} | - |")
        print()
        if yc["spread_10y_3m"] is not None:
            print(f"10Y-3Mスプレッド: **{yc['spread_10y_3m']:+.3f}%** — {yc['curve_status']}")
        if yc["history_10y"]:
            print()
            print("米10年債推移:")
            print("| 日付 | 利回り |")
            print("|:---|---:|")
            for h in yc["history_10y"]:
                print(f"| {h['date']} | {h['rate']}% |")
        print()
    else:
        print("金利データ取得不可")
        print()


if __name__ == "__main__":
    main()
