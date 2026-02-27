"""Portfolio command: simulate -- Run compound interest simulation."""

import json
import sys
from typing import Optional

import portfolio_commands as _pc


def cmd_simulate(
    csv_path: str,
    years: int = 10,
    monthly_add: float = 0.0,
    target: Optional[float] = None,
    reinvest_dividends: bool = True,
) -> None:
    """Run compound interest simulation."""
    if not _pc.HAS_SIMULATOR:
        print("Error: simulator モジュールが見つかりません。")
        sys.exit(1)
    if not _pc.HAS_RETURN_ESTIMATE:
        print("Error: return_estimate モジュールが見つかりません。")
        sys.exit(1)

    print("シミュレーション実行中（forecast データ取得）...\n")

    # 1. forecast データ取得
    # Import at call time to respect mocks in tests
    from src.core.return_estimate import estimate_portfolio_return
    forecast_result = estimate_portfolio_return(csv_path, _pc.yahoo_client)
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
    result = _pc.simulate_portfolio(
        current_value=total_value_jpy,
        returns=portfolio_returns,
        dividend_yield=weighted_div_yield,
        years=years,
        monthly_add=monthly_add,
        reinvest_dividends=reinvest_dividends,
        target=target,
    )

    # 4. 出力
    if _pc.HAS_SIMULATION_FORMATTER:
        print(_pc.format_simulation(result))
    else:
        # Fallback: JSON 出力
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
