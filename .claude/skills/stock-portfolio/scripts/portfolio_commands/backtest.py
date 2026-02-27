"""Portfolio command: backtest -- Run backtest on accumulated screening history."""

import sys
from typing import Optional

from portfolio_commands import (
    HAS_BACKTEST,
    run_backtest,
    yahoo_client,
)


def cmd_backtest(
    preset: Optional[str] = None,
    region: Optional[str] = None,
    days: int = 90,
) -> None:
    """Run backtest on accumulated screening history."""
    if not HAS_BACKTEST:
        print("Error: backtest モジュールが見つかりません。")
        sys.exit(1)

    print("バックテスト実行中（蓄積データ + 現在価格取得）...\n")

    result = run_backtest(
        yahoo_client_module=yahoo_client,
        category="screen",
        preset=preset,
        region=region,
        days_back=days,
    )

    stocks = result.get("stocks", [])
    period = result.get("period", {})

    if not stocks:
        print("対象期間のスクリーニング履歴がありません。")
        print(f"期間: {period.get('start', '?')} → {period.get('end', '?')}")
        if preset:
            print(f"プリセット: {preset}")
        if region:
            print(f"リージョン: {region}")
        return

    # Header
    print(f"## バックテスト結果（過去{days}日）")
    print(f"期間: {period.get('start', '?')} → {period.get('end', '?')}")
    if preset:
        print(f"プリセット: {preset}")
    if region:
        print(f"リージョン: {region}")
    print(f"対象スクリーニング回数: {result.get('total_screens', 0)}")
    print()

    # Stock table
    print("| 銘柄 | 名称 | スクリーニング日 | 当時スコア | 当時価格 | 現在価格 | リターン |")
    print("|:-----|:-----|:--------------|--------:|-------:|-------:|------:|")
    for s in stocks:
        ret_str = f"{s['return_pct'] * 100:+.2f}%"
        print(
            f"| {s['symbol']} | {s.get('name', '')} "
            f"| {s['screen_date']} | {s['score_at_screen']:.1f} "
            f"| {s['price_at_screen']:.2f} | {s['price_now']:.2f} | {ret_str} |"
        )
    print()

    # Summary
    print("### サマリー")
    print(f"- 対象銘柄数: {result.get('total_stocks', 0)}")
    print(f"- 平均リターン: {result.get('avg_return', 0) * 100:+.2f}%")
    print(f"- 中央値リターン: {result.get('median_return', 0) * 100:+.2f}%")
    print(f"- 勝率: {result.get('win_rate', 0) * 100:.1f}%")

    benchmark = result.get("benchmark", {})
    nikkei = benchmark.get("nikkei")
    sp500 = benchmark.get("sp500")
    if nikkei is not None:
        print(f"- ベンチマーク（日経225）: {nikkei * 100:+.2f}%")
    else:
        print("- ベンチマーク（日経225）: 取得不可")
    if sp500 is not None:
        print(f"- ベンチマーク（S&P500）: {sp500 * 100:+.2f}%")
    else:
        print("- ベンチマーク（S&P500）: 取得不可")

    alpha_n = result.get("alpha_nikkei")
    alpha_s = result.get("alpha_sp500")
    if alpha_n is not None:
        print(f"- α（対日経225）: {alpha_n * 100:+.2f}%")
    if alpha_s is not None:
        print(f"- α（対S&P500）: {alpha_s * 100:+.2f}%")
    print()
