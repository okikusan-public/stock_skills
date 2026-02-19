#!/usr/bin/env python3
"""Entry point for the stress-test skill.

Runs a portfolio stress test pipeline:
  1. Load portfolio data via yahoo_client
  2. Concentration analysis (HHI)
  3. Shock sensitivity scoring (Team 2)
  4. Scenario analysis (Team 3)
  5. Report output (Team 3)
"""

import argparse
import json
import sys
import os
import time
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from src.data import yahoo_client
from src.core.portfolio.concentration import analyze_concentration, compute_hhi
from src.core.ticker_utils import infer_country as _infer_country

# Team 2 module
try:
    from src.core.risk.shock_sensitivity import analyze_stock_sensitivity
except ImportError:
    analyze_stock_sensitivity = None

# Team 3 modules
try:
    from src.core.risk.scenario_analysis import resolve_scenario, analyze_portfolio_scenario
except ImportError:
    resolve_scenario = None
    analyze_portfolio_scenario = None

try:
    from src.output.stress_formatter import format_full_stress_report
except ImportError:
    format_full_stress_report = None

# KIK-352 modules
try:
    from src.core.risk.correlation import (
        compute_correlation_matrix,
        find_high_correlation_pairs,
        decompose_factors,
        compute_var,
        MACRO_FACTORS,
    )
except ImportError:
    compute_correlation_matrix = None
    find_high_correlation_pairs = None
    decompose_factors = None
    compute_var = None
    MACRO_FACTORS = []

try:
    from src.core.risk.recommender import generate_recommendations
except ImportError:
    generate_recommendations = None

# KIK-428: History auto-save
try:
    from src.data.history_store import save_stress_test as _save_stress_test
    HAS_HISTORY = True
except ImportError:
    HAS_HISTORY = False



# ---------------------------------------------------------------------------
# Portfolio data loading
# ---------------------------------------------------------------------------

def load_portfolio(
    symbols: list[str],
    weights: list[float],
) -> list[dict]:
    """Fetch fundamental + technical data for each portfolio symbol.

    Uses ``yahoo_client.get_stock_info()`` for fundamental data and
    ``yahoo_client.get_price_history()`` for technical data.  Infers
    ``country`` from the ticker suffix when the API does not supply it.

    Parameters
    ----------
    symbols : list[str]
        Ticker symbols.
    weights : list[float]
        Portfolio weights aligned with *symbols*.

    Returns
    -------
    list[dict]
        Per-stock data dicts enriched with ``weight``, ``country``, and
        price-history statistics.  Stocks that fail to load are excluded.
    """
    portfolio: list[dict] = []

    for i, symbol in enumerate(symbols):
        # Fundamental data
        info = yahoo_client.get_stock_info(symbol)
        if info is None:
            print(f"[stress-test] Warning: could not fetch data for {symbol}, skipping")
            continue

        stock = dict(info)  # shallow copy to avoid mutating cache
        stock["weight"] = weights[i]

        # Ensure country is present (infer from suffix if needed)
        if not stock.get("country"):
            stock["country"] = _infer_country(symbol)

        # Technical data -- price history
        try:
            hist = yahoo_client.get_price_history(symbol, period="1y")
            if hist is not None and not hist.empty and "Close" in hist.columns:
                closes = hist["Close"].dropna().tolist()
                stock["price_history"] = closes
                stock["price_history_length"] = len(closes)
                # Simple return statistics
                if len(closes) >= 2:
                    returns = [
                        (closes[j] - closes[j - 1]) / closes[j - 1]
                        for j in range(1, len(closes))
                        if closes[j - 1] != 0
                    ]
                    if returns:
                        stock["volatility_1y"] = (
                            (sum(r * r for r in returns) / len(returns)) ** 0.5
                        ) * (252 ** 0.5)  # annualised
                        stock["avg_daily_return"] = sum(returns) / len(returns)
            else:
                stock["price_history"] = []
                stock["price_history_length"] = 0
        except Exception as e:
            print(f"[stress-test] Warning: price history error for {symbol}: {e}")
            stock["price_history"] = []
            stock["price_history_length"] = 0

        portfolio.append(stock)

    return portfolio


