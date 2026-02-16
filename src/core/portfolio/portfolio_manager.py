"""Portfolio management core logic (KIK-342).

Provides CSV-based portfolio management with position tracking,
real-time pricing, P&L calculation, and structural analysis.
"""

import copy
import csv
import os
from datetime import datetime
from typing import Optional

from src.core.common import is_cash as _is_cash
from src.core.ticker_utils import (
    SUFFIX_TO_REGION as _SUFFIX_TO_COUNTRY,
    SUFFIX_TO_CURRENCY as _SUFFIX_TO_CURRENCY,
    cash_currency as _cash_currency,
    infer_country as _infer_country,
    infer_currency as _infer_currency,
)

# CSV path (default)
DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    ".claude",
    "skills",
    "stock-portfolio",
    "data",
    "portfolio.csv",
)

# CSV column definitions
CSV_COLUMNS = [
    "symbol",
    "shares",
    "cost_price",
    "cost_currency",
    "purchase_date",
    "memo",
]

# FX pairs to fetch for JPY conversion
_FX_PAIRS = [
    "USDJPY=X",
    "SGDJPY=X",
    "THBJPY=X",
    "MYRJPY=X",
    "IDRJPY=X",
    "PHPJPY=X",
    "HKDJPY=X",
    "KRWJPY=X",
    "TWDJPY=X",
    "CNYJPY=X",
    "GBPJPY=X",
    "EURJPY=X",
    "CADJPY=X",
    "AUDJPY=X",
    "BRLJPY=X",
    "INRJPY=X",
]


def _fx_symbol_for_currency(currency: str) -> Optional[str]:
    """Return the yfinance FX pair symbol for converting currency to JPY."""
    if currency == "JPY":
        return None  # No conversion needed
    return f"{currency}JPY=X"


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


def load_portfolio(csv_path: str = DEFAULT_CSV_PATH) -> list[dict]:
    """CSVからポートフォリオを読み込む。

    Returns
    -------
    list[dict]
        各行が dict: {symbol, shares, cost_price, cost_currency, purchase_date, memo}
        shares は int, cost_price は float に変換済み。
        ファイルが存在しない場合は空リストを返す。
    """
    csv_path = os.path.normpath(csv_path)
    if not os.path.exists(csv_path):
        return []

    portfolio: list[dict] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            position = {
                "symbol": row.get("symbol", "").strip(),
                "shares": int(float(row.get("shares", 0))),
                "cost_price": float(row.get("cost_price", 0.0)),
                "cost_currency": row.get("cost_currency", "JPY").strip(),
                "purchase_date": row.get("purchase_date", "").strip(),
                "memo": row.get("memo", "").strip(),
            }
            if position["symbol"] and position["shares"] > 0:
                portfolio.append(position)

    return portfolio


def save_portfolio(
    portfolio: list[dict], csv_path: str = DEFAULT_CSV_PATH
) -> None:
    """ポートフォリオをCSVに保存。

    ディレクトリが存在しない場合は自動作成する。
    """
    csv_path = os.path.normpath(csv_path)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for pos in portfolio:
            writer.writerow(
                {
                    "symbol": pos.get("symbol", ""),
                    "shares": pos.get("shares", 0),
                    "cost_price": pos.get("cost_price", 0.0),
                    "cost_currency": pos.get("cost_currency", "JPY"),
                    "purchase_date": pos.get("purchase_date", ""),
                    "memo": pos.get("memo", ""),
                }
            )


# ---------------------------------------------------------------------------
# Position operations
# ---------------------------------------------------------------------------


