"""Portfolio compound interest simulation engine (KIK-366).

Simulates portfolio growth over multiple years across 3 scenarios
(optimistic/base/pessimistic), factoring in monthly contributions
and dividend reinvestment.
"""

from typing import Optional, Union

from src.core.models import SimulationResult, YearlySnapshot


def simulate_portfolio(
    current_value: float,
    returns: dict[str, Union[float, None]],
    dividend_yield: float,
    years: int = 10,
    monthly_add: float = 0.0,
    reinvest_dividends: bool = True,
    target: Optional[float] = None,
) -> SimulationResult:
    """Run compound interest simulation for 3 scenarios.

    Parameters
    ----------
    current_value : float
        Current portfolio value in JPY.
    returns : dict
        {"optimistic": float|None, "base": float|None, "pessimistic": float|None}
    dividend_yield : float
        Portfolio weighted-average dividend yield (e.g. 0.026).
    years : int
        Number of years to simulate.
    monthly_add : float
        Monthly contribution in JPY.
    reinvest_dividends : bool
        Whether to reinvest dividends.
    target : float or None
        Target amount in JPY.

    Returns
    -------
    SimulationResult
    """
    base_return = returns.get("base")

    # If base return is None, simulation is not possible
    if base_return is None:
        return SimulationResult.empty()

    # Build scenarios (skip if return is None)
    scenario_keys = ["optimistic", "base", "pessimistic"]
    scenarios: dict[str, list[YearlySnapshot]] = {}

    for key in scenario_keys:
        scenario_return = returns.get(key)
        if scenario_return is None:
            continue

        snapshots: list[YearlySnapshot] = []
        # Year 0: initial state
        snapshots.append(YearlySnapshot(
            year=0,
            value=current_value,
            cumulative_input=current_value,
            capital_gain=0.0,
            cumulative_dividends=0.0,
        ))

        prev_value = current_value
        cumulative_dividends = 0.0

        for year in range(1, years + 1):
            annual_add = monthly_add * 12
            dividends = prev_value * dividend_yield
            cumulative_dividends += dividends

            if reinvest_dividends:
                capital_gain_year = prev_value * scenario_return
                value = prev_value + capital_gain_year + dividends + annual_add
            else:
                capital_gain_year = prev_value * scenario_return
                value = prev_value + capital_gain_year + annual_add

            cumulative_input = current_value + annual_add * year

            if reinvest_dividends:
                total_capital_gain = value - cumulative_input - cumulative_dividends
            else:
                total_capital_gain = value - cumulative_input

            snapshots.append(YearlySnapshot(
                year=year,
                value=value,
                cumulative_input=cumulative_input,
                capital_gain=total_capital_gain,
                cumulative_dividends=cumulative_dividends,
            ))

            prev_value = value

        scenarios[key] = snapshots

    # Target year calculations
    target_year_base = None
    target_year_optimistic = None
    target_year_pessimistic = None
    required_monthly = None

    if target is not None:
        if "base" in scenarios:
            base_values = [s.value for s in scenarios["base"]]
            target_year_base = calculate_target_year(base_values, target)
        if "optimistic" in scenarios:
            opt_values = [s.value for s in scenarios["optimistic"]]
            target_year_optimistic = calculate_target_year(opt_values, target)
        if "pessimistic" in scenarios:
            pess_values = [s.value for s in scenarios["pessimistic"]]
            target_year_pessimistic = calculate_target_year(pess_values, target)

        # Required monthly if base doesn't reach target
        if target_year_base is None:
            required_monthly = calculate_required_monthly(
                current_value=current_value,
                return_rate=base_return,
                dividend_yield=dividend_yield,
                target=target,
                years=years,
                reinvest_dividends=reinvest_dividends,
            )

    # Dividend effect
    div_effect, div_effect_pct = _calculate_dividend_effect(
        current_value=current_value,
        base_return=base_return,
        dividend_yield=dividend_yield,
        years=years,
        monthly_add=monthly_add,
    )

    return SimulationResult(
        scenarios=scenarios,
        target=target,
        target_year_base=target_year_base,
        target_year_optimistic=target_year_optimistic,
        target_year_pessimistic=target_year_pessimistic,
        required_monthly=required_monthly,
        dividend_effect=div_effect,
        dividend_effect_pct=div_effect_pct,
        years=years,
        monthly_add=monthly_add,
        reinvest_dividends=reinvest_dividends,
        current_value=current_value,
        portfolio_return_base=base_return,
        dividend_yield=dividend_yield,
    )