# ---------------------------------------------------------------------------
# Fallback output (used when Team 3 formatter is not yet available)
# ---------------------------------------------------------------------------

def _fallback_print_portfolio_summary(portfolio: list[dict]) -> None:
    """Print Step 1 -- Portfolio summary."""
    print("## Step 1: ポートフォリオ概要\n")
    print("| 銘柄 | 名称 | セクター | 地域 | 通貨 | 比率 | 株価 | Beta |")
    print("|:-----|:-----|:---------|:-----|:-----|-----:|-----:|-----:|")
    for s in portfolio:
        symbol = s.get("symbol", "-")
        name = s.get("name") or "-"
        sector = s.get("sector") or "-"
        country = s.get("country") or "-"
        currency = s.get("currency") or "-"
        weight = f"{s.get('weight', 0) * 100:.1f}%"
        price = f"{s['price']:.0f}" if s.get("price") is not None else "-"
        beta = f"{s['beta']:.2f}" if s.get("beta") is not None else "-"
        print(f"| {symbol} | {name} | {sector} | {country} | {currency} | {weight} | {price} | {beta} |")
    print()


def _fallback_print_concentration(conc: dict) -> None:
    """Print Step 2 -- Concentration analysis."""
    print("## Step 2: 集中度分析\n")
    print(f"- セクターHHI: {conc['sector_hhi']:.4f}")
    print(f"- 地域HHI:   {conc['region_hhi']:.4f}")
    print(f"- 通貨HHI:   {conc['currency_hhi']:.4f}")
    print(f"- 最大集中軸:  {conc['max_hhi_axis']}（HHI = {conc['max_hhi']:.4f}）")
    print(f"- 集中度倍率:  {conc['concentration_multiplier']:.2f}x")
    print(f"- リスクレベル: {conc['risk_level']}")
    print()

    # Breakdowns
    for axis_name, key in [("セクター", "sector_breakdown"),
                            ("地域", "region_breakdown"),
                            ("通貨", "currency_breakdown")]:
        breakdown = conc.get(key, {})
        if breakdown:
            print(f"### {axis_name}別構成")
            for label, w in sorted(breakdown.items(), key=lambda x: -x[1]):
                print(f"  - {label}: {w * 100:.1f}%")
            print()