def add_position(
    csv_path: str,
    symbol: str,
    shares: int,
    cost_price: float,
    cost_currency: str = "JPY",
    purchase_date: Optional[str] = None,
    memo: str = "",
) -> dict:
    """新規ポジション追加 or 既存ポジションへの追加購入。

    既存銘柄がある場合:
    - 株数を加算
    - 平均取得単価を再計算: new_avg = (old_shares * old_price + new_shares * new_price) / total_shares
    - purchase_date は最新の日付に更新

    Returns
    -------
    dict
        更新後のポジション dict
    """
    if purchase_date is None:
        purchase_date = datetime.now().strftime("%Y-%m-%d")

    portfolio = load_portfolio(csv_path)

    # Search for existing position with same symbol
    existing = None
    for pos in portfolio:
        if pos["symbol"].upper() == symbol.upper():
            existing = pos
            break

    if existing is not None:
        # 既存ポジションへの追加購入 → 平均取得単価を再計算
        old_shares = existing["shares"]
        old_price = existing["cost_price"]
        total_shares = old_shares + shares
        if total_shares > 0:
            new_avg = (old_shares * old_price + shares * cost_price) / total_shares
        else:
            new_avg = cost_price

        existing["shares"] = total_shares
        existing["cost_price"] = round(new_avg, 4)
        existing["purchase_date"] = purchase_date
        if memo:
            existing["memo"] = memo
        result = dict(existing)
    else:
        # 新規ポジション
        new_pos = {
            "symbol": symbol.upper() if "." not in symbol else symbol,
            "shares": shares,
            "cost_price": cost_price,
            "cost_currency": cost_currency,
            "purchase_date": purchase_date,
            "memo": memo,
        }
        portfolio.append(new_pos)
        result = dict(new_pos)

    save_portfolio(portfolio, csv_path)
    return result


def sell_position(
    csv_path: str,
    symbol: str,
    shares: int,
) -> dict:
    """売却。shares分を減算。0以下になったら行を削除。

    Returns
    -------
    dict
        更新後のポジション dict（削除された場合は shares=0 の dict）

    Raises
    ------
    ValueError
        銘柄が見つからない場合、または保有数を超える売却の場合
    """
    portfolio = load_portfolio(csv_path)

    target_idx = None
    for i, pos in enumerate(portfolio):
        if pos["symbol"].upper() == symbol.upper():
            target_idx = i
            break

    if target_idx is None:
        raise ValueError(f"銘柄 {symbol} はポートフォリオに存在しません。")

    target = portfolio[target_idx]

    if shares > target["shares"]:
        raise ValueError(
            f"銘柄 {symbol} の保有数 ({target['shares']}) を超える "
            f"売却数 ({shares}) が指定されました。"
        )

    remaining = target["shares"] - shares

    if remaining <= 0:
        # ポジション全売却 → 行を削除
        result = dict(target)
        result["shares"] = 0
        portfolio.pop(target_idx)
    else:
        target["shares"] = remaining
        result = dict(target)

    save_portfolio(portfolio, csv_path)
    return result


# ---------------------------------------------------------------------------
# FX rate fetching
# ---------------------------------------------------------------------------


def get_fx_rates(client) -> dict:
    """主要為替レートを取得。

    yfinance で USDJPY=X 等を取得。JPYは1.0固定。
    client は yahoo_client モジュール（get_stock_info を持つ）。

    Returns
    -------
    dict
        {"JPY": 1.0, "USD": 150.5, "SGD": 112.3, ...}
        1通貨単位あたりの円。取得失敗した通貨は含まれない。
    """
    rates: dict[str, float] = {"JPY": 1.0}

    for pair in _FX_PAIRS:
        # pair format: "USDJPY=X" -> currency = "USD"
        currency = pair.replace("JPY=X", "")
        try:
            info = client.get_stock_info(pair)
            if info is not None and info.get("price") is not None:
                rates[currency] = float(info["price"])
            else:
                print(f"[portfolio_manager] Warning: FX rate for {pair} unavailable")
        except Exception as e:
            print(f"[portfolio_manager] Warning: FX rate fetch error for {pair}: {e}")

    return rates


