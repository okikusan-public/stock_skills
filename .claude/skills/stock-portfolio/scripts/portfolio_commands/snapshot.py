"""Portfolio command: snapshot -- Generate portfolio snapshot with current prices and P&L."""

from portfolio_commands import (
    HAS_PORTFOLIO_FORMATTER,
    HAS_PORTFOLIO_MANAGER,
    _fallback_load_csv,
    _print_no_portfolio_message,
    format_snapshot,
    pm_get_snapshot,
    yahoo_client,
)


def cmd_snapshot(csv_path: str) -> None:
    """Generate a portfolio snapshot with current prices and P&L."""
    print("データ取得中...\n")

    if HAS_PORTFOLIO_MANAGER:
        # Use portfolio_manager's full snapshot (includes FX conversion)
        snapshot = pm_get_snapshot(csv_path, yahoo_client)
        positions = snapshot.get("positions", [])

        if not positions:
            print("ポートフォリオにデータがありません。")
            return

        if HAS_PORTFOLIO_FORMATTER:
            # Build the dict format expected by format_snapshot
            fmt_data = {
                "timestamp": snapshot.get("as_of", ""),
                "positions": [
                    {
                        "symbol": p["symbol"],
                        "memo": p.get("memo") or p.get("name") or "",
                        "shares": p["shares"],
                        "cost_price": p["cost_price"],
                        "current_price": p.get("current_price"),
                        "market_value_jpy": p.get("evaluation_jpy"),
                        "pnl_jpy": p.get("pnl_jpy"),
                        "pnl_pct": p.get("pnl_pct"),
                        "currency": p.get("market_currency") or p.get("cost_currency", "JPY"),
                    }
                    for p in positions
                ],
                "total_market_value_jpy": snapshot.get("total_value_jpy"),
                "total_cost_jpy": snapshot.get("total_cost_jpy"),
                "total_pnl_jpy": snapshot.get("total_pnl_jpy"),
                "total_pnl_pct": snapshot.get("total_pnl_pct"),
                "fx_rates": {
                    f"{k}/JPY": v for k, v in snapshot.get("fx_rates", {}).items() if k != "JPY"
                },
            }
            print(format_snapshot(fmt_data))
        else:
            # Fallback: table output
            print("## ポートフォリオ スナップショット\n")
            print("| 銘柄 | 名称 | 保有数 | 取得単価 | 現在価格 | 評価額(円) | 損益(円) | 損益率 |")
            print("|:-----|:-----|------:|--------:|--------:|---------:|--------:|------:|")
            for p in positions:
                price_str = f"{p['current_price']:.2f}" if p.get("current_price") else "-"
                mv_str = f"{p.get('evaluation_jpy', 0):,.0f}"
                pnl_str = f"{p.get('pnl_jpy', 0):+,.0f}"
                pnl_pct_str = f"{p.get('pnl_pct', 0) * 100:+.1f}%"
                print(
                    f"| {p['symbol']} | {p.get('name') or p.get('memo', '')} | {p['shares']} "
                    f"| {p['cost_price']:.2f} | {price_str} | {mv_str} "
                    f"| {pnl_str} | {pnl_pct_str} |"
                )
            print()
            print(f"**総評価額: ¥{snapshot.get('total_value_jpy', 0):,.0f}** / "
                  f"総損益: ¥{snapshot.get('total_pnl_jpy', 0):+,.0f} "
                  f"({snapshot.get('total_pnl_pct', 0) * 100:+.1f}%)")
        return

    # Fallback: no portfolio_manager available
    holdings = _fallback_load_csv(csv_path)
    if not holdings:
        _print_no_portfolio_message(csv_path)
        return

    print("## ポートフォリオ スナップショット\n")
    print("| 銘柄 | 保有数 | 取得単価 | 現在価格 | 損益率 |")
    print("|:-----|------:|--------:|--------:|------:|")
    for h in holdings:
        symbol = h["symbol"]
        # Skip cash positions
        if symbol.upper().endswith(".CASH"):
            currency = symbol.upper().replace(".CASH", "")
            print(f"| {symbol} | {h['shares']} | {h['cost_price']:.2f} | {h['cost_price']:.2f} | - |")
            continue
        info = yahoo_client.get_stock_info(symbol)
        price = info.get("price") if info else None
        price_str = f"{price:.2f}" if price else "-"
        if price and h["cost_price"] > 0:
            pnl_pct = (price - h["cost_price"]) / h["cost_price"] * 100
            pnl_str = f"{pnl_pct:+.1f}%"
        else:
            pnl_str = "-"
        print(f"| {symbol} | {h['shares']} | {h['cost_price']:.2f} | {price_str} | {pnl_str} |")
    print()
