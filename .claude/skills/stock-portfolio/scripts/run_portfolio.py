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
from src.core.ticker_utils import infer_country as _infer_country

# ---------------------------------------------------------------------------
# Optional module imports — registry-based bulk import (KIK-393)
# Each entry: (module_path, HAS_flag_suffix, [(original_name, alias), ...])
# Sets globals: HAS_{flag_suffix} = True/False, and each name/alias.
# ---------------------------------------------------------------------------
_IMPORT_REGISTRY = [
    ("src.core.portfolio.portfolio_manager", "PORTFOLIO_MANAGER", [
        ("load_portfolio", None), ("save_portfolio", None),
        ("add_position", None), ("sell_position", None),
        ("get_snapshot", "pm_get_snapshot"),
        ("get_structure_analysis", "pm_get_structure_analysis"),
    ]),
    ("src.output.portfolio_formatter", "PORTFOLIO_FORMATTER", [
        ("format_snapshot", None), ("format_position_list", None),
        ("format_structure_analysis", None), ("format_trade_result", None),
        ("format_health_check", None), ("format_return_estimate", None),
    ]),
    ("src.core.return_estimate", "RETURN_ESTIMATE", [
        ("estimate_portfolio_return", None),
    ]),
    ("src.core.health_check", "HEALTH_CHECK", [
        ("run_health_check", "hc_run_health_check"),
    ]),
    ("src.core.portfolio.concentration", "CONCENTRATION", [
        ("analyze_concentration", None),
    ]),
    ("src.core.portfolio.rebalancer", "REBALANCER", [
        ("generate_rebalance_proposal", None),
    ]),
    ("src.output.portfolio_formatter", "REBALANCE_FORMATTER", [
        ("format_rebalance_report", None),
    ]),
    ("src.core.portfolio.simulator", "SIMULATOR", [
        ("simulate_portfolio", None),
    ]),
    ("src.output.portfolio_formatter", "SIMULATION_FORMATTER", [
        ("format_simulation", None),
    ]),
    ("src.data.history_store", "HISTORY", [
        ("save_trade", None), ("save_health", None), ("save_market_context", None),
        ("save_forecast", None),
    ]),
    ("src.core.portfolio.backtest", "BACKTEST", [
        ("run_backtest", None),
    ]),
    ("src.core.risk.correlation", "CORRELATION", [
        ("compute_correlation_matrix", None), ("find_high_correlation_pairs", None),
    ]),
    ("src.core.screening.indicators", "SHAREHOLDER_RETURN", [
        ("calculate_shareholder_return", None),
    ]),
    ("src.core.portfolio.portfolio_simulation", "WHAT_IF", [
        ("parse_add_arg", None), ("run_what_if_simulation", None),
    ]),
    ("src.output.portfolio_formatter", "WHAT_IF_FORMATTER", [
        ("format_what_if", None),
    ]),
    ("src.core.portfolio.portfolio_manager", "SHAREHOLDER_ANALYSIS", [
        ("get_portfolio_shareholder_return", None),
    ]),
    ("src.output.portfolio_formatter", "SHAREHOLDER_ANALYSIS_FMT", [
        ("format_shareholder_return_analysis", None),
    ]),
    ("src.data.graph_query", "GRAPH_QUERY", [
        ("get_recent_market_context", None),
    ]),
    ("src.data.graph_store", "GRAPH_STORE", [
        ("sync_portfolio", None),
    ]),
    ("src.core.portfolio.portfolio_manager", "PERFORMANCE_REVIEW", [
        ("get_performance_review", None),
    ]),
    ("src.output.review_formatter", "REVIEW_FORMATTER", [
        ("format_performance_review", None),
    ]),
]

for _mod_path, _flag_suffix, _names in _IMPORT_REGISTRY:
    try:
        _mod = __import__(_mod_path, fromlist=[n[0] for n in _names])
        for _orig, _alias in _names:
            globals()[_alias or _orig] = getattr(_mod, _orig)
        globals()[f"HAS_{_flag_suffix}"] = True
    except ImportError:
        globals()[f"HAS_{_flag_suffix}"] = False


# ---------------------------------------------------------------------------
# Default CSV path
# ---------------------------------------------------------------------------
DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__), "..", "data", "portfolio.csv"
)


# ---------------------------------------------------------------------------
# Error helpers (KIK-443)
# ---------------------------------------------------------------------------

