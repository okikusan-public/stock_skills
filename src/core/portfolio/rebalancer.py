"""Portfolio rebalancer engine (KIK-363).

Generates risk-constrained rebalancing proposals that maximize
expected return while staying within HHI, single-stock ratio,
and correlation constraints.

Uses existing modules:
  - return_estimate: per-stock expected returns (base/optimistic/pessimistic)
  - health_check: alert levels (exit -> immediate sell)
  - concentration: HHI analysis (sector/region/currency)
  - correlation: high-correlation pairs
"""

from typing import Optional

from src.core.common import is_cash as _is_cash
from src.core.portfolio.concentration import compute_hhi

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

SELL_RETURN_THRESHOLD = -0.10  # Sell if base expected return below this
SECTOR_CURRENCY_REDUCE_RATIO = 0.30  # Reduce 30% of sector/currency holdings
MAX_ALLOC_PER_POSITION = 0.40  # Max 40% of remaining cash per position
MIN_ALLOC_JPY = 10000  # Minimum allocation in JPY


def _pos_value_jpy(pos: dict) -> float:
    """Extract JPY value from a position dict, handling key aliases."""
    return pos.get("value_jpy") or pos.get("evaluation_jpy") or 0


def _pos_currency(pos: dict) -> str:
    """Extract currency from a position dict, handling key aliases."""
    return pos.get("currency") or pos.get("market_currency") or "Unknown"


# ---------------------------------------------------------------------------
# Default constraints
# ---------------------------------------------------------------------------

_DEFAULT_CONSTRAINTS = {
    "max_single_ratio": 0.15,
    "max_sector_hhi": 0.25,
    "max_region_hhi": 0.30,
    "max_corr_pair_ratio": 0.30,
    "corr_threshold": 0.7,
}

