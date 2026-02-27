"""Portfolio command: adjust -- Generate portfolio adjustment plan from health check."""

import sys

from portfolio_commands import (
    HAS_ADJUST_FORMATTER,
    HAS_ADJUSTMENT_ADVISOR,
    HAS_CONCENTRATION,
    HAS_CORRELATION,
    HAS_HEALTH_CHECK,
    HAS_MARKET_REGIME,
    HAS_PORTFOLIO_MANAGER,
    analyze_concentration,
    compute_correlation_matrix,
    detect_regime,
    find_high_correlation_pairs,
    format_adjustment_plan,
    generate_adjustment_plan,
    get_default_index_symbol,
    hc_run_health_check,
    pm_get_snapshot,
    yahoo_client,
)


def cmd_adjust(csv_path: str, full: bool = False) -> None:
    """Generate portfolio adjustment plan from health check."""
    if not HAS_HEALTH_CHECK:
        print("Error: health_check モジュールが見つかりません。")
        sys.exit(1)
    if not HAS_MARKET_REGIME:
        print("Error: market_regime モジュールが見つかりません。")
        sys.exit(1)
    if not HAS_ADJUSTMENT_ADVISOR:
        print("Error: adjustment_advisor モジュールが見つかりません。")
        sys.exit(1)

    print("調整プラン生成中（ヘルスチェック + レジーム判定）...\n")

    # 1. Health check
    health_data = hc_run_health_check(csv_path, yahoo_client)
    positions = health_data.get("positions", [])
    if not positions:
        print("ポートフォリオにデータがありません。")
        return

    # 2. Market regime
    index_sym = get_default_index_symbol(positions)
    regime = detect_regime(yahoo_client, index_sym)

    # 3. Optional full analysis (API-heavy)
    concentration = None
    stress_result = None
    correlation_pairs = None
    var_result = None

    if full:
        print("フル分析モード（集中度・相関・VaR取得中）...\n")
        if HAS_CONCENTRATION:
            try:
                snapshot = pm_get_snapshot(csv_path, yahoo_client)
                concentration = analyze_concentration(snapshot)
            except Exception:
                pass

        if HAS_CORRELATION:
            try:
                symbols = [p["symbol"] for p in positions]
                corr_matrix = compute_correlation_matrix(symbols, yahoo_client)
                correlation_pairs = find_high_correlation_pairs(corr_matrix)
            except Exception:
                pass

    # 4. Generate plan
    plan = generate_adjustment_plan(
        health_data, regime,
        concentration=concentration,
        stress_result=stress_result,
        correlation_pairs=correlation_pairs,
        var_result=var_result,
    )

    # 5. Output
    if HAS_ADJUST_FORMATTER:
        print(format_adjustment_plan(plan))
    else:
        print(f"Regime: {regime.regime}")
        print(f"Actions: {len(plan.actions)}")
        for a in plan.actions:
            print(f"  [{a.urgency.value}] {a.type.value} {a.target}: {'; '.join(a.reasons)}")
        print(f"\n{plan.summary}")