def _print_no_portfolio_message(csv_path: str) -> None:
    """Print human-readable message when portfolio has no data (KIK-443)."""
    if not os.path.exists(csv_path):
        print(
            "⚠️  ポートフォリオデータが見つかりません\n"
            "    原因: portfolio.csv がまだ作成されていません\n"
            "    対処: まず buy コマンドで銘柄を追加してください\n"
            "    例: run_portfolio.py buy --symbol 7203.T --shares 100 --price 2800"
        )
    else:
        print("ポートフォリオにデータがありません。")


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
        _print_no_portfolio_message(csv_path)
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


# ---------------------------------------------------------------------------
# Helper: save market context at trade time
# ---------------------------------------------------------------------------

def _save_trade_market_context() -> None:
    """Save market context snapshot alongside a trade record."""
    if not HAS_HISTORY:
        return
    try:
        macro = yahoo_client.get_macro_indicators()
        if macro:
            save_market_context({"indices": macro})
    except Exception as e:
        print(f"Warning: 市況スナップショット保存失敗: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Command: buy
# ---------------------------------------------------------------------------

def _fmt_conf_price(price: float, currency: str) -> str:
    """Format a price for confirmation messages (KIK-444)."""
    if currency == "JPY":
        return f"¥{price:,.0f}"
    return f"${price:,.2f}"


def cmd_buy(
    csv_path: str,
    symbol: str,
    shares: int,
    price: float,
    currency: str = "JPY",
    purchase_date: Optional[str] = None,
    memo: str = "",
    yes: bool = False,
) -> None:
    """Add a purchase record to the portfolio CSV."""
    if purchase_date is None:
        purchase_date = date.today().isoformat()

    # KIK-444: 確認ステップ（--yes なしの場合はプレビューのみ）
    if not yes:
        total = shares * price if price else None
        lines = ["## 購入確認", "",
                 "以下の内容で購入記録を追加します:", ""]
        lines.append(f"  銘柄:     {symbol}")
        lines.append(f"  株数:     {shares:,}株")
        if price:
            lines.append(f"  購入価格: {_fmt_conf_price(price, currency)}")
        lines.append(f"  購入日:   {purchase_date}")
        if total:
            lines.append(f"  取得額:   {_fmt_conf_price(total, currency)}")
        if memo:
            lines.append(f"  メモ:     {memo}")
        lines.append("")
        lines.append("記録しますか？ `--yes` をつけて再実行してください。")
        print("\n".join(lines))
        return

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
            if HAS_HISTORY:
                try:
                    save_trade(symbol, "buy", shares, price, currency, purchase_date, memo)
                except Exception as e:
                    print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
                _save_trade_market_context()
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

    if HAS_HISTORY:
        try:
            save_trade(symbol, "buy", shares, price, currency, purchase_date, memo)
        except Exception as e:
            print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
        _save_trade_market_context()

    # KIK-414: Sync portfolio to Neo4j
    if HAS_GRAPH_STORE:
        try:
            _holdings = load_portfolio(csv_path) if HAS_PORTFOLIO_MANAGER else _fallback_load_csv(csv_path)
            sync_portfolio(_holdings)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Command: sell
# ---------------------------------------------------------------------------

def cmd_sell(
    csv_path: str,
    symbol: str,
    shares: int,
    sell_price: float | None = None,
    sell_date: str | None = None,
    yes: bool = False,
) -> None:
    """Record a sale (reduce shares for a symbol). KIK-441: sell_price/sell_date added. KIK-444: yes flag added."""
    # KIK-444: 確認ステップ（--yes なしの場合はプレビューのみ）
    if not yes:
        lines = ["## 売却確認", "",
                 "以下の内容で売却記録を追加します:", ""]
        lines.append(f"  銘柄:     {symbol}")
        lines.append(f"  株数:     {shares:,}株")
        cost_price = None
        currency = "JPY"
        try:
            holdings = _fallback_load_csv(csv_path)
            matching = [h for h in holdings if h.get("symbol") == symbol]
            if matching:
                cost_price = matching[0].get("cost_price")
                currency = matching[0].get("cost_currency", "JPY")
        except Exception:
            pass
        if cost_price is not None:
            lines.append(f"  取得単価: {_fmt_conf_price(cost_price, currency)}")
        if sell_price:
            lines.append(f"  売却単価: {_fmt_conf_price(sell_price, currency)}")
            if cost_price:  # cost_price=0.0 は意図的にスキップ（ゼロ除算回避）
                pnl = (sell_price - cost_price) * shares
                pnl_rate = (sell_price - cost_price) / cost_price
                sign = "+" if pnl >= 0 else ""
                lines.append(
                    f"  推定実現損益: {sign}{_fmt_conf_price(pnl, currency)}"
                    f" ({sign}{pnl_rate * 100:.2f}%)"
                )
        lines.append(f"  売却日:   {sell_date or date.today().isoformat()}")
        lines.append("")
        lines.append("記録しますか？ `--yes` をつけて再実行してください。")
        print("\n".join(lines))
        return

    if HAS_PORTFOLIO_MANAGER:
        try:
            result = sell_position(csv_path, symbol, shares,
                                   sell_price=sell_price, sell_date=sell_date)
            remaining = result.get("shares", 0)
            cost_price = result.get("cost_price")
            realized_pnl = result.get("realized_pnl")
            pnl_rate = result.get("pnl_rate")
            hold_days = result.get("hold_days")
            currency = result.get("cost_currency", "JPY")
            trade_date = sell_date or date.today().isoformat()

            if HAS_PORTFOLIO_FORMATTER:
                print(format_trade_result({
                    "symbol": symbol,
                    "shares": shares,
                    "price": sell_price,
                    "currency": currency,
                    "total_shares": remaining,
                    "avg_cost": None,
                    "cost_price": cost_price,
                    "sell_price": sell_price,
                    "realized_pnl": realized_pnl,
                    "pnl_rate": pnl_rate,
                    "hold_days": hold_days,
                }, "sell"))
            else:
                if remaining == 0:
                    print(f"売却完了: {symbol} {shares}株 (全株売却 -- ポートフォリオから削除)")
                else:
                    print(f"売却記録を追加しました: {symbol} {shares}株 (残り {remaining}株)")

            if HAS_HISTORY:
                try:
                    save_trade(
                        symbol, "sell", shares,
                        price=cost_price or 0.0,
                        currency=currency,
                        date_str=trade_date,
                        sell_price=sell_price,
                        realized_pnl=realized_pnl,
                        pnl_rate=pnl_rate,
                        hold_days=hold_days,
                        cost_price=cost_price,
                    )
                except Exception as e:
                    print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
                _save_trade_market_context()
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

    trade_date = sell_date or date.today().isoformat()
    if HAS_HISTORY:
        try:
            save_trade(symbol, "sell", shares, 0.0, "", trade_date,
                       sell_price=sell_price)
        except Exception as e:
            print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
        _save_trade_market_context()

    # KIK-414: Sync portfolio to Neo4j
    if HAS_GRAPH_STORE:
        try:
            _holdings = load_portfolio(csv_path) if HAS_PORTFOLIO_MANAGER else _fallback_load_csv(csv_path)
            sync_portfolio(_holdings)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Command: review (KIK-441)
# ---------------------------------------------------------------------------


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

        # KIK-375/393: Shareholder return section (delegated to core)
        if HAS_SHAREHOLDER_ANALYSIS:
            sr_data = get_portfolio_shareholder_return(csv_path, yahoo_client)
            if sr_data.get("positions"):
                if HAS_SHAREHOLDER_ANALYSIS_FMT:
                    print()
                    print(format_shareholder_return_analysis(sr_data))
                else:
                    avg = sr_data.get("weighted_avg_rate")
                    if avg is not None:
                        print(f"\n加重平均 総株主還元率: {avg * 100:.2f}%")

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
        # Skip cash positions
        if symbol.upper().endswith(".CASH"):
            continue
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

    # KIK-428: Auto-save forecast results
    if HAS_HISTORY:
        try:
            total_jpy = result.get("total_value_jpy", 0)
            save_forecast(positions=positions, total_value_jpy=total_jpy)
        except Exception as e:
            print(f"Warning: フォーキャスト履歴保存失敗: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Command: rebalance (KIK-363)
# ---------------------------------------------------------------------------

def cmd_rebalance(
    csv_path: str,
    strategy: str = "balanced",
    reduce_sector: Optional[str] = None,
    reduce_currency: Optional[str] = None,
    max_single_ratio: Optional[float] = None,
    max_sector_hhi: Optional[float] = None,
    max_region_hhi: Optional[float] = None,
    additional_cash: float = 0.0,
    min_dividend_yield: Optional[float] = None,
) -> None:
    """Generate rebalancing proposal."""
    if not HAS_REBALANCER:
        print("Error: rebalancer モジュールが見つかりません。")
        sys.exit(1)
    if not HAS_RETURN_ESTIMATE:
        print("Error: return_estimate モジュールが見つかりません。")
        sys.exit(1)

    print("リバランス提案を生成中（forecast + health + 相関分析）...\n")

    # 1. Forecast data
    forecast_result = estimate_portfolio_return(csv_path, yahoo_client)
    if not forecast_result.get("positions"):
        print("ポートフォリオにデータがありません。")
        return

    # 2. Health check (optional)
    health_result = None
    if HAS_HEALTH_CHECK:
        try:
            health_result = hc_run_health_check(csv_path, yahoo_client)
        except Exception as e:
            print(f"Warning: ヘルスチェック取得エラー: {e}", file=sys.stderr)

    # 3. Concentration (optional, from forecast positions)
    concentration = None
    if HAS_CONCENTRATION and HAS_PORTFOLIO_MANAGER:
        try:
            concentration = pm_get_structure_analysis(csv_path, yahoo_client)
        except Exception as e:
            print(f"Warning: 構造分析取得エラー: {e}", file=sys.stderr)

    # 4. High-correlation pairs (optional)
    high_corr_pairs = None
    if HAS_CORRELATION:
        try:
            # Build portfolio_data for correlation from snapshot positions
            snapshot = pm_get_snapshot(csv_path, yahoo_client) if HAS_PORTFOLIO_MANAGER else None
            if snapshot and snapshot.get("positions"):
                corr_portfolio = []
                for pos in snapshot["positions"]:
                    symbol = pos.get("symbol", "")
                    if symbol.upper().endswith(".CASH"):
                        continue
                    hist = yahoo_client.get_price_history(symbol, period="1y")
                    if hist is not None and not hist.empty and "Close" in hist.columns:
                        corr_portfolio.append({
                            "symbol": symbol,
                            "price_history": hist["Close"].dropna().tolist(),
                        })
                if len(corr_portfolio) >= 2:
                    corr_result = compute_correlation_matrix(corr_portfolio)
                    high_corr_pairs = find_high_correlation_pairs(corr_result)
        except Exception as e:
            print(f"Warning: 相関分析エラー: {e}", file=sys.stderr)

    # 5. Enrich forecast positions with sector/country/currency from snapshot
    if HAS_PORTFOLIO_MANAGER:
        try:
            snapshot = pm_get_snapshot(csv_path, yahoo_client)
            snapshot_map = {
                p["symbol"]: p for p in snapshot.get("positions", [])
            }
            for pos in forecast_result.get("positions", []):
                snap_pos = snapshot_map.get(pos.get("symbol", ""))
                if snap_pos:
                    if not pos.get("sector"):
                        pos["sector"] = snap_pos.get("sector")
                    if not pos.get("country"):
                        pos["country"] = _infer_country(pos.get("symbol", ""))
                    if not pos.get("evaluation_jpy"):
                        pos["evaluation_jpy"] = snap_pos.get("evaluation_jpy", 0)
        except Exception:
            pass

    # 6. Generate proposal
    proposal = generate_rebalance_proposal(
        forecast_result=forecast_result,
        health_result=health_result,
        concentration=concentration,
        high_corr_pairs=high_corr_pairs,
        strategy=strategy,
        reduce_sector=reduce_sector,
        reduce_currency=reduce_currency,
        max_single_ratio=max_single_ratio,
        max_sector_hhi=max_sector_hhi,
        max_region_hhi=max_region_hhi,
        additional_cash=additional_cash,
        min_dividend_yield=min_dividend_yield,
    )

    # 7. Output
    if HAS_REBALANCE_FORMATTER:
        print(format_rebalance_report(proposal))
    else:
        print(json.dumps(proposal, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Command: simulate (KIK-366)
# ---------------------------------------------------------------------------

def cmd_simulate(
    csv_path: str,
    years: int = 10,
    monthly_add: float = 0.0,
    target: Optional[float] = None,
    reinvest_dividends: bool = True,
) -> None:
    """Run compound interest simulation."""
    if not HAS_SIMULATOR:
        print("Error: simulator モジュールが見つかりません。")
        sys.exit(1)
    if not HAS_RETURN_ESTIMATE:
        print("Error: return_estimate モジュールが見つかりません。")
        sys.exit(1)

    print("シミュレーション実行中（forecast データ取得）...\n")

    # 1. forecast データ取得
    forecast_result = estimate_portfolio_return(csv_path, yahoo_client)
    positions = forecast_result.get("positions", [])
    if not positions:
        print("ポートフォリオにデータがありません。")
        return

    portfolio_returns = forecast_result.get("portfolio", {})
    total_value_jpy = forecast_result.get("total_value_jpy", 0)

    # 2. 加重平均配当利回り算出
    weighted_div_yield = 0.0
    if total_value_jpy > 0:
        for pos in positions:
            dy = pos.get("dividend_yield") or 0.0
            value = pos.get("value_jpy") or 0
            weighted_div_yield += dy * (value / total_value_jpy)

    # 3. シミュレーション実行
    result = simulate_portfolio(
        current_value=total_value_jpy,
        returns=portfolio_returns,
        dividend_yield=weighted_div_yield,
        years=years,
        monthly_add=monthly_add,
        reinvest_dividends=reinvest_dividends,
        target=target,
    )

    # 4. 出力
    if HAS_SIMULATION_FORMATTER:
        print(format_simulation(result))
    else:
        # Fallback: JSON 出力
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Command: what-if (KIK-376)
# ---------------------------------------------------------------------------

def cmd_what_if(csv_path: str, add_str: str) -> None:
    """Run What-If simulation: add proposed stocks and compare metrics."""
    if not HAS_WHAT_IF:
        print("Error: portfolio_simulation モジュールが見つかりません。")
        sys.exit(1)

    # 1. Parse --add argument
    try:
        proposed = parse_add_arg(add_str)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("What-If シミュレーション実行中...\n")

    # 2. Run simulation
    result = run_what_if_simulation(csv_path, proposed, yahoo_client)

    # 3. Output
    if HAS_WHAT_IF_FORMATTER:
        print(format_what_if(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command: backtest (KIK-368)
# ---------------------------------------------------------------------------

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
    buy_parser.add_argument("-y", "--yes", action="store_true", default=False,
                            help="確認をスキップして直接記録する (KIK-444)")

    # sell
    sell_parser = subparsers.add_parser("sell", help="売却記録")
    sell_parser.add_argument("--symbol", required=True, help="銘柄シンボル (例: 7203.T)")
    sell_parser.add_argument("--shares", required=True, type=int, help="売却株数")
    sell_parser.add_argument("--price", type=float, default=None,
                             help="売却単価 (KIK-441, 例: 138.5)")
    sell_parser.add_argument("--date", default=None,
                             help="売却日 (KIK-441, YYYY-MM-DD, デフォルト: 今日)")
    sell_parser.add_argument("-y", "--yes", action="store_true", default=False,
                             help="確認をスキップして直接記録する (KIK-444)")

    # review (KIK-441)
    review_parser = subparsers.add_parser("review", help="売買パフォーマンスレビュー (KIK-441)")
    review_parser.add_argument("--year", type=int, default=None,
                               help="集計年 (例: 2026, デフォルト: 全期間)")
    review_parser.add_argument("--symbol", default=None,
                               help="銘柄フィルタ (例: NVDA)")

    # analyze
    subparsers.add_parser("analyze", help="構造分析 (セクター/地域/通貨HHI)")

    # list
    subparsers.add_parser("list", help="保有銘柄一覧表示")

    # health (KIK-356)
    subparsers.add_parser("health", help="保有銘柄ヘルスチェック")

    # forecast (KIK-359)
    subparsers.add_parser("forecast", help="推定利回り（3シナリオ）")

    # rebalance (KIK-363)
    rebalance_parser = subparsers.add_parser("rebalance", help="リバランス提案")
    rebalance_parser.add_argument(
        "--strategy",
        choices=["defensive", "balanced", "aggressive"],
        default="balanced",
        help="投資戦略 (デフォルト: balanced)",
    )
    rebalance_parser.add_argument(
        "--reduce-sector", default=None,
        help="削減対象セクター (例: Technology)",
    )
    rebalance_parser.add_argument(
        "--reduce-currency", default=None,
        help="削減対象通貨 (例: USD)",
    )
    rebalance_parser.add_argument(
        "--max-single-ratio", type=float, default=None,
        help="1銘柄の上限比率 (例: 0.15)",
    )
    rebalance_parser.add_argument(
        "--max-sector-hhi", type=float, default=None,
        help="セクターHHI上限 (例: 0.25)",
    )
    rebalance_parser.add_argument(
        "--max-region-hhi", type=float, default=None,
        help="地域HHI上限 (例: 0.30)",
    )
    rebalance_parser.add_argument(
        "--additional-cash", type=float, default=0.0,
        help="追加投入資金 (円, 例: 1000000)",
    )
    rebalance_parser.add_argument(
        "--min-dividend-yield", type=float, default=None,
        help="増加候補の最低配当利回り (例: 0.03)",
    )

    # simulate (KIK-366)
    simulate_parser = subparsers.add_parser("simulate", help="複利シミュレーション")
    simulate_parser.add_argument(
        "--years", type=int, default=10,
        help="シミュレーション年数 (デフォルト: 10)",
    )
    simulate_parser.add_argument(
        "--monthly-add", type=float, default=0.0,
        help="月額積立額 (円, デフォルト: 0)",
    )
    simulate_parser.add_argument(
        "--target", type=float, default=None,
        help="目標額 (円, 例: 15000000)",
    )
    simulate_parser.add_argument(
        "--reinvest-dividends", action="store_true", default=True,
        dest="reinvest_dividends",
        help="配当再投資する (デフォルト: ON)",
    )
    simulate_parser.add_argument(
        "--no-reinvest-dividends", action="store_false",
        dest="reinvest_dividends",
        help="配当再投資しない",
    )

    # what-if (KIK-376)
    whatif_parser = subparsers.add_parser("what-if", help="What-Ifシミュレーション")
    whatif_parser.add_argument(
        "--add", required=True,
        help="追加銘柄 (形式: SYMBOL:SHARES:PRICE,... 例: 7203.T:100:2850,AAPL:10:250)",
    )

    # backtest (KIK-368)
    backtest_parser = subparsers.add_parser("backtest", help="スクリーニング履歴のバックテスト")
    backtest_parser.add_argument(
        "--preset", default=None,
        help="対象プリセット (例: value, alpha)",
    )
    backtest_parser.add_argument(
        "--region", default=None,
        help="対象リージョン (例: jp, us)",
    )
    backtest_parser.add_argument(
        "--days", type=int, default=90,
        help="何日前までの履歴を対象にするか (デフォルト: 90)",
    )

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
            yes=args.yes,
        )
    elif args.command == "sell":
        cmd_sell(
            csv_path=csv_path,
            symbol=args.symbol,
            shares=args.shares,
            sell_price=getattr(args, "price", None),
            sell_date=getattr(args, "date", None),
            yes=args.yes,
        )
    elif args.command == "analyze":
        cmd_analyze(csv_path)
    elif args.command == "list":
        cmd_list(csv_path)
    elif args.command == "health":
        cmd_health(csv_path)
    elif args.command == "forecast":
        cmd_forecast(csv_path)
    elif args.command == "rebalance":
        cmd_rebalance(
            csv_path=csv_path,
            strategy=args.strategy,
            reduce_sector=args.reduce_sector,
            reduce_currency=args.reduce_currency,
            max_single_ratio=args.max_single_ratio,
            max_sector_hhi=args.max_sector_hhi,
            max_region_hhi=args.max_region_hhi,
            additional_cash=args.additional_cash,
            min_dividend_yield=args.min_dividend_yield,
        )
    elif args.command == "simulate":
        cmd_simulate(
            csv_path=csv_path,
            years=args.years,
            monthly_add=args.monthly_add,
            target=args.target,
            reinvest_dividends=args.reinvest_dividends,
        )
    elif args.command == "what-if":
        cmd_what_if(csv_path=csv_path, add_str=args.add)
    elif args.command == "backtest":
        cmd_backtest(
            preset=args.preset,
            region=args.region,
            days=args.days,
        )
    elif args.command == "review":
        cmd_review(
            year=getattr(args, "year", None),
            symbol=getattr(args, "symbol", None),
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