def calculate_target_year(
    yearly_values: list[float],
    target: float,
) -> Optional[float]:
    """Calculate the year when target is reached via linear interpolation.

    Parameters
    ----------
    yearly_values : list[float]
        [year0_value, year1_value, ..., yearN_value]
    target : float
        Target amount.

    Returns
    -------
    float or None
        Fractional year (e.g. 4.7), or None if not reached.
    """
    if not yearly_values:
        return None

    if yearly_values[0] >= target:
        return 0.0

    for i in range(1, len(yearly_values)):
        if yearly_values[i] >= target:
            prev_val = yearly_values[i - 1]
            curr_val = yearly_values[i]
            if curr_val == prev_val:
                return float(i)
            fraction = (target - prev_val) / (curr_val - prev_val)
            return (i - 1) + fraction

    return None


def calculate_required_monthly(
    current_value: float,
    return_rate: float,
    dividend_yield: float,
    target: float,
    years: int,
    reinvest_dividends: bool = True,
) -> float:
    """Calculate required monthly contribution to reach target.

    Parameters
    ----------
    current_value : float
        Current portfolio value.
    return_rate : float
        Base scenario annual return rate.
    dividend_yield : float
        Portfolio dividend yield.
    target : float
        Target amount.
    years : int
        Number of years.
    reinvest_dividends : bool
        Whether dividends are reinvested.

    Returns
    -------
    float
        Required monthly contribution in JPY.
    """
    effective_rate = return_rate + (dividend_yield if reinvest_dividends else 0)

    # Future value of current portfolio without additional contributions
    future_value_no_add = current_value * ((1 + effective_rate) ** years)
    gap = target - future_value_no_add

    if gap <= 0:
        return 0.0

    if effective_rate == 0:
        return gap / (years * 12)

    # Annuity future value formula: FV = A * ((1+r)^n - 1) / r
    # Solve for A: A = gap * r / ((1+r)^n - 1)
    r = effective_rate
    n = years
    annuity_factor = ((1 + r) ** n - 1) / r
    annual_need = gap / annuity_factor
    return annual_need / 12


def _calculate_dividend_effect(
    current_value: float,
    base_return: float,
    dividend_yield: float,
    years: int,
    monthly_add: float,
) -> tuple[float, float]:
    """Calculate the effect of dividend reinvestment.

    Parameters
    ----------
    current_value : float
        Current portfolio value.
    base_return : float
        Base scenario return rate.
    dividend_yield : float
        Dividend yield.
    years : int
        Number of years.
    monthly_add : float
        Monthly contribution.

    Returns
    -------
    tuple[float, float]
        (dividend_effect in JPY, dividend_effect_pct as ratio)
    """
    if dividend_yield == 0 or years == 0:
        return 0.0, 0.0

    # With reinvestment
    val_with = current_value
    for _ in range(years):
        annual_add = monthly_add * 12
        dividends = val_with * dividend_yield
        capital_gain = val_with * base_return
        val_with = val_with + capital_gain + dividends + annual_add

    # Without reinvestment
    val_without = current_value
    for _ in range(years):
        annual_add = monthly_add * 12
        capital_gain = val_without * base_return
        val_without = val_without + capital_gain + annual_add

    effect = val_with - val_without
    effect_pct = effect / val_without if val_without != 0 else 0.0

    return effect, effect_pct