# Strategy presets override constraints
_STRATEGY_PRESETS = {
    "defensive": {
        "max_single_ratio": 0.10,
        "max_sector_hhi": 0.20,
        "max_region_hhi": 0.25,
        "max_corr_pair_ratio": 0.25,
    },
    "balanced": {
        # Use defaults
    },
    "aggressive": {
        "max_single_ratio": 0.25,
        "max_sector_hhi": 0.35,
        "max_region_hhi": 0.40,
        "max_corr_pair_ratio": 0.40,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_constraints(
    strategy: str = "balanced",
    max_single_ratio: Optional[float] = None,
    max_sector_hhi: Optional[float] = None,
    max_region_hhi: Optional[float] = None,
    max_corr_pair_ratio: Optional[float] = None,
) -> dict:
    """Build constraints dict from strategy preset + explicit overrides."""
    constraints = dict(_DEFAULT_CONSTRAINTS)

    # Apply strategy preset
    preset = _STRATEGY_PRESETS.get(strategy, {})
    constraints.update(preset)

    # Explicit overrides take highest priority
    if max_single_ratio is not None:
        constraints["max_single_ratio"] = max_single_ratio
    if max_sector_hhi is not None:
        constraints["max_sector_hhi"] = max_sector_hhi
    if max_region_hhi is not None:
        constraints["max_region_hhi"] = max_region_hhi
    if max_corr_pair_ratio is not None:
        constraints["max_corr_pair_ratio"] = max_corr_pair_ratio

    return constraints


def _compute_current_metrics(positions: list[dict], total_value_jpy: float) -> dict:
    """Compute current portfolio metrics from position data."""
    if total_value_jpy <= 0:
        return {
            "base_return": 0.0,
            "weights": {},
            "sector_weights": {},
            "region_weights": {},
            "currency_weights": {},
        }

    weights = {}
    sector_weights: dict[str, float] = {}
    region_weights: dict[str, float] = {}
    currency_weights: dict[str, float] = {}
    weighted_return = 0.0

    for pos in positions:
        symbol = pos.get("symbol", "")
        value_jpy = _pos_value_jpy(pos)
        w = value_jpy / total_value_jpy if total_value_jpy > 0 else 0
        weights[symbol] = w

        sector = pos.get("sector") or "Unknown"
        sector_weights[sector] = sector_weights.get(sector, 0) + w

        country = pos.get("country") or "Unknown"
        region_weights[country] = region_weights.get(country, 0) + w

        currency = _pos_currency(pos)
        currency_weights[currency] = currency_weights.get(currency, 0) + w

        base_ret = pos.get("base")
        if base_ret is not None:
            weighted_return += base_ret * w

    return {
        "base_return": weighted_return,
        "weights": weights,
        "sector_weights": sector_weights,
        "region_weights": region_weights,
        "currency_weights": currency_weights,
    }



# ---------------------------------------------------------------------------
# Action generation
# ---------------------------------------------------------------------------

def _generate_sell_actions(
    positions: list[dict],
    health_results: Optional[dict],
) -> list[dict]:
    """Generate SELL actions for positions that should be fully exited.

    Rules:
      1. health alert = "exit" (撤退)
      2. base expected return is significantly negative (< -10%)
    """
    actions = []
    alert_map: dict[str, dict] = {}

    if health_results:
        for pos_health in health_results.get("positions", []):
            alert_map[pos_health["symbol"]] = pos_health.get("alert", {})

    for pos in positions:
        symbol = pos.get("symbol", "")
        if _is_cash(symbol):
            continue

        # Rule 1: health=exit
        alert = alert_map.get(symbol, {})
        if alert.get("level") == "exit":
            reasons = alert.get("reasons", [])
            reason_str = "、".join(reasons) if reasons else "撤退シグナル"
            actions.append({
                "action": "sell",
                "symbol": symbol,
                "name": pos.get("name", ""),
                "ratio": 1.0,
                "reason": f"ヘルスチェック撤退: {reason_str}",
                "value_jpy": _pos_value_jpy(pos),
                "priority": 1,
            })
            continue

        # Rule 2: base return below threshold
        base_ret = pos.get("base")
        if base_ret is not None and base_ret < SELL_RETURN_THRESHOLD:
            actions.append({
                "action": "sell",
                "symbol": symbol,
                "name": pos.get("name", ""),
                "ratio": 1.0,
                "reason": f"ベース期待値 {base_ret*100:.1f}% (大幅マイナス)",
                "value_jpy": _pos_value_jpy(pos),
                "priority": 2,
            })

    return actions


def _generate_reduce_actions(
    positions: list[dict],
    total_value_jpy: float,
    constraints: dict,
    high_corr_pairs: Optional[list[dict]] = None,
    reduce_sector: Optional[str] = None,
    reduce_currency: Optional[str] = None,
    sell_symbols: Optional[set] = None,
) -> list[dict]:
    """Generate REDUCE actions for overweight or concentrated positions.

    Rules:
      1. Single stock ratio exceeds max_single_ratio
      2. High-correlation pair combined ratio exceeds max_corr_pair_ratio
      3. User requested sector/currency reduction
    """
    actions = []
    if sell_symbols is None:
        sell_symbols = set()
    if total_value_jpy <= 0:
        return actions

    max_single = constraints["max_single_ratio"]
    max_corr = constraints["max_corr_pair_ratio"]

    # Build weight map
    weight_map = {}
    for pos in positions:
        symbol = pos.get("symbol", "")
        if symbol in sell_symbols or _is_cash(symbol):
            continue
        value_jpy = _pos_value_jpy(pos)
        weight_map[symbol] = value_jpy / total_value_jpy

    already_reduced = set()

    # Rule 1: single stock over limit
    for pos in positions:
        symbol = pos.get("symbol", "")
        if symbol in sell_symbols or _is_cash(symbol):
            continue
        w = weight_map.get(symbol, 0)
        if w > max_single:
            target_w = max_single
            reduce_ratio = 1 - (target_w / w) if w > 0 else 0
            value_jpy = _pos_value_jpy(pos)
            actions.append({
                "action": "reduce",
                "symbol": symbol,
                "name": pos.get("name", ""),
                "ratio": round(reduce_ratio, 2),
                "reason": f"比率 {w*100:.1f}% → {target_w*100:.1f}% (上限{max_single*100:.0f}%)",
                "value_jpy": round(value_jpy * reduce_ratio, 0),
                "priority": 3,
            })
            already_reduced.add(symbol)

    # Rule 2: high-correlation pair concentration
    if high_corr_pairs:
        for pair_info in high_corr_pairs:
            pair = pair_info.get("pair", [])
            if len(pair) != 2:
                continue
            sym_a, sym_b = pair[0], pair[1]
            if sym_a in sell_symbols or sym_b in sell_symbols:
                continue
            combined_w = weight_map.get(sym_a, 0) + weight_map.get(sym_b, 0)
            if combined_w > max_corr:
                # Reduce the one with lower expected return
                pos_a = next((p for p in positions if p.get("symbol") == sym_a), {})
                pos_b = next((p for p in positions if p.get("symbol") == sym_b), {})
                ret_a = pos_a.get("base") or 0
                ret_b = pos_b.get("base") or 0
                target_sym = sym_a if ret_a <= ret_b else sym_b
                target_pos = pos_a if target_sym == sym_a else pos_b
                if target_sym not in already_reduced:
                    excess = combined_w - max_corr
                    target_w = weight_map.get(target_sym, 0)
                    reduce_ratio = min(excess / target_w, 0.5) if target_w > 0 else 0
                    corr_val = pair_info.get("correlation", 0)
                    value_jpy = _pos_value_jpy(target_pos)
                    actions.append({
                        "action": "reduce",
                        "symbol": target_sym,
                        "name": target_pos.get("name", ""),
                        "ratio": round(reduce_ratio, 2),
                        "reason": f"相関集中 ({sym_a}/{sym_b} r={corr_val:.2f}, 合計{combined_w*100:.0f}%>{max_corr*100:.0f}%)",
                        "value_jpy": round(value_jpy * reduce_ratio, 0),
                        "priority": 4,
                    })
                    already_reduced.add(target_sym)

    # Rule 3: user-requested sector reduction
    if reduce_sector:
        for pos in positions:
            symbol = pos.get("symbol", "")
            if symbol in sell_symbols or symbol in already_reduced or _is_cash(symbol):
                continue
            sector = pos.get("sector") or ""
            if sector.lower() == reduce_sector.lower():
                w = weight_map.get(symbol, 0)
                reduce_ratio = SECTOR_CURRENCY_REDUCE_RATIO
                value_jpy = _pos_value_jpy(pos)
                actions.append({
                    "action": "reduce",
                    "symbol": symbol,
                    "name": pos.get("name", ""),
                    "ratio": reduce_ratio,
                    "reason": f"セクター削減指示 ({reduce_sector})",
                    "value_jpy": round(value_jpy * reduce_ratio, 0),
                    "priority": 5,
                })
                already_reduced.add(symbol)

    # Rule 4: user-requested currency reduction
    if reduce_currency:
        for pos in positions:
            symbol = pos.get("symbol", "")
            if symbol in sell_symbols or symbol in already_reduced or _is_cash(symbol):
                continue
            currency = _pos_currency(pos)
            if currency.upper() == reduce_currency.upper():
                w = weight_map.get(symbol, 0)
                reduce_ratio = SECTOR_CURRENCY_REDUCE_RATIO
                value_jpy = _pos_value_jpy(pos)
                actions.append({
                    "action": "reduce",
                    "symbol": symbol,
                    "name": pos.get("name", ""),
                    "ratio": reduce_ratio,
                    "reason": f"通貨削減指示 ({reduce_currency})",
                    "value_jpy": round(value_jpy * reduce_ratio, 0),
                    "priority": 5,
                })
                already_reduced.add(symbol)

    return actions


def _generate_increase_actions(
    positions: list[dict],
    total_value_jpy: float,
    freed_cash_jpy: float,
    additional_cash_jpy: float,
    constraints: dict,
    sell_symbols: set,
    reduce_symbols: set,
    min_dividend_yield: Optional[float] = None,
) -> list[dict]:
    """Generate INCREASE actions for existing positions worth adding to.

    Rules:
      - Positive base expected return
      - Would not exceed single-stock limit after increase
      - Prioritized by base return (highest first)
      - If min_dividend_yield specified, only consider positions meeting it
    """
    actions = []
    if total_value_jpy <= 0:
        return actions

    available_cash = freed_cash_jpy + additional_cash_jpy
    if available_cash <= 0:
        return actions

    max_single = constraints["max_single_ratio"]

    # Build candidates: existing positions with positive return, not being sold/reduced
    candidates = []
    for pos in positions:
        symbol = pos.get("symbol", "")
        if symbol in sell_symbols or symbol in reduce_symbols or _is_cash(symbol):
            continue
        base_ret = pos.get("base")
        if base_ret is None or base_ret <= 0:
            continue
        if min_dividend_yield is not None:
            div_yield = pos.get("dividend_yield") or 0
            if div_yield < min_dividend_yield:
                continue
        candidates.append(pos)

    # Sort by base return descending
    candidates.sort(key=lambda p: p.get("base", 0), reverse=True)

    # Allocate available cash proportionally to top candidates
    allocated = 0.0
    new_total = total_value_jpy + additional_cash_jpy
    for pos in candidates:
        if allocated >= available_cash:
            break
        symbol = pos.get("symbol", "")
        value_jpy = _pos_value_jpy(pos)
        current_w = value_jpy / total_value_jpy if total_value_jpy > 0 else 0

        # How much can we add before hitting the limit?
        max_add = max_single * new_total - value_jpy
        if max_add <= 0:
            continue

        # Allocate up to MAX_ALLOC_PER_POSITION of remaining cash per position
        alloc = min(available_cash - allocated, max_add, available_cash * MAX_ALLOC_PER_POSITION)
        if alloc < MIN_ALLOC_JPY:
            continue

        base_ret = pos.get("base", 0)
        actions.append({
            "action": "increase",
            "symbol": symbol,
            "name": pos.get("name", ""),
            "amount_jpy": round(alloc, 0),
            "reason": f"ベース期待値 +{base_ret*100:.1f}% (比率{current_w*100:.1f}%→{(value_jpy+alloc)/new_total*100:.1f}%)",
            "priority": 6,
        })
        allocated += alloc

    return actions


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def generate_rebalance_proposal(
    forecast_result: dict,
    health_result: Optional[dict] = None,
    concentration: Optional[dict] = None,
    high_corr_pairs: Optional[list[dict]] = None,
    strategy: str = "balanced",
    reduce_sector: Optional[str] = None,
    reduce_currency: Optional[str] = None,
    max_single_ratio: Optional[float] = None,
    max_sector_hhi: Optional[float] = None,
    max_region_hhi: Optional[float] = None,
    additional_cash: float = 0.0,
    min_dividend_yield: Optional[float] = None,
) -> dict:
    """Generate a rebalancing proposal for the portfolio.

    Parameters
    ----------
    forecast_result : dict
        Output of estimate_portfolio_return().
        Must contain "positions" list and "portfolio" dict.
    health_result : dict, optional
        Output of run_health_check().
    concentration : dict, optional
        Output of analyze_concentration().
    high_corr_pairs : list[dict], optional
        Output of find_high_correlation_pairs().
    strategy : str
        "defensive", "balanced", or "aggressive".
    reduce_sector : str, optional
        Sector name to reduce (e.g., "Technology").
    reduce_currency : str, optional
        Currency to reduce (e.g., "USD").
    max_single_ratio : float, optional
        Override max single stock ratio.
    max_sector_hhi : float, optional
        Override max sector HHI.
    max_region_hhi : float, optional
        Override max region HHI.
    additional_cash : float
        Additional cash to invest (in JPY).
    min_dividend_yield : float, optional
        Minimum dividend yield filter for increase candidates.

    Returns
    -------
    dict
        {
            "actions": list[dict],
            "before": {"base_return": float, "sector_hhi": float, "region_hhi": float},
            "after": {"base_return": float, "sector_hhi": float, "region_hhi": float},
            "freed_cash_jpy": float,
            "additional_cash_jpy": float,
            "strategy": str,
            "constraints": dict,
        }
    """
    constraints = _build_constraints(
        strategy=strategy,
        max_single_ratio=max_single_ratio,
        max_sector_hhi=max_sector_hhi,
        max_region_hhi=max_region_hhi,
    )

    positions = forecast_result.get("positions", [])
    total_value_jpy = forecast_result.get("total_value_jpy", 0)

    # --- Before metrics ---
    before_metrics = _compute_current_metrics(positions, total_value_jpy)
    before = {
        "base_return": round(before_metrics["base_return"], 4),
        "sector_hhi": round(compute_hhi(list(before_metrics["sector_weights"].values())), 4),
        "region_hhi": round(compute_hhi(list(before_metrics["region_weights"].values())), 4),
    }
    # Use concentration module values if available (more accurate)
    if concentration:
        before["sector_hhi"] = concentration.get("sector_hhi", before["sector_hhi"])
        before["region_hhi"] = concentration.get("region_hhi", before["region_hhi"])

    # --- Step 1: Sell actions ---
    sell_actions = _generate_sell_actions(positions, health_result)
    sell_symbols = {a["symbol"] for a in sell_actions}

    # --- Step 2: Reduce actions ---
    reduce_actions = _generate_reduce_actions(
        positions=positions,
        total_value_jpy=total_value_jpy,
        constraints=constraints,
        high_corr_pairs=high_corr_pairs,
        reduce_sector=reduce_sector,
        reduce_currency=reduce_currency,
        sell_symbols=sell_symbols,
    )
    reduce_symbols = {a["symbol"] for a in reduce_actions}

    # --- Calculate freed cash ---
    freed_from_sells = sum(a.get("value_jpy", 0) for a in sell_actions)
    freed_from_reduces = sum(a.get("value_jpy", 0) for a in reduce_actions)
    freed_cash_jpy = freed_from_sells + freed_from_reduces

    # --- Step 3: Increase actions ---
    increase_actions = _generate_increase_actions(
        positions=positions,
        total_value_jpy=total_value_jpy,
        freed_cash_jpy=freed_cash_jpy,
        additional_cash_jpy=additional_cash,
        constraints=constraints,
        sell_symbols=sell_symbols,
        reduce_symbols=reduce_symbols,
        min_dividend_yield=min_dividend_yield,
    )

    # --- All actions ---
    all_actions = sell_actions + reduce_actions + increase_actions
    all_actions.sort(key=lambda a: a.get("priority", 99))

    # --- After metrics (estimated) ---
    after_return = before_metrics["base_return"]
    for a in sell_actions:
        sym = a["symbol"]
        pos = next((p for p in positions if p.get("symbol") == sym), {})
        base_ret = pos.get("base") or 0
        w = before_metrics["weights"].get(sym, 0)
        after_return -= base_ret * w

    for a in reduce_actions:
        sym = a["symbol"]
        pos = next((p for p in positions if p.get("symbol") == sym), {})
        base_ret = pos.get("base") or 0
        w = before_metrics["weights"].get(sym, 0)
        after_return -= base_ret * w * a.get("ratio", 0)

    for a in increase_actions:
        sym = a["symbol"]
        pos = next((p for p in positions if p.get("symbol") == sym), {})
        base_ret = pos.get("base") or 0
        amount = a.get("amount_jpy", 0)
        new_total = total_value_jpy + additional_cash
        if new_total > 0:
            after_return += base_ret * (amount / new_total)

    after = {
        "base_return": round(after_return, 4),
        "sector_hhi": before["sector_hhi"],  # simplified estimate
        "region_hhi": before["region_hhi"],
    }

    return {
        "actions": all_actions,
        "before": before,
        "after": after,
        "freed_cash_jpy": round(freed_cash_jpy, 0),
        "additional_cash_jpy": additional_cash,
        "strategy": strategy,
        "constraints": constraints,
    }
