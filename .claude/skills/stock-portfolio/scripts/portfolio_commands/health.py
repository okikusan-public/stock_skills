"""Portfolio command: health -- Run health check on portfolio holdings."""

import sys

from portfolio_commands import (
    HAS_GRAPH_QUERY,
    HAS_HEALTH_CHECK,
    HAS_HISTORY,
    HAS_PORTFOLIO_FORMATTER,
    format_health_check,
    get_recent_market_context,
    hc_run_health_check,
    save_health,
    yahoo_client,
)


def cmd_health(csv_path: str) -> dict | None:
    """Run health check on portfolio holdings.

    Returns the health_data dict (for action item processing in main).
    """
    if not HAS_HEALTH_CHECK:
        print("Error: health_check モジュールが見つかりません。")
        sys.exit(1)

    print("ヘルスチェック実行中（価格・財務データ取得）...\n")

    health_data = hc_run_health_check(csv_path, yahoo_client)
    positions = health_data.get("positions", [])

    if not positions:
        print("ポートフォリオにデータがありません。")
        return health_data

    if HAS_PORTFOLIO_FORMATTER:
        print(format_health_check(health_data))
    else:
        # Fallback text output
        print("## 保有銘柄ヘルスチェック\n")
        print("| 銘柄 | 損益 | トレンド | 変化の質 | アラート |")
        print("|:-----|-----:|:-------|:--------|:------------|")
        for pos in positions:
            symbol = pos.get("symbol", "-")
            pnl_pct = pos.get("pnl_pct", 0)
            pnl_str = f"{pnl_pct * 100:+.1f}%" if pnl_pct else "-"
            trend = pos.get("trend_health", {}).get("trend", "不明")
            quality = pos.get("change_quality", {}).get("quality_label", "-")
            alert = pos.get("alert", {})
            alert_label = alert.get("label", "なし")
            emoji = alert.get("emoji", "")
            alert_str = f"{emoji} {alert_label}".strip() if emoji else "なし"
            print(f"| {symbol} | {pnl_str} | {trend} | {quality} | {alert_str} |")
        print()

    # KIK-406: Market context display
    if HAS_GRAPH_QUERY:
        try:
            ctx = get_recent_market_context()
            if ctx and ctx.get("indices"):
                print(f"\n### 市況コンテキスト ({ctx['date']})")
                for idx in ctx["indices"]:
                    name = idx.get("name", "?")
                    price = idx.get("price")
                    change = idx.get("change_pct")
                    if price is not None:
                        change_str = f" ({change:+.2f}%)" if change is not None else ""
                        print(f"  - {name}: {price:,.2f}{change_str}")
                print()
        except Exception:
            pass

    if HAS_HISTORY:
        try:
            save_health(health_data)
        except Exception as e:
            print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)

    return health_data
