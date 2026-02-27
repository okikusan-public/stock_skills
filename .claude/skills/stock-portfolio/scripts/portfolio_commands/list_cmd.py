"""Portfolio command: list -- Display raw CSV contents."""

from portfolio_commands import (
    HAS_PORTFOLIO_FORMATTER,
    HAS_PORTFOLIO_MANAGER,
    _fallback_load_csv,
    _print_no_portfolio_message,
    format_position_list,
    load_portfolio,
)


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
