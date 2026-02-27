"""Portfolio command: rebalance -- Generate rebalancing proposal."""

import json
import sys
from typing import Optional

from portfolio_commands import (
    HAS_CONCENTRATION,
    HAS_CORRELATION,
    HAS_HEALTH_CHECK,
    HAS_PORTFOLIO_MANAGER,
    HAS_REBALANCE_FORMATTER,
    HAS_REBALANCER,
    HAS_RETURN_ESTIMATE,
    _infer_country,
    compute_correlation_matrix,
    estimate_portfolio_return,
    find_high_correlation_pairs,
    format_rebalance_report,
    generate_rebalance_proposal,
    hc_run_health_check,
    pm_get_snapshot,
    pm_get_structure_analysis,
    yahoo_client,
)


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