def _get_fx_rate_for_currency(
    currency: str, fx_rates: dict[str, float]
) -> float:
    """指定通貨の対円レートを返す。見つからない場合は1.0（JPY扱い）。"""
    if currency in fx_rates:
        return fx_rates[currency]
    # Fallback: JPY扱い
    print(
        f"[portfolio_manager] Warning: FX rate for {currency} not found, "
        f"assuming 1.0 (JPY equivalent)"
    )
    return 1.0


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def get_snapshot(csv_path: str, client) -> dict:
    """スナップショット生成。

    各銘柄について:
    - yahoo_client.get_stock_info() で現在価格・セクター等を取得
    - 損益計算: (current_price - cost_price) * shares
    - 損益率: (current_price - cost_price) / cost_price
    - 評価額: current_price * shares

    為替レート取得:
    - USDJPY=X, SGDJPY=X 等をyfinanceで取得
    - 全銘柄を円換算

    Parameters
    ----------
    csv_path : str
        ポートフォリオCSVのパス
    client
        yahoo_client モジュール（get_stock_info を持つ）

    Returns
    -------
    dict
        {
            "positions": list[dict],
            "total_value_jpy": float,
            "total_cost_jpy": float,
            "total_pnl_jpy": float,
            "total_pnl_pct": float,
            "fx_rates": dict,
            "as_of": str,
        }
    """
    portfolio = load_portfolio(csv_path)

    if not portfolio:
        return {
            "positions": [],
            "total_value_jpy": 0.0,
            "total_cost_jpy": 0.0,
            "total_pnl_jpy": 0.0,
            "total_pnl_pct": 0.0,
            "fx_rates": {"JPY": 1.0},
            "as_of": datetime.now().isoformat(),
        }

    # Collect unique currencies for FX rate fetching
    currencies_needed: set[str] = set()
    for pos in portfolio:
        currencies_needed.add(pos.get("cost_currency", "JPY"))
        # Also need the market currency (inferred from symbol)
        currencies_needed.add(_infer_currency(pos["symbol"]))

    # Fetch FX rates (only if non-JPY currencies exist)
    if currencies_needed - {"JPY"}:
        fx_rates = get_fx_rates(client)
    else:
        fx_rates = {"JPY": 1.0}

    # Fetch current prices and build position details
    positions: list[dict] = []
    total_value_jpy = 0.0
    total_cost_jpy = 0.0

    for pos in portfolio:
        symbol = pos["symbol"]
        shares = pos["shares"]
        cost_price = pos["cost_price"]
        cost_currency = pos.get("cost_currency", "JPY")

        # Cash positions: skip API call, use cost_price as current price
        if _is_cash(symbol):
            cash_currency = _cash_currency(symbol)
            fx_rate = _get_fx_rate_for_currency(cash_currency, fx_rates)
            value_jpy = cost_price * shares * fx_rate
            cost_jpy = value_jpy  # cash has no P&L
            total_value_jpy += value_jpy
            total_cost_jpy += cost_jpy
            positions.append({
                "symbol": symbol,
                "name": f"現金 ({cash_currency})",
                "sector": "Cash",
                "shares": shares,
                "cost_price": cost_price,
                "cost_currency": cost_currency,
                "current_price": cost_price,
                "market_currency": cash_currency,
                "evaluation": cost_price * shares,
                "evaluation_jpy": round(value_jpy, 0),
                "cost_jpy": round(cost_jpy, 0),
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "pnl_jpy": 0.0,
                "purchase_date": pos.get("purchase_date", ""),
                "memo": pos.get("memo", ""),
            })
            continue

        # Get current market data
        info = client.get_stock_info(symbol)
        current_price = None
        name = None
        sector = None
        market_currency = _infer_currency(symbol)

        if info is not None:
            current_price = info.get("price")
            name = info.get("name")
            sector = info.get("sector")
            # Use the currency from yfinance if available
            if info.get("currency"):
                market_currency = info["currency"]

        # P&L calculation (in market currency)
        if current_price is not None:
            pnl = (current_price - cost_price) * shares
            pnl_pct = (current_price - cost_price) / cost_price if cost_price != 0 else 0.0
            evaluation = current_price * shares
        else:
            pnl = 0.0
            pnl_pct = 0.0
            evaluation = 0.0

        # JPY conversion
        fx_rate = _get_fx_rate_for_currency(market_currency, fx_rates)
        evaluation_jpy = evaluation * fx_rate
        cost_jpy = cost_price * shares * _get_fx_rate_for_currency(
            cost_currency, fx_rates
        )
        pnl_jpy = evaluation_jpy - cost_jpy

        total_value_jpy += evaluation_jpy
        total_cost_jpy += cost_jpy

        position_detail = {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "shares": shares,
            "cost_price": cost_price,
            "cost_currency": cost_currency,
            "current_price": current_price,
            "market_currency": market_currency,
            "evaluation": evaluation,
            "evaluation_jpy": round(evaluation_jpy, 0),
            "cost_jpy": round(cost_jpy, 0),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 4),
            "pnl_jpy": round(pnl_jpy, 0),
            "purchase_date": pos.get("purchase_date", ""),
            "memo": pos.get("memo", ""),
        }
        positions.append(position_detail)

    total_pnl_jpy = total_value_jpy - total_cost_jpy
    total_pnl_pct = (
        total_pnl_jpy / total_cost_jpy if total_cost_jpy != 0 else 0.0
    )

    return {
        "positions": positions,
        "total_value_jpy": round(total_value_jpy, 0),
        "total_cost_jpy": round(total_cost_jpy, 0),
        "total_pnl_jpy": round(total_pnl_jpy, 0),
        "total_pnl_pct": round(total_pnl_pct, 4),
        "fx_rates": fx_rates,
        "as_of": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Structure analysis
# ---------------------------------------------------------------------------


def get_structure_analysis(csv_path: str, client) -> dict:
    """構造分析。PFの偏りを自動集計。

    各銘柄のセクター・地域・通貨をyfinanceから取得し、
    evaluation_jpy ベースの比率でHHIを算出。

    concentration.py の analyze_concentration() を活用。

    Parameters
    ----------
    csv_path : str
        ポートフォリオCSVのパス
    client
        yahoo_client モジュール（get_stock_info を持つ）

    Returns
    -------
    dict
        {
            "region_breakdown": dict,
            "sector_breakdown": dict,
            "currency_breakdown": dict,
            "region_hhi": float,
            "sector_hhi": float,
            "currency_hhi": float,
            "concentration_multiplier": float,
            "risk_level": str,
        }
    """
    from src.core.portfolio.concentration import analyze_concentration

    # Get snapshot first (this also fetches current prices and FX rates)
    snapshot = get_snapshot(csv_path, client)
    positions = snapshot["positions"]

    if not positions:
        return {
            "region_breakdown": {},
            "sector_breakdown": {},
            "currency_breakdown": {},
            "region_hhi": 0.0,
            "sector_hhi": 0.0,
            "currency_hhi": 0.0,
            "concentration_multiplier": 1.0,
            "risk_level": "分散",
        }

    # Calculate weights based on evaluation_jpy
    total_value = snapshot["total_value_jpy"]
    if total_value <= 0:
        # Fallback: equal weights
        n = len(positions)
        weights = [1.0 / n] * n
    else:
        weights = [
            pos["evaluation_jpy"] / total_value for pos in positions
        ]

    # Build portfolio_data for analyze_concentration
    portfolio_data: list[dict] = []
    for pos in positions:
        stock_data = {
            "symbol": pos["symbol"],
            "sector": pos.get("sector") or "Unknown",
            "country": _infer_country(pos["symbol"]),
            "currency": pos.get("market_currency") or _infer_currency(pos["symbol"]),
        }
        portfolio_data.append(stock_data)

    # Run concentration analysis
    conc = analyze_concentration(portfolio_data, weights)

    return {
        "region_breakdown": conc.get("region_breakdown", {}),
        "sector_breakdown": conc.get("sector_breakdown", {}),
        "currency_breakdown": conc.get("currency_breakdown", {}),
        "region_hhi": conc.get("region_hhi", 0.0),
        "sector_hhi": conc.get("sector_hhi", 0.0),
        "currency_hhi": conc.get("currency_hhi", 0.0),
        "concentration_multiplier": conc.get("concentration_multiplier", 1.0),
        "risk_level": conc.get("risk_level", "分散"),
    }


# ---------------------------------------------------------------------------
# Merge positions (KIK-376: What-If simulation)
# ---------------------------------------------------------------------------


def merge_positions(
    current: list[dict], proposed: list[dict]
) -> list[dict]:
    """現在PFに提案銘柄をマージ（加重平均コスト計算）。

    入力リストは変更しない（deep copy して操作）。

    Parameters
    ----------
    current : list[dict]
        現在のポートフォリオ（load_portfolio の戻り値）。
    proposed : list[dict]
        追加提案銘柄。各 dict は symbol, shares, cost_price,
        cost_currency を持つ。

    Returns
    -------
    list[dict]
        マージ後のポートフォリオ。
    """
    merged = copy.deepcopy(current)
    symbol_map: dict[str, int] = {
        p["symbol"].upper(): i for i, p in enumerate(merged)
    }

    for prop in proposed:
        key = prop["symbol"].upper()
        if key in symbol_map:
            old = merged[symbol_map[key]]
            total = old["shares"] + prop["shares"]
            if total > 0:
                old["cost_price"] = (
                    old["shares"] * old["cost_price"]
                    + prop["shares"] * prop["cost_price"]
                ) / total
            old["shares"] = total
        else:
            merged.append({
                "symbol": prop["symbol"],
                "shares": prop["shares"],
                "cost_price": prop["cost_price"],
                "cost_currency": prop.get("cost_currency", "JPY"),
                "purchase_date": "",
                "memo": "(what-if)",
            })
            symbol_map[key] = len(merged) - 1

    return merged
