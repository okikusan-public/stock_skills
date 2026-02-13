#!/usr/bin/env python3
"""Entry point for the stock-portfolio skill.

Manages portfolio holdings stored in a CSV file.
Commands:
  snapshot  -- Generate a portfolio snapshot with current prices and P&L
  buy       -- Record a stock purchase
  sell      -- Record a stock sale (reduce shares)
  analyze   -- Structural analysis (sector/region/currency HHI)
  list      -- Display raw CSV contents
"""

import argparse
import csv
import json
import os
import sys
from datetime import date
from typing import Optional

# ---------------------------------------------------------------------------
# sys.path setup (same pattern as run_screen.py / run_stress_test.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
sys.path.insert(0, PROJECT_ROOT)

from src.data import yahoo_client

# Team 2 module: portfolio_manager (core logic for portfolio operations)
try:
    from src.core.portfolio_manager import (
        load_portfolio,
        save_portfolio,
        add_position,
        sell_position,
        get_snapshot as pm_get_snapshot,
        get_structure_analysis as pm_get_structure_analysis,
    )
    HAS_PORTFOLIO_MANAGER = True
except ImportError:
    HAS_PORTFOLIO_MANAGER = False

# Team 3 module: portfolio_formatter (output formatting)
try:
    from src.output.portfolio_formatter import (
        format_snapshot,
        format_position_list,
        format_structure_analysis,
        format_trade_result,
        format_health_check,
        format_return_estimate,
    )
    HAS_PORTFOLIO_FORMATTER = True
except ImportError:
    HAS_PORTFOLIO_FORMATTER = False

# KIK-359: Return estimation module
try:
    from src.core.return_estimate import estimate_portfolio_return
    HAS_RETURN_ESTIMATE = True
except ImportError:
    HAS_RETURN_ESTIMATE = False

# KIK-356: Health check module
try:
    from src.core.health_check import run_health_check as hc_run_health_check
    HAS_HEALTH_CHECK = True
except ImportError:
    HAS_HEALTH_CHECK = False

# Concentration analysis (already exists in the codebase)
try:
    from src.core.concentration import analyze_concentration
    HAS_CONCENTRATION = True
except ImportError:
    HAS_CONCENTRATION = False


# ---------------------------------------------------------------------------
# Default CSV path
# ---------------------------------------------------------------------------
DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__), "..", "data", "portfolio.csv"
)


# ---------------------------------------------------------------------------
# Country inference from ticker suffix (reused from stress-test)
# ---------------------------------------------------------------------------
_SUFFIX_TO_COUNTRY = {
    ".T": "Japan",
    ".SI": "Singapore",
    ".BK": "Thailand",
    ".KL": "Malaysia",
    ".JK": "Indonesia",
    ".PS": "Philippines",
    ".HK": "Hong Kong",
    ".KS": "South Korea",
    ".KQ": "South Korea",
    ".TW": "Taiwan",
    ".TWO": "Taiwan",
    ".SS": "China",
    ".SZ": "China",
    ".L": "United Kingdom",
    ".DE": "Germany",
    ".PA": "France",
    ".TO": "Canada",
    ".AX": "Australia",
    ".SA": "Brazil",
    ".NS": "India",
    ".BO": "India",
}


def _infer_country(symbol: str) -> str:
    """Infer country/region from ticker symbol suffix."""
    for suffix, country in _SUFFIX_TO_COUNTRY.items():
        if symbol.upper().endswith(suffix.upper()):
            return country
    if "." not in symbol:
        return "United States"
    return "Unknown"


# ---------------------------------------------------------------------------
# Fallback CSV helpers (used when Team 2 portfolio_manager is unavailable)
# ---------------------------------------------------------------------------

def _fallback_load_csv(csv_path: str) -> list[dict]:
    """Load portfolio CSV into a list of dicts."""
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            row["shares"] = int(row["shares"])
            row["cost_price"] = float(row["cost_price"])
            rows.append(row)
    return rows


