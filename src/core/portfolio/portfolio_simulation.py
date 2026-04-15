"""What-If portfolio simulation (KIK-376, KIK-451).

Temporarily adds/removes stocks from the portfolio and compares
before/after metrics (snapshot, concentration, forecast, health).
Uses a temp CSV approach to leverage existing csv_path-based functions.

KIK-451: Added swap simulation support via --remove argument.
"""

import copy
import os
import tempfile

from src.core.portfolio.fx_utils import get_fx_rates  # KIK-511
from src.core.portfolio.portfolio_manager import (
    get_snapshot,
    get_structure_analysis,
    load_portfolio,
    merge_positions,
    save_portfolio,
)
from src.core.return_estimate import estimate_portfolio_return
from src.core.ticker_utils import infer_currency, validate_lot_size


def parse_add_arg(add_str: str) -> list[dict]:
    """Parse --add argument into a list of proposed positions.

    Format: "SYMBOL:SHARES:PRICE,SYMBOL:SHARES:PRICE,..."

    Parameters
    ----------
    add_str : str
        Comma-separated entries of "SYMBOL:SHARES:PRICE".

    Returns
    -------
    list[dict]
        Each dict has: symbol, shares, cost_price, cost_currency.

    Raises
    ------
    ValueError
        If format is invalid.
    """
    if not add_str or not add_str.strip():
        raise ValueError("--add の値が空です。形式: SYMBOL:SHARES:PRICE")

    results: list[dict] = []
    entries = [e.strip() for e in add_str.split(",") if e.strip()]

    for entry in entries:
        parts = entry.split(":")
        if len(parts) != 3:
            raise ValueError(
                f"不正な形式: '{entry}' — SYMBOL:SHARES:PRICE の形式で指定してください"
            )

        symbol = parts[0].strip()
        if not symbol:
            raise ValueError(f"銘柄シンボルが空です: '{entry}'")

        try:
            shares = int(parts[1].strip())
        except ValueError:
            raise ValueError(
                f"株数が不正です: '{parts[1].strip()}' in '{entry}'"
            )
        if shares <= 0:
            raise ValueError(
                f"株数は正の整数を指定してください: {shares} in '{entry}'"
            )

        validate_lot_size(shares, symbol)

        try:
            price = float(parts[2].strip())
        except ValueError:
            raise ValueError(
                f"価格が不正です: '{parts[2].strip()}' in '{entry}'"
            )
        if price <= 0:
            raise ValueError(
                f"価格は正の数を指定してください: {price} in '{entry}'"
            )

        cost_currency = infer_currency(symbol)

        results.append({
            "symbol": symbol,
            "shares": shares,
            "cost_price": price,
            "cost_currency": cost_currency,
        })

    return results


def parse_remove_arg(remove_str: str) -> list[dict]:
    """Parse --remove argument into a list of removal specs.

    Format: "SYMBOL:SHARES,SYMBOL:SHARES,..."
    Note: NO price field — proceeds are computed from current market value.

    Parameters
    ----------
    remove_str : str
        Comma-separated entries of "SYMBOL:SHARES".

    Returns
    -------
    list[dict]
        Each dict has: symbol (str), shares (int).

    Raises
    ------
    ValueError
        If format is invalid, symbol is empty, or shares is not a positive integer.
    """
    if not remove_str or not remove_str.strip():
        raise ValueError("--remove の値が空です。形式: SYMBOL:SHARES")

    results: list[dict] = []
    entries = [e.strip() for e in remove_str.split(",") if e.strip()]

    for entry in entries:
        parts = entry.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"不正な形式: '{entry}' — SYMBOL:SHARES の形式で指定してください（価格不要）"
            )

        symbol = parts[0].strip()
        if not symbol:
            raise ValueError(f"銘柄シンボルが空です: '{entry}'")

        try:
            shares = int(parts[1].strip())
        except ValueError:
            raise ValueError(
                f"株数が不正です: '{parts[1].strip()}' in '{entry}'"
            )
        if shares <= 0:
            raise ValueError(
                f"株数は正の整数を指定してください: {shares} in '{entry}'"
            )

        validate_lot_size(shares, symbol)

        results.append({"symbol": symbol, "shares": shares})

    return results


