"""Portfolio I/O: CSV load/save and position operations (KIK-578 split).

Extracted from portfolio_manager.py. Provides CSV-based portfolio
persistence with position tracking and P&L calculation.
"""

import csv
import os
from datetime import datetime
from typing import Optional

from src.data.ticker_utils import (
    SUFFIX_TO_CURRENCY as _SUFFIX_TO_CURRENCY,
    infer_currency as _infer_currency,
)

# CSV path (default)
DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
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
    "next_earnings",  # KIK-683: 直近決算日（YYYY-MM-DD）。ETFは空欄
]


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
                "next_earnings": row.get("next_earnings", "").strip(),
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
                    "next_earnings": pos.get("next_earnings", ""),
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
            "next_earnings": "",
        }
        portfolio.append(new_pos)
        result = dict(new_pos)

    save_portfolio(portfolio, csv_path)
    return result


def sell_position(
    csv_path: str,
    symbol: str,
    shares: int,
    sell_price: Optional[float] = None,
    sell_date: Optional[str] = None,
) -> dict:
    """売却。shares分を減算。0以下になったら行を削除。

    Parameters
    ----------
    sell_price : float, optional
        売却単価。指定時に realized_pnl / pnl_rate を計算。
    sell_date : str, optional
        売却日 (YYYY-MM-DD)。指定時に hold_days を計算。

    Returns
    -------
    dict
        更新後のポジション dict（削除された場合は shares=0 の dict）。
        KIK-441: sold_shares / sell_price / realized_pnl / pnl_rate / hold_days を追加。

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

    # KIK-441: P&L フィールドを追加
    result["sold_shares"] = shares
    result["sell_price"] = sell_price

    cost_price = target.get("cost_price")
    if sell_price is not None and cost_price is not None and cost_price != 0:
        result["realized_pnl"] = (sell_price - cost_price) * shares
        result["pnl_rate"] = (sell_price - cost_price) / cost_price
    else:
        result["realized_pnl"] = None
        result["pnl_rate"] = None

    purchase_date = target.get("purchase_date", "")
    if sell_date and purchase_date:
        try:
            from datetime import date as _date
            d1 = _date.fromisoformat(purchase_date)
            d2 = _date.fromisoformat(sell_date)
            result["hold_days"] = (d2 - d1).days
        except (ValueError, TypeError):
            result["hold_days"] = None
    else:
        result["hold_days"] = None

    return result


def update_next_earnings(
    csv_path: str,
    symbol: str,
    next_earnings: str,
) -> bool:
    """特定銘柄の next_earnings を更新する (KIK-683)。

    Parameters
    ----------
    csv_path : str
        ポートフォリオCSVパス
    symbol : str
        ティッカーシンボル
    next_earnings : str
        決算日 (YYYY-MM-DD)。空文字で消去

    Returns
    -------
    bool
        更新成功なら True、銘柄が見つからなければ False
    """
    portfolio = load_portfolio(csv_path)
    found = False
    for pos in portfolio:
        if pos["symbol"].upper() == symbol.upper():
            pos["next_earnings"] = next_earnings
            found = True
            break
    if found:
        save_portfolio(portfolio, csv_path)
    return found


def get_performance_review(
    year: Optional[int] = None,
    symbol: Optional[str] = None,
    base_dir: str = "data/history",
) -> dict:
    """売買パフォーマンスレビュー集計 (KIK-441)。

    data/history/trade/*.json から trade_type="sell" かつ
    realized_pnl があるレコードを集計して統計を返す。

    Parameters
    ----------
    year : int, optional
        指定年でフィルタ（例: 2026）。None なら全期間。
    symbol : str, optional
        指定シンボルでフィルタ。None なら全銘柄。
    base_dir : str
        history ルートディレクトリ。

    Returns
    -------
    dict
        {
            "trades": [...],  # フィルタ済みの sell レコード一覧
            "stats": {
                "total": int,
                "wins": int,
                "win_rate": float | None,
                "avg_return": float | None,   # pnl_rate の平均
                "avg_hold_days": float | None,
                "total_pnl": float | None,
            }
        }
    """
    from src.data.history import load_history

    all_trades = load_history("trade", base_dir=base_dir)

    # sell かつ realized_pnl があるものだけ
    sells = [
        t for t in all_trades
        if t.get("trade_type") == "sell" and t.get("realized_pnl") is not None
    ]

    # year フィルタ
    if year is not None:
        sells = [t for t in sells if str(t.get("date", "")).startswith(str(year))]

    # symbol フィルタ
    if symbol is not None:
        sym_upper = symbol.upper()
        sells = [t for t in sells if t.get("symbol", "").upper() == sym_upper]

    # 統計計算
    total = len(sells)
    if total == 0:
        return {
            "trades": [],
            "stats": {
                "total": 0,
                "wins": 0,
                "win_rate": None,
                "avg_return": None,
                "avg_hold_days": None,
                "total_pnl": None,
            },
        }

    wins = sum(1 for t in sells if (t.get("realized_pnl") or 0) > 0)
    win_rate = wins / total

    pnl_rates_stored = [t["pnl_rate"] for t in sells if t.get("pnl_rate") is not None]
    avg_return = sum(pnl_rates_stored) / len(pnl_rates_stored) if pnl_rates_stored else None

    hold_days_list = [t["hold_days"] for t in sells if t.get("hold_days") is not None]
    avg_hold_days = sum(hold_days_list) / len(hold_days_list) if hold_days_list else None

    total_pnl = sum(t.get("realized_pnl", 0) or 0 for t in sells)

    return {
        "trades": sells,
        "stats": {
            "total": total,
            "wins": wins,
            "win_rate": win_rate,
            "avg_return": avg_return,
            "avg_hold_days": avg_hold_days,
            "total_pnl": total_pnl,
        },
    }
