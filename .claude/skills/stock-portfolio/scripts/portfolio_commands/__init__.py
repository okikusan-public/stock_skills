"""Portfolio subcommand modules package.

Shared helpers and re-exports for all portfolio subcommands.
"""

import csv
import os
import sys
from datetime import date
from typing import Optional

from src.data import yahoo_client
from src.core.ticker_utils import infer_country as _infer_country
from scripts.common import print_removal_contexts

# ---------------------------------------------------------------------------
# Optional module imports — registry-based bulk import (KIK-393)
# Each entry: (module_path, HAS_flag_suffix, [(original_name, alias), ...])
# Sets module-level globals: HAS_{flag_suffix} = True/False, and each name/alias.
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
    ("src.output.simulate_formatter", "SIMULATION_FORMATTER", [
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
        ("parse_add_arg", None), ("parse_remove_arg", None),
        ("run_what_if_simulation", None),
    ]),
    ("src.output.simulate_formatter", "WHAT_IF_FORMATTER", [
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
    ("src.core.portfolio.market_regime", "MARKET_REGIME", [
        ("detect_regime", None),
        ("get_default_index_symbol", None),
    ]),
    ("src.core.portfolio.adjustment_advisor", "ADJUSTMENT_ADVISOR", [
        ("generate_adjustment_plan", None),
    ]),
    ("src.output.adjust_formatter", "ADJUST_FORMATTER", [
        ("format_adjustment_plan", None),
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
# Fallback CSV helpers (used when portfolio_manager is unavailable)
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
# Helper: format confirmation prices (KIK-444)
# ---------------------------------------------------------------------------

def _fmt_conf_price(price: float, currency: str) -> str:
    """Format a price for confirmation messages (KIK-444)."""
    if currency == "JPY":
        return f"¥{price:,.0f}"
    return f"${price:,.2f}"
