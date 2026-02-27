"""Portfolio command: analyze -- Structural analysis (sector/region/currency HHI)."""

from portfolio_commands import (
    HAS_CONCENTRATION,
    HAS_PORTFOLIO_FORMATTER,
    HAS_PORTFOLIO_MANAGER,
    HAS_SHAREHOLDER_ANALYSIS,
    HAS_SHAREHOLDER_ANALYSIS_FMT,
    _fallback_load_csv,
    _infer_country,
    analyze_concentration,
    format_shareholder_return_analysis,
    format_structure_analysis,
    get_portfolio_shareholder_return,
    pm_get_structure_analysis,
    yahoo_client,
)


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
