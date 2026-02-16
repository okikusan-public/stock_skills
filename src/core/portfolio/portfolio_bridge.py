"""Bridge between portfolio management and stress test skills (KIK-342 -> KIK-339).

Reads portfolio.csv and converts it into arguments suitable for the
stress-test skill (run_stress_test.py).
"""

import csv
import os
from typing import Optional


# Default portfolio CSV path (relative to the project root)
_DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    ".claude", "skills", "stock-portfolio", "data", "portfolio.csv",
)

# Stress test script path
_STRESS_TEST_SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    ".claude", "skills", "stress-test", "scripts", "run_stress_test.py",
)


def _load_portfolio_csv(csv_path: str) -> list[dict]:
    """Load portfolio positions from a CSV file.

    Tries to use ``portfolio_manager.load_portfolio()`` if available,
    otherwise falls back to direct CSV reading.

    Parameters
    ----------
    csv_path : str
        Path to the portfolio CSV file.

    Returns
    -------
    list[dict]
        List of position dicts with keys: symbol, shares, cost_price,
        cost_currency, purchase_date, memo.
    """
    # Try portfolio_manager first (may be implemented later)
    try:
        from src.core.portfolio.portfolio_manager import load_portfolio as _pm_load
        return _pm_load(csv_path)
    except (ImportError, ModuleNotFoundError):
        pass

    # Fallback: direct CSV reading
    positions: list[dict] = []
    if not os.path.exists(csv_path):
        return positions

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                shares = int(float(row.get("shares", "0")))
            except (ValueError, TypeError):
                shares = 0

            try:
                cost_price = float(row.get("cost_price", "0"))
            except (ValueError, TypeError):
                cost_price = 0.0

            positions.append({
                "symbol": row.get("symbol", "").strip(),
                "shares": shares,
                "cost_price": cost_price,
                "cost_currency": row.get("cost_currency", "JPY").strip(),
                "purchase_date": row.get("purchase_date", "").strip(),
                "memo": row.get("memo", "").strip(),
            })

    # Filter out empty symbols
    positions = [p for p in positions if p["symbol"]]
    return positions


def _get_current_price(symbol: str) -> Optional[float]:
    """Try to fetch the current price for a symbol via yahoo_client.

    Returns None if the fetch fails.
    """
    try:
        from src.data import yahoo_client
        info = yahoo_client.get_stock_info(symbol)
        if info is not None:
            return info.get("price")
    except (ImportError, Exception):
        pass
    return None


def portfolio_to_stress_args(csv_path: Optional[str] = None) -> dict:
    """Generate stress-test arguments from portfolio.csv.

    Parameters
    ----------
    csv_path : str, optional
        Path to portfolio.csv.  Uses the default skill data path if omitted.

    Returns
    -------
    dict
        {
            "symbols": list[str],
            "weights": list[float],
            "portfolio_arg": str,
            "weights_arg": str,
        }

    Raises
    ------
    FileNotFoundError
        If the CSV file does not exist.
    ValueError
        If the CSV contains no valid positions.
    """
    if csv_path is None:
        csv_path = os.path.normpath(_DEFAULT_CSV_PATH)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Portfolio CSV not found: {csv_path}")

    positions = _load_portfolio_csv(csv_path)
    if not positions:
        raise ValueError("Portfolio CSV contains no valid positions.")

    symbols: list[str] = []
    values: list[float] = []

    for pos in positions:
        symbol = pos["symbol"]
        shares = pos["shares"]
        if shares <= 0:
            continue

        # Try to get current price; fall back to cost_price
        current_price = _get_current_price(symbol)
        if current_price is None:
            current_price = pos["cost_price"]

        market_value = current_price * shares
        symbols.append(symbol)
        values.append(market_value)

    if not symbols:
        raise ValueError("No positions with positive shares found.")

    # Compute weights from market values
    total_value = sum(values)
    if total_value <= 0:
        # Equal weight as fallback
        n = len(symbols)
        weights = [round(1.0 / n, 4) for _ in range(n)]
    else:
        weights = [round(v / total_value, 4) for v in values]

    # Normalize rounding errors so weights sum exactly to 1.0
    weight_sum = sum(weights)
    if weight_sum > 0 and abs(weight_sum - 1.0) > 0.001:
        weights = [w / weight_sum for w in weights]
    # Adjust last weight to ensure exact sum
    if weights:
        remainder = 1.0 - sum(weights[:-1])
        weights[-1] = round(remainder, 4)

    # Build argument strings
    portfolio_arg = f"--portfolio {','.join(symbols)}"
    weights_str = ",".join(f"{w:.4f}" for w in weights)
    weights_arg = f"--weights {weights_str}"

    return {
        "symbols": symbols,
        "weights": weights,
        "portfolio_arg": portfolio_arg,
        "weights_arg": weights_arg,
    }


def build_stress_test_command(
    csv_path: Optional[str] = None,
    scenario: Optional[str] = None,
    base_shock: float = -0.20,
) -> str:
    """Build a full stress-test command string from portfolio CSV.

    Parameters
    ----------
    csv_path : str, optional
        Path to portfolio.csv.  Uses the default skill data path if omitted.
    scenario : str, optional
        Scenario name (e.g. "triple_decline", "dollar_yen").
    base_shock : float
        Base shock rate (default: -0.20 = -20%).

    Returns
    -------
    str
        Full command string, e.g.:
        "python3 .../run_stress_test.py --portfolio 7203.T,AAPL,D05.SI
         --weights 0.50,0.30,0.20 --scenario triple_decline"
    """
    args = portfolio_to_stress_args(csv_path)

    script_path = os.path.normpath(_STRESS_TEST_SCRIPT)
    parts = [
        f"python3 {script_path}",
        args["portfolio_arg"],
        args["weights_arg"],
    ]

    if scenario:
        parts.append(f"--scenario {scenario}")

    if base_shock != -0.20:
        parts.append(f"--base-shock {base_shock}")

    return " ".join(parts)