def _fallback_save_csv(csv_path: str, holdings: list[dict]) -> None:
    """Save holdings list back to CSV."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    fieldnames = ["symbol", "shares", "cost_price", "cost_currency", "purchase_date", "memo"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for h in holdings:
            writer.writerow({k: h.get(k, "") for k in fieldnames})


# ---------------------------------------------------------------------------
# Command: list
# ---------------------------------------------------------------------------

def cmd_list(csv_path: str) -> None:
    """Display raw CSV contents."""
    if HAS_PORTFOLIO_MANAGER:
        holdings = load_portfolio(csv_path)
    else:
        holdings = _fallback_load_csv(csv_path)

    if not holdings:
        print("ポートフォリオにデータがありません。")
        return

    if HAS_PORTFOLIO_FORMATTER:
        print(format_position_list(holdings))
        return

    # Fallback: print as markdown table
    print("## ポートフォリオ一覧\n")
    print("| 銘柄 | 保有数 | 取得単価 | 通貨 | 購入日 | メモ |")
    print("|:-----|------:|--------:|:-----|:-------|:-----|")
    for h in holdings:
        print(
            f"| {h['symbol']} | {h['shares']} | {h['cost_price']:.2f} "
            f"| {h.get('cost_currency', '-')} | {h.get('purchase_date', '-')} "
            f"| {h.get('memo', '')} |"
        )
    print()


# ---------------------------------------------------------------------------
# Command: snapshot
# ---------------------------------------------------------------------------

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
        print("ポートフォリオにデータがありません。")
        return

    print("## ポートフォリオ スナップショット\n")
    print("| 銘柄 | 保有数 | 取得単価 | 現在価格 | 損益率 |")
    print("|:-----|------:|--------:|--------:|------:|")
    for h in holdings:
        info = yahoo_client.get_stock_info(h["symbol"])
        price = info.get("price") if info else None
        price_str = f"{price:.2f}" if price else "-"
        if price and h["cost_price"] > 0:
            pnl_pct = (price - h["cost_price"]) / h["cost_price"] * 100
            pnl_str = f"{pnl_pct:+.1f}%"
        else:
            pnl_str = "-"
        print(f"| {h['symbol']} | {h['shares']} | {h['cost_price']:.2f} | {price_str} | {pnl_str} |")
    print()


# ---------------------------------------------------------------------------
# Command: buy
# ---------------------------------------------------------------------------

def cmd_buy(
    csv_path: str,
    symbol: str,
    shares: int,
    price: float,
    currency: str = "JPY",
    purchase_date: Optional[str] = None,
    memo: str = "",
) -> None:
    """Add a purchase record to the portfolio CSV."""
    if purchase_date is None:
        purchase_date = date.today().isoformat()

    if HAS_PORTFOLIO_MANAGER:
        result = add_position(csv_path, symbol, shares, price, currency, purchase_date, memo)
        if HAS_PORTFOLIO_FORMATTER:
            print(format_trade_result({
                "symbol": symbol,
                "shares": shares,
                "price": price,
                "currency": currency,
                "total_shares": result.get("shares"),
                "avg_cost": result.get("cost_price"),
                "memo": memo,
            }, "buy"))
            return
    else:
        holdings = _fallback_load_csv(csv_path)
        # Check if symbol already exists -- merge shares
        existing = [h for h in holdings if h["symbol"] == symbol]
        if existing:
            old = existing[0]
            # Weighted average cost
            old_total = old["cost_price"] * old["shares"]
            new_total = price * shares
            combined_shares = old["shares"] + shares
            old["cost_price"] = (old_total + new_total) / combined_shares
            old["shares"] = combined_shares
            old["purchase_date"] = purchase_date
            if memo:
                old["memo"] = memo
        else:
            holdings.append({
                "symbol": symbol,
                "shares": shares,
                "cost_price": price,
                "cost_currency": currency,
                "purchase_date": purchase_date,
                "memo": memo,
            })
        _fallback_save_csv(csv_path, holdings)

    print(f"購入記録を追加しました: {symbol} {shares}株 @ {price} {currency}")
    print(f"  購入日: {purchase_date}")
    if memo:
        print(f"  メモ: {memo}")


# ---------------------------------------------------------------------------
# Command: sell
# ---------------------------------------------------------------------------

def cmd_sell(csv_path: str, symbol: str, shares: int) -> None:
    """Record a sale (reduce shares for a symbol)."""
    if HAS_PORTFOLIO_MANAGER:
        try:
            result = sell_position(csv_path, symbol, shares)
            remaining = result.get("shares", 0)
            if remaining == 0:
                print(f"売却完了: {symbol} {shares}株 (全株売却 -- ポートフォリオから削除)")
            else:
                print(f"売却記録を追加しました: {symbol} {shares}株 (残り {remaining}株)")
            return
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    holdings = _fallback_load_csv(csv_path)
    existing = [h for h in holdings if h["symbol"] == symbol]
    if not existing:
        print(f"Error: {symbol} はポートフォリオに存在しません。")
        sys.exit(1)

    h = existing[0]
    if shares > h["shares"]:
        print(f"Error: 売却数 ({shares}) が保有数 ({h['shares']}) を超えています。")
        sys.exit(1)

    h["shares"] -= shares
    if h["shares"] == 0:
        holdings = [x for x in holdings if x["symbol"] != symbol]
        print(f"売却完了: {symbol} {shares}株 (全株売却 -- ポートフォリオから削除)")
    else:
        print(f"売却記録を追加しました: {symbol} {shares}株 (残り {h['shares']}株)")

    _fallback_save_csv(csv_path, holdings)


# ---------------------------------------------------------------------------
# Command: analyze
# ---------------------------------------------------------------------------

def cmd_analyze(csv_path: str) -> None:
    """Structural analysis -- sector/region/currency HHI."""
    print("データ取得中...\n")

    if HAS_PORTFOLIO_MANAGER:
        # Use portfolio_manager's structure analysis (includes FX + concentration)
        conc = pm_get_structure_analysis(csv_path, yahoo_client)

        if not conc.get("sector_breakdown") and not conc.get("region_breakdown"):
            print("ポートフォリオにデータがありません。")
            return

        if HAS_PORTFOLIO_FORMATTER:
            print(format_structure_analysis(conc))
        else:
            # Fallback text output
            print("## ポートフォリオ構造分析\n")
            print(f"- セクターHHI: {conc.get('sector_hhi', 0):.4f}")
            print(f"- 地域HHI:   {conc.get('region_hhi', 0):.4f}")
            print(f"- 通貨HHI:   {conc.get('currency_hhi', 0):.4f}")
            print(f"- 最大集中軸:  {conc.get('max_hhi_axis', '-')}")
            print(f"- リスクレベル: {conc.get('risk_level', '-')}")
            print()
            for axis_name, key in [
                ("セクター", "sector_breakdown"),
                ("地域", "region_breakdown"),
                ("通貨", "currency_breakdown"),
            ]:
                breakdown = conc.get(key, {})
                if breakdown:
                    print(f"### {axis_name}別構成")
                    for label, w in sorted(breakdown.items(), key=lambda x: -x[1]):
                        print(f"  - {label}: {w * 100:.1f}%")
                    print()
        return

    # Fallback: no portfolio_manager available
    holdings = _fallback_load_csv(csv_path)
    if not holdings:
        print("ポートフォリオにデータがありません。")
        return

    # Build portfolio data with stock info
    portfolio_data = []
    for h in holdings:
        symbol = h["symbol"]
        info = yahoo_client.get_stock_info(symbol)
        if info is None:
            print(f"Warning: {symbol} のデータ取得に失敗しました。スキップします。")
            continue

        stock = dict(info)
        if not stock.get("country"):
            stock["country"] = _infer_country(symbol)
        price = stock.get("price", 0) or 0
        stock["market_value"] = price * h["shares"]
        portfolio_data.append(stock)

    if not portfolio_data:
        print("有効なデータを取得できた銘柄がありません。")
        return

    total_mv = sum(s.get("market_value", 0) for s in portfolio_data)
    if total_mv > 0:
        weights = [s.get("market_value", 0) / total_mv for s in portfolio_data]
    else:
        n = len(portfolio_data)
        weights = [1.0 / n] * n

    if HAS_CONCENTRATION:
        conc = analyze_concentration(portfolio_data, weights)
    else:
        conc = {"sector_hhi": 0.0, "region_hhi": 0.0, "currency_hhi": 0.0, "risk_level": "不明"}

    print("## ポートフォリオ構造分析\n")
    print(f"- セクターHHI: {conc.get('sector_hhi', 0):.4f}")
    print(f"- 地域HHI:   {conc.get('region_hhi', 0):.4f}")
    print(f"- 通貨HHI:   {conc.get('currency_hhi', 0):.4f}")
    print(f"- リスクレベル: {conc.get('risk_level', '-')}")
    print()


# ---------------------------------------------------------------------------
# Command: health (KIK-356)
# ---------------------------------------------------------------------------

def cmd_health(csv_path: str) -> None:
    """Run health check on portfolio holdings."""
    if not HAS_HEALTH_CHECK:
        print("Error: health_check モジュールが見つかりません。")
        sys.exit(1)

    print("ヘルスチェック実行中（価格・財務データ取得）...\n")

    health_data = hc_run_health_check(csv_path, yahoo_client)
    positions = health_data.get("positions", [])

    if not positions:
        print("ポートフォリオにデータがありません。")
        return

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


# ---------------------------------------------------------------------------
# Command: forecast (KIK-359)
# ---------------------------------------------------------------------------

def cmd_forecast(csv_path: str) -> None:
    """Generate 3-scenario return estimation for portfolio."""
    if not HAS_RETURN_ESTIMATE:
        print("Error: return_estimate モジュールが見つかりません。")
        sys.exit(1)

    print("推定利回り算出中（アナリスト目標・ニュース・センチメント取得）...\n")

    result = estimate_portfolio_return(csv_path, yahoo_client)

    positions = result.get("positions", [])
    if not positions:
        print("ポートフォリオにデータがありません。")
        return

    if HAS_PORTFOLIO_FORMATTER:
        print(format_return_estimate(result))
    else:
        # Fallback text output
        portfolio = result.get("portfolio", {})
        print("## 推定利回り（12ヶ月）\n")
        for label, key in [("楽観", "optimistic"), ("ベース", "base"), ("悲観", "pessimistic")]:
            ret = portfolio.get(key)
            if ret is not None:
                print(f"- {label}: {ret * 100:+.2f}%")
            else:
                print(f"- {label}: -")
        print()
        for pos in positions:
            base_r = pos.get("base")
            base_str = f"{base_r * 100:+.2f}%" if base_r is not None else "-"
            print(f"  {pos.get('symbol', '-')}: {base_str} ({pos.get('method', '')})")
        print()


# ---------------------------------------------------------------------------
# Main: argparse with subcommands
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ポートフォリオ管理 -- 保有銘柄の一覧表示・売買記録・構造分析"
    )
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV,
        help=f"ポートフォリオCSVファイルのパス (デフォルト: {DEFAULT_CSV})",
    )

    subparsers = parser.add_subparsers(dest="command", help="実行コマンド")

    # snapshot
    subparsers.add_parser("snapshot", help="PFスナップショット生成")

    # buy
    buy_parser = subparsers.add_parser("buy", help="購入記録追加")
    buy_parser.add_argument("--symbol", required=True, help="銘柄シンボル (例: 7203.T)")
    buy_parser.add_argument("--shares", required=True, type=int, help="株数")
    buy_parser.add_argument("--price", required=True, type=float, help="取得単価")
    buy_parser.add_argument("--currency", default="JPY", help="通貨コード (デフォルト: JPY)")
    buy_parser.add_argument("--date", default=None, help="購入日 (YYYY-MM-DD)")
    buy_parser.add_argument("--memo", default="", help="メモ")

    # sell
    sell_parser = subparsers.add_parser("sell", help="売却記録")
    sell_parser.add_argument("--symbol", required=True, help="銘柄シンボル (例: 7203.T)")
    sell_parser.add_argument("--shares", required=True, type=int, help="売却株数")

    # analyze
    subparsers.add_parser("analyze", help="構造分析 (セクター/地域/通貨HHI)")

    # list
    subparsers.add_parser("list", help="保有銘柄一覧表示")

    # health (KIK-356)
    subparsers.add_parser("health", help="保有銘柄ヘルスチェック")

    # forecast (KIK-359)
    subparsers.add_parser("forecast", help="推定利回り（3シナリオ）")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    csv_path = os.path.normpath(args.csv)

    if args.command == "snapshot":
        cmd_snapshot(csv_path)
    elif args.command == "buy":
        cmd_buy(
            csv_path=csv_path,
            symbol=args.symbol,
            shares=args.shares,
            price=args.price,
            currency=args.currency,
            purchase_date=args.date,
            memo=args.memo,
        )
    elif args.command == "sell":
        cmd_sell(csv_path=csv_path, symbol=args.symbol, shares=args.shares)
    elif args.command == "analyze":
        cmd_analyze(csv_path)
    elif args.command == "list":
        cmd_list(csv_path)
    elif args.command == "health":
        cmd_health(csv_path)
    elif args.command == "forecast":
        cmd_forecast(csv_path)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