def remove_positions(current: list[dict], removals: list[dict]) -> list[dict]:
    """Remove specified shares from the current portfolio (simulation only).

    Does not modify the original portfolio CSV.
    Input lists are not mutated (deep copy).

    Parameters
    ----------
    current : list[dict]
        Current portfolio (from load_portfolio).
    removals : list[dict]
        Removal specs from parse_remove_arg. Each dict has: symbol, shares.

    Returns
    -------
    list[dict]
        Portfolio after applying removals (positions with 0 shares are deleted).

    Raises
    ------
    ValueError
        If a removal symbol is not found in current, or if removal shares
        exceed held shares.
    """
    merged = copy.deepcopy(current)
    symbol_map: dict[str, int] = {
        p["symbol"].upper(): i for i, p in enumerate(merged)
    }

    for removal in removals:
        key = removal["symbol"].upper()
        if key not in symbol_map:
            raise ValueError(
                f"{removal['symbol']} はポートフォリオに存在しません"
            )
        idx = symbol_map[key]
        held = merged[idx]["shares"]
        if removal["shares"] > held:
            raise ValueError(
                f"保有数を超えています: {removal['symbol']} 保有 {held} 株に対して "
                f"{removal['shares']} 株の売却を指定"
            )
        merged[idx] = dict(merged[idx])
        merged[idx]["shares"] = held - removal["shares"]

    return [p for p in merged if p["shares"] > 0]


def _compute_proceeds(
    removals: list[dict],
    snapshot_positions: list[dict],
) -> float:
    """Compute total proceeds in JPY from selling specified positions at market price.

    Uses evaluation_jpy from the before-snapshot to price each removal.
    Partial removals are prorated: (removal_shares / held_shares) * evaluation_jpy.

    Parameters
    ----------
    removals : list[dict]
        Removal specs from parse_remove_arg. Each dict has: symbol, shares.
    snapshot_positions : list[dict]
        Positions from get_snapshot() result["positions"].

    Returns
    -------
    float
        Total proceeds in JPY. Returns 0.0 for any symbol not found in snapshot.
    """
    pos_map = {p["symbol"].upper(): p for p in snapshot_positions}
    total = 0.0
    for removal in removals:
        pos = pos_map.get(removal["symbol"].upper())
        if pos is None:
            continue
        held = pos.get("shares", 0)
        if held <= 0:
            continue
        ratio = min(removal["shares"] / held, 1.0)
        # Note: if evaluation_jpy is 0 (API price fetch failed), proceeds will be 0
        # for this position. This is graceful degradation — the caller should check
        # whether proceeds_jpy is plausible relative to the position size.
        total += ratio * pos.get("evaluation_jpy", 0.0)
    return total


def _extract_metrics(snapshot: dict, structure: dict, forecast: dict) -> dict:
    """Extract flat comparison metrics from analysis results."""
    portfolio_return = forecast.get("portfolio", {})

    return {
        "total_value_jpy": snapshot.get("total_value_jpy", 0),
        "total_cost_jpy": snapshot.get("total_cost_jpy", 0),
        "total_pnl_jpy": snapshot.get("total_pnl_jpy", 0),
        "total_pnl_pct": snapshot.get("total_pnl_pct", 0),
        "sector_hhi": structure.get("sector_hhi", 0),
        "region_hhi": structure.get("region_hhi", 0),
        "currency_hhi": structure.get("currency_hhi", 0),
        "concentration_multiplier": structure.get(
            "concentration_multiplier", 1.0
        ),
        "risk_level": structure.get("risk_level", "分散"),
        "forecast_optimistic": portfolio_return.get("optimistic"),
        "forecast_base": portfolio_return.get("base"),
        "forecast_pessimistic": portfolio_return.get("pessimistic"),
    }


def _compute_required_cash(
    proposed: list[dict], fx_rates: dict
) -> float:
    """Compute total required cash in JPY for proposed positions."""
    total = 0.0
    for prop in proposed:
        currency = prop.get("cost_currency", "JPY")
        fx_rate = fx_rates.get(currency, 1.0)
        total += prop["shares"] * prop["cost_price"] * fx_rate
    return total


