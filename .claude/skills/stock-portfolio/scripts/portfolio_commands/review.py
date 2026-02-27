"""Portfolio command: review -- Display trade performance review."""

import sys

from portfolio_commands import (
    HAS_PERFORMANCE_REVIEW,
    HAS_REVIEW_FORMATTER,
    format_performance_review,
    get_performance_review,
)


def cmd_review(
    year: int | None = None,
    symbol: str | None = None,
) -> None:
    """売買パフォーマンスレビューを表示する (KIK-441)。"""
    if not HAS_PERFORMANCE_REVIEW:
        print("Error: get_performance_review が利用できません。")
        sys.exit(1)

    data = get_performance_review(year=year, symbol=symbol)

    if HAS_REVIEW_FORMATTER:
        print(format_performance_review(data, year=year, symbol=symbol))
    else:
        # フォールバック: 統計だけプリント
        stats = data.get("stats", {})
        trades = data.get("trades", [])
        print(f"## 売買パフォーマンスレビュー")
        print(f"- 取引件数: {stats.get('total', 0)}")
        if stats.get("win_rate") is not None:
            print(f"- 勝率: {stats['win_rate'] * 100:.1f}%")
        if stats.get("total_pnl") is not None:
            print(f"- 合計実現損益: {stats['total_pnl']:+,.0f}")