def _fallback_print_shock_sensitivity(portfolio: list[dict]) -> None:
    """Print Step 3 -- Shock sensitivity (basic fallback)."""
    print("## Step 3: ショック感応度（簡易版）\n")
    print("| 銘柄 | Beta | 年間Vol | D/E | 感応度 |")
    print("|:-----|-----:|-------:|----:|-------:|")
    for s in portfolio:
        symbol = s.get("symbol", "-")
        beta = s.get("beta")
        vol = s.get("volatility_1y")
        de = s.get("debt_to_equity")

        # Simple heuristic score when Team 2 module is unavailable
        score = 50.0  # base
        if beta is not None:
            score += (beta - 1.0) * 20  # higher beta -> higher sensitivity
        if vol is not None:
            score += (vol - 0.20) * 30  # higher vol -> higher sensitivity
        if de is not None and de > 100:
            score += 10  # high leverage
        score = max(0.0, min(100.0, score))

        beta_str = f"{beta:.2f}" if beta is not None else "-"
        vol_str = f"{vol * 100:.1f}%" if vol is not None else "-"
        de_str = f"{de:.0f}" if de is not None else "-"
        print(f"| {symbol} | {beta_str} | {vol_str} | {de_str} | {score:.1f} |")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ポートフォリオ ストレステスト"
    )
    parser.add_argument(
        "--portfolio",
        required=True,
        help="カンマ区切りの銘柄リスト (例: 7203.T,AAPL,D05.SI)",
    )
    parser.add_argument(
        "--weights",
        default=None,
        help="カンマ区切りの保有比率 (例: 0.5,0.3,0.2)。省略時は等分",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help="シナリオ名 (例: トリプル安, ドル高円安, 米国リセッション)",
    )
    parser.add_argument(
        "--base-shock",
        type=float,
        default=-0.20,
        help="ベースショック率 (デフォルト: -0.20 = -20%%)",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Parse symbols
    # ------------------------------------------------------------------
    symbols = [s.strip() for s in args.portfolio.split(",") if s.strip()]
    if not symbols:
        print("Error: --portfolio に有効な銘柄が指定されていません。")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Parse weights
    # ------------------------------------------------------------------
    if args.weights:
        try:
            weights = [float(w.strip().rstrip("%")) for w in args.weights.split(",")]
            # If values look like percentages (> 1), convert to decimals
            if any(w > 1.0 for w in weights):
                weights = [w / 100.0 for w in weights]
        except ValueError:
            print("Error: --weights のフォーマットが不正です。カンマ区切りの数値を指定してください。")
            sys.exit(1)

        if len(weights) != len(symbols):
            print(
                f"Error: --weights の数 ({len(weights)}) が --portfolio の銘柄数 ({len(symbols)}) と一致しません。"
            )
            sys.exit(1)

        # Normalize weights to sum to 1.0
        total_w = sum(weights)
        if total_w > 0:
            weights = [w / total_w for w in weights]
    else:
        # Equal-weight
        n = len(symbols)
        weights = [1.0 / n] * n

    # ------------------------------------------------------------------
    # Step 1: Load portfolio data
    # ------------------------------------------------------------------
    print("=" * 60)
    print("ポートフォリオ ストレステスト")
    print("=" * 60)
    print()
    print(f"対象銘柄: {', '.join(symbols)}")
    print(f"シナリオ: {args.scenario or '(自動判定)'}")
    print(f"ベースショック: {args.base_shock * 100:.0f}%")
    print()

    print("データ取得中...")
    portfolio = load_portfolio(symbols, weights)

    if not portfolio:
        print("Error: 有効なデータを取得できた銘柄がありません。")
        sys.exit(1)

    # Recalculate weights for successfully loaded stocks only
    loaded_symbols = [s["symbol"] for s in portfolio]
    if len(portfolio) < len(symbols):
        print(
            f"Warning: {len(symbols) - len(portfolio)} 銘柄のデータ取得に失敗しました。"
            f" 残り {len(portfolio)} 銘柄で分析を実行します。"
        )
        # Re-normalise weights
        total_w = sum(s["weight"] for s in portfolio)
        if total_w > 0:
            for s in portfolio:
                s["weight"] = s["weight"] / total_w

    final_weights = [s["weight"] for s in portfolio]
    print(f"取得完了: {len(portfolio)} 銘柄\n")

    # ------------------------------------------------------------------
    # Step 1 output: Portfolio summary
    # ------------------------------------------------------------------
    _fallback_print_portfolio_summary(portfolio)

    # ------------------------------------------------------------------
    # Step 2: Concentration analysis
    # ------------------------------------------------------------------
    conc = analyze_concentration(portfolio, final_weights)
    _fallback_print_concentration(conc)

    # ------------------------------------------------------------------
    # Step 3: Shock sensitivity (per-stock)
    # ------------------------------------------------------------------
    sensitivities = []
    if analyze_stock_sensitivity is not None:
        print("## Step 3: ショック感応度スコア\n")
        print("| 銘柄 | ファンダ | テクニカル | 象限 | 統合ショック |")
        print("|:-----|-------:|--------:|:-----|----------:|")
        for s in portfolio:
            hist = None
            try:
                hist = yahoo_client.get_price_history(s["symbol"], period="1y")
            except Exception:
                pass
            sens = analyze_stock_sensitivity(
                stock_info=s,
                hist=hist,
                concentration_multiplier=conc["concentration_multiplier"],
                base_shock=args.base_shock,
            )
            sensitivities.append(sens)
            f_score = sens["fundamental"]["score"]
            t_score = sens["technical"]["score"]
            quad = sens["integrated"]["quadrant"]
            adj_shock = sens["integrated"]["adjusted_shock"]
            print(
                f"| {s['symbol']} | {f_score:.2f} | {t_score:.2f} "
                f"| {quad['emoji']} {quad['quadrant']} | {adj_shock*100:.1f}% |"
            )
        print()
    else:
        _fallback_print_shock_sensitivity(portfolio)

    # ------------------------------------------------------------------
    # Step 4-7: Scenario analysis
    # ------------------------------------------------------------------
    scenario_result = None
    if analyze_portfolio_scenario is not None and resolve_scenario is not None:
        scenario_def = None
        if args.scenario:
            scenario_def = resolve_scenario(args.scenario)
        if scenario_def is None and args.scenario:
            print(f"Warning: シナリオ '{args.scenario}' が見つかりません。デフォルト(トリプル安)を使用します。")
            scenario_def = resolve_scenario("triple_decline")
        elif scenario_def is None:
            scenario_def = resolve_scenario("triple_decline")

        scenario_result = analyze_portfolio_scenario(
            portfolio=portfolio,
            sensitivities=sensitivities,
            weights=final_weights,
            scenario=scenario_def,
        )
    else:
        print("## Step 4-7: シナリオ分析\n")
        print(
            f"(scenario_analysis モジュールが未実装のため、"
            f"Claudeが以下の情報を元にシナリオ分析を実施してください)\n"
        )
        print(f"- シナリオ: {args.scenario or '(PF構成から自動判定)'}")
        print(f"- ベースショック: {args.base_shock * 100:.0f}%")
        print(f"- 集中度倍率: {conc['concentration_multiplier']:.2f}x")
        print(f"- 最大集中軸: {conc['max_hhi_axis']}")
        print()

    # ------------------------------------------------------------------
    # Flatten sensitivities for the formatter (KIK-353 bug fix)
    # analyze_stock_sensitivity() returns nested dicts but
    # format_sensitivity_report() expects flat keys.
    # ------------------------------------------------------------------
    flat_sensitivities = []
    for i, sens in enumerate(sensitivities):
        flat = dict(sens)
        flat["symbol"] = portfolio[i].get("symbol", "?") if i < len(portfolio) else "?"
        flat["name"] = portfolio[i].get("name", "") if i < len(portfolio) else ""
        # Flatten nested keys
        fund = sens.get("fundamental", {})
        tech = sens.get("technical", {})
        integ = sens.get("integrated", {})
        flat["fundamental_score"] = fund.get("score")
        flat["technical_score"] = tech.get("score")
        quad = integ.get("quadrant", {})
        flat["quadrant"] = f"{quad.get('emoji', '')} {quad.get('quadrant', '-')}".strip() if isinstance(quad, dict) else str(quad)
        flat["composite_shock"] = integ.get("adjusted_shock")
        flat_sensitivities.append(flat)

    # ------------------------------------------------------------------
    # KIK-352: Correlation analysis + VaR + Recommendations
    # ------------------------------------------------------------------
    corr_result = None
    high_pairs = None
    factor_results = None
    var_result = None
    recommendations = None

    if compute_correlation_matrix is not None and len(portfolio) >= 2:
        print("相関分析中...")
        corr_result = compute_correlation_matrix(portfolio)
        high_pairs = find_high_correlation_pairs(corr_result)

        # Factor decomposition -- fetch macro factor data
        if decompose_factors is not None and MACRO_FACTORS:
            factor_histories: dict[str, list[float]] = {}
            for factor in MACRO_FACTORS:
                fsym = factor["symbol"]
                try:
                    hist = yahoo_client.get_price_history(fsym, period="1y")
                    if hist is not None and not hist.empty and "Close" in hist.columns:
                        factor_histories[fsym] = hist["Close"].dropna().tolist()
                except Exception as e:
                    print(f"[stress-test] Warning: factor {fsym} fetch error: {e}")
            if factor_histories:
                factor_results = decompose_factors(portfolio, factor_histories)

    if compute_var is not None:
        print("VaR算出中...")
        # total_value is only meaningful when called from portfolio_bridge
        # (with actual holding amounts). --portfolio direct invocation has no
        # real portfolio value, so we pass None to suppress absolute amounts.
        var_total = None
        total_mv = sum(
            (s.get("market_value_jpy") or 0) * (s.get("weight") or 0)
            for s in portfolio
        )
        if total_mv > 0:
            var_total = total_mv
        var_result = compute_var(
            portfolio, final_weights, total_value=var_total
        )

    if generate_recommendations is not None:
        print("推奨アクション生成中...")
        recommendations = generate_recommendations(
            concentration=conc,
            correlation_pairs=high_pairs,
            var_result=var_result,
            scenario_result=scenario_result,
            sensitivities=sensitivities or None,
        )

    print()

    # ------------------------------------------------------------------
    # Step 8: Report output
    # ------------------------------------------------------------------
    if format_full_stress_report is not None and scenario_result is not None:
        portfolio_summary = {
            "stock_count": len(portfolio),
            "stocks": [
                {
                    "symbol": s.get("symbol", ""),
                    "name": s.get("name", ""),
                    "weight": s.get("weight", 0),
                    "price": s.get("price") or s.get("current_price"),
                    "sector": s.get("sector", ""),
                }
                for s in portfolio
            ],
        }
        report = format_full_stress_report(
            portfolio_summary=portfolio_summary,
            concentration=conc,
            sensitivities=flat_sensitivities,
            scenario_result=scenario_result,
            correlation=corr_result,
            high_correlation_pairs=high_pairs,
            factor_decomposition=factor_results,
            var_result=var_result,
            recommendations=recommendations,
        )
        print(report)
    elif scenario_result is not None:
        # scenario available but no formatter -- print raw
        print("## Step 4-7: シナリオ分析結果\n")
        print(f"シナリオ: {scenario_result.get('scenario_name', '-')}")
        print(f"PF影響率: {scenario_result.get('portfolio_impact', 0)*100:.1f}%")
        print(f"判定: {scenario_result.get('judgment', '-')}")
        print()
    else:
        print("## Step 8: 推奨アクション\n")
        print(
            "(stress_formatter モジュールが未実装のため、"
            "上記の分析結果を元にClaudeが推奨アクションを生成してください)\n"
        )

    # ------------------------------------------------------------------
    # Raw data dump for Claude's analysis
    # ------------------------------------------------------------------
    print("\n---\n## 分析用生データ (JSON)\n")
    raw_data = {
        "portfolio": [
            {
                "symbol": s.get("symbol"),
                "name": s.get("name"),
                "sector": s.get("sector"),
                "country": s.get("country"),
                "currency": s.get("currency"),
                "weight": s.get("weight"),
                "price": s.get("price"),
                "beta": s.get("beta"),
                "per": s.get("per"),
                "pbr": s.get("pbr"),
                "roe": s.get("roe"),
                "dividend_yield": s.get("dividend_yield"),
                "debt_to_equity": s.get("debt_to_equity"),
                "current_ratio": s.get("current_ratio"),
                "free_cashflow": s.get("free_cashflow"),
                "revenue_growth": s.get("revenue_growth"),
                "volatility_1y": s.get("volatility_1y"),
                "market_cap": s.get("market_cap"),
            }
            for s in portfolio
        ],
        "concentration": conc,
        "scenario": args.scenario,
        "base_shock": args.base_shock,
    }
    print(json.dumps(raw_data, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------
    # KIK-428: Auto-save stress test results
    # ------------------------------------------------------------------
    if HAS_HISTORY:
        try:
            loaded_symbols = [s.get("symbol", "") for s in portfolio if s.get("symbol")]
            scenario_name = (
                scenario_result.get("scenario_name", args.scenario or "auto")
                if scenario_result
                else (args.scenario or "auto")
            )
            pf_impact = (
                scenario_result.get("portfolio_impact", 0)
                if scenario_result
                else 0
            )
            per_stock = (
                scenario_result.get("per_stock_impacts", [])
                if scenario_result
                else []
            )
            _save_stress_test(
                scenario=scenario_name,
                symbols=loaded_symbols,
                portfolio_impact=pf_impact,
                per_stock_impacts=per_stock,
                var_result=var_result,
                high_correlation_pairs=(
                    [{"pair": list(p[0]), "corr": p[1]} for p in high_pairs]
                    if high_pairs else []
                ),
                concentration=conc,
                recommendations=recommendations,
            )
        except Exception:
            pass  # graceful degradation


if __name__ == "__main__":
    main()