def _compute_judgment(
    before: dict,
    after: dict,
    proposed_health: list[dict],
    removed_health: list[dict] | None = None,
) -> dict:
    """Compute recommendation judgment based on 4 axes.

    Axes:
    1. Diversification: HHI change (sector_hhi as primary)
    2. Return: forecast_base change
    3. Health: exit signals in proposed stocks
    4. Removed health: exit/caution in sold stocks (positive factor, KIK-451)

    Returns
    -------
    dict
        {"recommendation": str, "reasons": list[str]}
        recommendation is one of: "recommend", "caution", "not_recommended"
    """
    reasons: list[str] = []

    # 1. Diversification check
    before_hhi = max(
        before.get("sector_hhi", 0),
        before.get("region_hhi", 0),
    )
    after_hhi = max(
        after.get("sector_hhi", 0),
        after.get("region_hhi", 0),
    )
    hhi_improved = after_hhi < before_hhi
    hhi_worsened = after_hhi > before_hhi + 0.05  # threshold

    if hhi_improved:
        reasons.append(
            f"分散度改善: HHI {before_hhi:.2f} → {after_hhi:.2f}"
        )
    elif hhi_worsened:
        reasons.append(
            f"集中度悪化: HHI {before_hhi:.2f} → {after_hhi:.2f}"
        )

    # 2. Return check
    before_ret = before.get("forecast_base")
    after_ret = after.get("forecast_base")
    ret_improved = False
    ret_worsened = False

    if before_ret is not None and after_ret is not None:
        diff_pp = (after_ret - before_ret) * 100  # percentage points
        if diff_pp > 0.1:
            ret_improved = True
            reasons.append(f"期待リターン改善: {diff_pp:+.1f}pp")
        elif diff_pp < -0.5:
            ret_worsened = True
            reasons.append(f"期待リターン悪化: {diff_pp:+.1f}pp")

    # 3. Health check for proposed stocks
    has_exit = False
    has_warning = False

    for ph in proposed_health:
        alert = ph.get("alert", {})
        level = alert.get("level", "none")
        symbol = ph.get("symbol", "")
        if level == "exit":
            has_exit = True
            reasons.append(f"撤退シグナル: {symbol}")
        elif level in ("caution", "early_warning"):
            has_warning = True
            alert_label = alert.get("label", level)
            reasons.append(f"注意シグナル: {symbol} ({alert_label})")

    # 4. Removed stocks health (KIK-451): exit/caution in sold stocks is a positive signal.
    #    Design intent: adds to "reasons" text only. Does NOT override the recommendation
    #    judgment (e.g. HHI worsening + return drop still yields "not_recommended" even
    #    if an exit stock was sold). The positive signal is surfaced as context for the
    #    user, not as a mechanical override — selling one bad stock does not compensate
    #    for degraded diversification or lower expected returns.
    for ph in (removed_health or []):
        alert = ph.get("alert", {})
        level = alert.get("level", "none")
        symbol = ph.get("symbol", "")
        if level in ("exit", "caution", "early_warning"):
            alert_label = alert.get("label", level)
            reasons.append(f"撤退/注意対象を売却: {symbol} ({alert_label})")

    # 5. ETF quality signals (KIK-469 Phase 2)
    for ph in proposed_health:
        etf_h = ph.get("change_quality", {}).get("etf_health")
        if etf_h:
            score = etf_h.get("score", 50)
            symbol = ph.get("symbol", "")
            if score >= 75:
                reasons.append(f"ETF\u54c1\u8cea\u826f\u597d: {symbol} (\u30b9\u30b3\u30a2 {score}/100)")
            elif score < 40:
                has_warning = True
                reasons.append(f"ETF\u54c1\u8cea\u4f4e: {symbol} (\u30b9\u30b3\u30a2 {score}/100)")
            for etf_alert in etf_h.get("alerts", []):
                reasons.append(f"ETF\u6ce8\u610f: {symbol} - {etf_alert}")

    # Judgment logic
    if has_exit or (hhi_worsened and ret_worsened):
        recommendation = "not_recommended"
    elif hhi_improved and ret_improved and not has_exit:
        recommendation = "recommend"
    elif has_warning or hhi_worsened or ret_worsened:
        recommendation = "caution"
    elif hhi_improved or ret_improved:
        recommendation = "recommend"
    else:
        recommendation = "caution"

    if not reasons:
        reasons.append("大きな変化なし")

    return {
        "recommendation": recommendation,
        "reasons": reasons,
    }


def run_what_if_simulation(
    csv_path: str,
    proposed: list[dict],
    client,
    removals: list[dict] | None = None,
) -> dict:
    """Run What-If simulation comparing before/after portfolio metrics.

    Uses a temp CSV file to leverage existing csv_path-based analysis
    functions without modifying the original portfolio.

    Parameters
    ----------
    csv_path : str
        Path to the current portfolio CSV.
    proposed : list[dict]
        Proposed positions (from parse_add_arg). May be empty for sell-only.
    client
        yahoo_client module.
    removals : list[dict] | None
        Removal specs from parse_remove_arg (KIK-451). Each dict has:
        symbol, shares. None = add-only mode (existing behavior unchanged).

    Returns
    -------
    dict
        Simulation result with before/after comparison.
        KIK-451: When removals is not None, also includes:
          "removals": enriched list (each dict gains "proceeds_jpy" key)
          "removed_health": list of health check results for removed stocks
          "proceeds_jpy": total JPY proceeds from removals
          "net_cash_jpy": proceeds_jpy - required_cash_jpy
    """
    # 1. Load current portfolio
    current = load_portfolio(csv_path)

    # 2. Before analysis (uses cache for subsequent calls)
    before_snapshot = get_snapshot(csv_path, client)
    before_structure = get_structure_analysis(csv_path, client)
    before_forecast = estimate_portfolio_return(csv_path, client)
    before_metrics = _extract_metrics(
        before_snapshot, before_structure, before_forecast
    )

    # 3. (KIK-451) Apply removals: build after_current with specified shares removed
    if removals:
        after_current = remove_positions(current, removals)
    else:
        after_current = current

    # 4. Merge proposed into after_current
    merged = merge_positions(after_current, proposed)

    # 5. Write to temp CSV
    temp_fd, temp_path = tempfile.mkstemp(suffix=".csv", prefix="whatif_")
    os.close(temp_fd)

    try:
        save_portfolio(merged, temp_path)

        # 6. After analysis (new stocks will need API calls,
        #    existing stocks hit yahoo_client's 24h cache)
        after_snapshot = get_snapshot(temp_path, client)
        after_structure = get_structure_analysis(temp_path, client)
        after_forecast = estimate_portfolio_return(temp_path, client)
        after_metrics = _extract_metrics(
            after_snapshot, after_structure, after_forecast
        )

        # 7. Health check on proposed stocks only
        proposed_health: list[dict] = []
        try:
            from src.core.health_check import run_health_check

            health_data = run_health_check(temp_path, client)
            proposed_symbols = {
                p["symbol"].upper() for p in proposed
            }
            for pos in health_data.get("positions", []):
                if pos.get("symbol", "").upper() in proposed_symbols:
                    proposed_health.append(pos)
        except ImportError:
            pass

        # 8. FX rates and required cash
        fx_rates = before_snapshot.get("fx_rates", {"JPY": 1.0})
        required_cash = _compute_required_cash(proposed, fx_rates)

        # 9. (KIK-451) Proceeds and removed-stock health check
        removed_health: list[dict] = []
        proceeds = 0.0
        enriched_removals: list[dict] | None = None

        if removals:
            snapshot_positions = before_snapshot.get("positions", [])
            proceeds = _compute_proceeds(removals, snapshot_positions)

            # Enrich each removal with its per-stock proceeds for the formatter
            pos_map = {p["symbol"].upper(): p for p in snapshot_positions}
            enriched_removals = []
            for rem in removals:
                rem_copy = dict(rem)
                pos = pos_map.get(rem["symbol"].upper(), {})
                held = pos.get("shares", 0)
                if held > 0:
                    ratio = min(rem["shares"] / held, 1.0)
                    rem_copy["proceeds_jpy"] = ratio * pos.get("evaluation_jpy", 0.0)
                else:
                    rem_copy["proceeds_jpy"] = 0.0
                enriched_removals.append(rem_copy)

            # Health check for removed stocks via temporary CSV
            removal_portfolio = [
                p for p in current
                if p["symbol"].upper() in {r["symbol"].upper() for r in removals}
            ]
            if removal_portfolio:
                rem_fd, rem_path = tempfile.mkstemp(
                    suffix=".csv", prefix="whatif_rem_"
                )
                os.close(rem_fd)
                try:
                    save_portfolio(removal_portfolio, rem_path)
                    try:
                        from src.core.health_check import run_health_check

                        rem_health_data = run_health_check(rem_path, client)
                        removal_symbols = {
                            r["symbol"].upper() for r in removals
                        }
                        for pos in rem_health_data.get("positions", []):
                            if pos.get("symbol", "").upper() in removal_symbols:
                                removed_health.append(pos)
                    except ImportError:
                        pass
                finally:
                    if os.path.exists(rem_path):
                        os.remove(rem_path)

        # 10. Judgment
        judgment = _compute_judgment(
            before_metrics, after_metrics, proposed_health,
            removed_health=removed_health if removals else None,
        )

    finally:
        # 11. Cleanup main temp CSV
        if os.path.exists(temp_path):
            os.remove(temp_path)

    result: dict = {
        "proposed": proposed,
        "before": before_metrics,
        "after": after_metrics,
        "proposed_health": proposed_health,
        "required_cash_jpy": required_cash,
        "judgment": judgment,
    }

    if removals is not None:
        result["removals"] = enriched_removals or []
        result["removed_health"] = removed_health
        result["proceeds_jpy"] = proceeds
        result["net_cash_jpy"] = proceeds - required_cash

    return result
