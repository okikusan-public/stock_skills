"""Tests for src/core/simulator.py (KIK-366)."""

import pytest

from src.core.simulator import (
    simulate_portfolio,
    calculate_target_year,
    calculate_required_monthly,
    _calculate_dividend_effect,
)
from src.core.models import SimulationResult, YearlySnapshot


# ===================================================================
# TestSimulatePortfolio
# ===================================================================

class TestSimulatePortfolio:
    """Tests for simulate_portfolio()."""

    def test_basic_simulation(self):
        """3 scenarios generated, correct number of snapshots."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"optimistic": 0.20, "base": 0.10, "pessimistic": -0.05},
            dividend_yield=0.02,
            years=5,
        )
        assert isinstance(result, SimulationResult)
        assert "optimistic" in result.scenarios
        assert "base" in result.scenarios
        assert "pessimistic" in result.scenarios
        # year 0 + 5 years = 6 snapshots
        for key in ["optimistic", "base", "pessimistic"]:
            assert len(result.scenarios[key]) == 6
            assert result.scenarios[key][0].year == 0
            assert result.scenarios[key][-1].year == 5

    def test_zero_years(self):
        """years=0 produces only the initial snapshot."""
        result = simulate_portfolio(
            current_value=500_000,
            returns={"optimistic": 0.20, "base": 0.10, "pessimistic": -0.05},
            dividend_yield=0.02,
            years=0,
        )
        for key in result.scenarios:
            assert len(result.scenarios[key]) == 1
            assert result.scenarios[key][0].year == 0
            assert result.scenarios[key][0].value == 500_000

    def test_one_year_calculation(self):
        """1-year compound matches hand calculation."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.02,
            years=1,
            monthly_add=0.0,
            reinvest_dividends=True,
        )
        base = result.scenarios["base"]
        assert len(base) == 2
        # Year 0
        assert base[0].value == 1_000_000
        # Year 1: value = 1_000_000 + 1_000_000*0.10 + 1_000_000*0.02 + 0
        #        = 1_000_000 + 100_000 + 20_000 = 1_120_000
        assert base[1].value == pytest.approx(1_120_000)
        assert base[1].cumulative_input == pytest.approx(1_000_000)
        assert base[1].cumulative_dividends == pytest.approx(20_000)
        # capital_gain = value - cumulative_input - cumulative_dividends
        #              = 1_120_000 - 1_000_000 - 20_000 = 100_000
        assert base[1].capital_gain == pytest.approx(100_000)

    def test_compound_calculation(self):
        """Multi-year compound interest matches hand calculation."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.0,
            years=3,
            monthly_add=0.0,
            reinvest_dividends=True,
        )
        base = result.scenarios["base"]
        # Year 1: 1_000_000 * 1.10 = 1_100_000
        assert base[1].value == pytest.approx(1_100_000)
        # Year 2: 1_100_000 * 1.10 = 1_210_000
        assert base[2].value == pytest.approx(1_210_000)
        # Year 3: 1_210_000 * 1.10 = 1_331_000
        assert base[3].value == pytest.approx(1_331_000)

    def test_compound_with_monthly_add(self):
        """Monthly additions compound correctly."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.0,
            years=2,
            monthly_add=50_000,
            reinvest_dividends=True,
        )
        base = result.scenarios["base"]
        annual_add = 50_000 * 12  # 600_000
        # Year 1: 1_000_000 * 1.10 + 600_000 = 1_700_000
        assert base[1].value == pytest.approx(1_700_000)
        assert base[1].cumulative_input == pytest.approx(1_000_000 + 600_000)
        # Year 2: 1_700_000 * 1.10 + 600_000 = 2_470_000
        assert base[2].value == pytest.approx(2_470_000)
        assert base[2].cumulative_input == pytest.approx(1_000_000 + 600_000 * 2)

    def test_negative_return(self):
        """Negative returns decrease value correctly."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": -0.10},
            dividend_yield=0.0,
            years=2,
        )
        base = result.scenarios["base"]
        # Year 1: 1_000_000 * 0.90 = 900_000
        assert base[1].value == pytest.approx(900_000)
        # Year 2: 900_000 * 0.90 = 810_000
        assert base[2].value == pytest.approx(810_000)
        assert base[2].value < base[1].value < base[0].value

    def test_zero_return(self):
        """Zero return with zero dividend keeps value unchanged."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.0},
            dividend_yield=0.0,
            years=5,
        )
        base = result.scenarios["base"]
        for snap in base:
            assert snap.value == pytest.approx(1_000_000)

    def test_reinvest_dividends_on(self):
        """Dividend reinvestment adds dividends to value."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.03,
            years=1,
            reinvest_dividends=True,
        )
        base = result.scenarios["base"]
        # value = 1_000_000 + 100_000 + 30_000 = 1_130_000
        assert base[1].value == pytest.approx(1_130_000)

    def test_reinvest_dividends_off(self):
        """Without reinvestment, dividends are tracked but not added to value."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.03,
            years=1,
            reinvest_dividends=False,
        )
        base = result.scenarios["base"]
        # value = 1_000_000 + 100_000 = 1_100_000 (no dividend added)
        assert base[1].value == pytest.approx(1_100_000)
        # But cumulative_dividends is still tracked
        assert base[1].cumulative_dividends == pytest.approx(30_000)

    def test_dividend_effect(self):
        """Reinvest ON produces higher final value than OFF."""
        result_on = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.03,
            years=5,
            reinvest_dividends=True,
        )
        result_off = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.03,
            years=5,
            reinvest_dividends=False,
        )
        val_on = result_on.scenarios["base"][-1].value
        val_off = result_off.scenarios["base"][-1].value
        assert val_on > val_off

    def test_target_reached(self):
        """Target year is calculated via linear interpolation."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.0,
            years=10,
            target=1_500_000,
        )
        assert result.target_year_base is not None
        # 1_000_000 * 1.10^n >= 1_500_000 → n ~ 4.25
        # Year 4: 1_000_000 * 1.10^4 = 1_464_100 < 1_500_000
        # Year 5: 1_000_000 * 1.10^5 = 1_610_510 >= 1_500_000
        assert 4.0 < result.target_year_base < 5.0

    def test_target_not_reached(self):
        """Target not reached within simulation period returns None."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.01},
            dividend_yield=0.0,
            years=3,
            target=5_000_000,
        )
        assert result.target_year_base is None
        assert result.required_monthly is not None
        assert result.required_monthly > 0

    def test_required_monthly(self):
        """Required monthly is computed when target is not reached."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.05},
            dividend_yield=0.0,
            years=10,
            target=10_000_000,
        )
        if result.target_year_base is None:
            assert result.required_monthly is not None
            assert result.required_monthly > 0

    def test_required_monthly_zero_return(self):
        """With 0% return, required monthly = gap / (years * 12)."""
        result = simulate_portfolio(
            current_value=0,
            returns={"base": 0.0},
            dividend_yield=0.0,
            years=10,
            target=1_200_000,
        )
        assert result.target_year_base is None
        assert result.required_monthly is not None
        # gap = 1_200_000, years * 12 = 120
        assert result.required_monthly == pytest.approx(10_000)

    def test_zero_initial_value(self):
        """Simulation works with initial value of 0."""
        result = simulate_portfolio(
            current_value=0,
            returns={"base": 0.10},
            dividend_yield=0.0,
            years=3,
            monthly_add=100_000,
        )
        base = result.scenarios["base"]
        assert base[0].value == 0
        # Year 1: 0 * 1.10 + 1_200_000 = 1_200_000
        assert base[1].value == pytest.approx(1_200_000)
        # Year 2: 1_200_000 * 1.10 + 1_200_000 = 2_520_000
        assert base[2].value == pytest.approx(2_520_000)

    def test_large_years(self):
        """30-year simulation runs without error."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"optimistic": 0.15, "base": 0.08, "pessimistic": -0.02},
            dividend_yield=0.025,
            years=30,
        )
        for key in result.scenarios:
            assert len(result.scenarios[key]) == 31
        # Optimistic should grow substantially over 30 years
        assert result.scenarios["optimistic"][-1].value > 1_000_000

    def test_none_base_return_empty(self):
        """base=None produces an empty SimulationResult."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"optimistic": 0.20, "base": None, "pessimistic": -0.05},
            dividend_yield=0.02,
            years=5,
        )
        assert result.scenarios == {}

    def test_none_optimistic_skipped(self):
        """optimistic=None skips that scenario only."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"optimistic": None, "base": 0.10, "pessimistic": -0.05},
            dividend_yield=0.02,
            years=5,
        )
        assert "optimistic" not in result.scenarios
        assert "base" in result.scenarios
        assert "pessimistic" in result.scenarios

    def test_dividend_effect_positive(self):
        """Positive dividend yield produces positive dividend effect."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.03,
            years=10,
        )
        assert result.dividend_effect > 0
        assert result.dividend_effect_pct > 0

    def test_dividend_effect_zero_yield(self):
        """Zero dividend yield produces zero dividend effect."""
        result = simulate_portfolio(
            current_value=1_000_000,
            returns={"base": 0.10},
            dividend_yield=0.0,
            years=10,
        )
        assert result.dividend_effect == 0.0
        assert result.dividend_effect_pct == 0.0

    def test_metadata_fields(self):
        """SimulationResult stores metadata correctly."""
        result = simulate_portfolio(
            current_value=2_000_000,
            returns={"base": 0.08},
            dividend_yield=0.025,
            years=5,
            monthly_add=50_000,
            reinvest_dividends=False,
            target=3_000_000,
        )
        assert result.years == 5
        assert result.monthly_add == 50_000
        assert result.reinvest_dividends is False
        assert result.current_value == 2_000_000
        assert result.portfolio_return_base == 0.08
        assert result.dividend_yield == 0.025
        assert result.target == 3_000_000


# ===================================================================
# TestCalculateTargetYear
# ===================================================================

class TestCalculateTargetYear:
    """Tests for calculate_target_year()."""

    def test_target_reached_exact(self):
        """Target exactly matched at a year boundary."""
        values = [100, 200, 300, 400, 500]
        result = calculate_target_year(values, 300)
        assert result == pytest.approx(2.0)

    def test_target_interpolated(self):
        """Target between two year values is interpolated."""
        values = [100, 200, 400]
        # target=300, between year 1 (200) and year 2 (400)
        # fraction = (300-200) / (400-200) = 0.5
        # year = 1 + 0.5 = 1.5
        result = calculate_target_year(values, 300)
        assert result == pytest.approx(1.5)

    def test_target_not_reached(self):
        """Target not reached returns None."""
        values = [100, 110, 120, 130]
        result = calculate_target_year(values, 500)
        assert result is None

    def test_target_already_reached(self):
        """Initial value >= target returns 0.0."""
        values = [500, 600, 700]
        result = calculate_target_year(values, 300)
        assert result == 0.0

    def test_empty_values(self):
        """Empty list returns None."""
        result = calculate_target_year([], 100)
        assert result is None

    def test_single_value_below(self):
        """Single value below target returns None."""
        result = calculate_target_year([50], 100)
        assert result is None

    def test_single_value_above(self):
        """Single value at or above target returns 0.0."""
        result = calculate_target_year([100], 100)
        assert result == 0.0

    def test_same_consecutive_values(self):
        """Equal consecutive values where target is matched."""
        values = [100, 200, 200]
        result = calculate_target_year(values, 200)
        # First reached at year 1
        assert result == pytest.approx(1.0)


# ===================================================================
# TestCalculateRequiredMonthly
# ===================================================================

class TestCalculateRequiredMonthly:
    """Tests for calculate_required_monthly()."""

    def test_basic_calculation(self):
        """Basic required monthly is positive."""
        monthly = calculate_required_monthly(
            current_value=1_000_000,
            return_rate=0.05,
            dividend_yield=0.02,
            target=5_000_000,
            years=10,
        )
        assert monthly > 0

    def test_already_sufficient(self):
        """No additional monthly needed when growth alone suffices."""
        monthly = calculate_required_monthly(
            current_value=1_000_000,
            return_rate=0.20,
            dividend_yield=0.05,
            target=1_000_000,
            years=10,
        )
        assert monthly == 0.0

    def test_zero_return_rate(self):
        """Zero return rate: monthly = gap / (years * 12)."""
        monthly = calculate_required_monthly(
            current_value=0,
            return_rate=0.0,
            dividend_yield=0.0,
            target=1_200_000,
            years=10,
        )
        assert monthly == pytest.approx(10_000)

    def test_high_target(self):
        """High target requires significant monthly contribution."""
        monthly = calculate_required_monthly(
            current_value=1_000_000,
            return_rate=0.05,
            dividend_yield=0.02,
            target=50_000_000,
            years=10,
        )
        assert monthly > 100_000

    def test_reinvest_dividends_off(self):
        """Without reinvesting dividends, effective rate excludes dividend_yield."""
        monthly_on = calculate_required_monthly(
            current_value=1_000_000,
            return_rate=0.05,
            dividend_yield=0.03,
            target=5_000_000,
            years=10,
            reinvest_dividends=True,
        )
        monthly_off = calculate_required_monthly(
            current_value=1_000_000,
            return_rate=0.05,
            dividend_yield=0.03,
            target=5_000_000,
            years=10,
            reinvest_dividends=False,
        )
        # Need more monthly when not reinvesting dividends
        assert monthly_off > monthly_on


# ===================================================================
# TestDividendEffect
# ===================================================================

class TestDividendEffect:
    """Tests for _calculate_dividend_effect()."""

    def test_positive_effect(self):
        """Positive dividend yield produces positive effect."""
        effect, pct = _calculate_dividend_effect(
            current_value=1_000_000,
            base_return=0.10,
            dividend_yield=0.03,
            years=10,
            monthly_add=0.0,
        )
        assert effect > 0
        assert pct > 0

    def test_zero_dividend(self):
        """Zero dividend yield produces zero effect."""
        effect, pct = _calculate_dividend_effect(
            current_value=1_000_000,
            base_return=0.10,
            dividend_yield=0.0,
            years=10,
            monthly_add=0.0,
        )
        assert effect == 0.0
        assert pct == 0.0

    def test_zero_years(self):
        """Zero years produces zero effect."""
        effect, pct = _calculate_dividend_effect(
            current_value=1_000_000,
            base_return=0.10,
            dividend_yield=0.03,
            years=0,
            monthly_add=0.0,
        )
        assert effect == 0.0
        assert pct == 0.0

    def test_with_monthly_add(self):
        """Monthly additions amplify dividend effect."""
        effect_no_add, _ = _calculate_dividend_effect(
            current_value=1_000_000,
            base_return=0.10,
            dividend_yield=0.03,
            years=10,
            monthly_add=0.0,
        )
        effect_with_add, _ = _calculate_dividend_effect(
            current_value=1_000_000,
            base_return=0.10,
            dividend_yield=0.03,
            years=10,
            monthly_add=100_000,
        )
        assert effect_with_add > effect_no_add


# ===================================================================
# TestSimulationResultToDict
# ===================================================================

class TestSimulationResultToDict:
    """Tests for SimulationResult.to_dict() and related methods."""

    def test_simulation_result_to_dict(self):
        """to_dict() produces correct structure."""
        snap = YearlySnapshot(year=0, value=1_000_000,
                              cumulative_input=1_000_000,
                              capital_gain=0.0, cumulative_dividends=0.0)
        result = SimulationResult(
            scenarios={"base": [snap]},
            target=2_000_000,
            target_year_base=5.5,
            target_year_optimistic=3.2,
            target_year_pessimistic=None,
            required_monthly=None,
            dividend_effect=50_000,
            dividend_effect_pct=0.05,
            years=10,
            monthly_add=50_000,
            reinvest_dividends=True,
            current_value=1_000_000,
            portfolio_return_base=0.10,
            dividend_yield=0.025,
        )
        d = result.to_dict()
        assert d["target"] == 2_000_000
        assert d["target_year_base"] == 5.5
        assert d["target_year_optimistic"] == 3.2
        assert d["target_year_pessimistic"] is None
        assert d["required_monthly"] is None
        assert d["dividend_effect"] == 50_000
        assert d["dividend_effect_pct"] == 0.05
        assert d["years"] == 10
        assert d["monthly_add"] == 50_000
        assert d["reinvest_dividends"] is True
        assert d["current_value"] == 1_000_000
        assert d["portfolio_return_base"] == 0.10
        assert d["dividend_yield"] == 0.025
        # Scenario dict
        assert "base" in d["scenarios"]
        assert len(d["scenarios"]["base"]) == 1
        assert d["scenarios"]["base"][0]["year"] == 0
        assert d["scenarios"]["base"][0]["value"] == 1_000_000

    def test_yearly_snapshot_to_dict(self):
        """YearlySnapshot.to_dict() produces all fields."""
        snap = YearlySnapshot(
            year=3,
            value=1_500_000,
            cumulative_input=1_200_000,
            capital_gain=250_000,
            cumulative_dividends=50_000,
        )
        d = snap.to_dict()
        assert d == {
            "year": 3,
            "value": 1_500_000,
            "cumulative_input": 1_200_000,
            "capital_gain": 250_000,
            "cumulative_dividends": 50_000,
        }

    def test_simulation_result_empty(self):
        """SimulationResult.empty() produces valid empty result."""
        result = SimulationResult.empty()
        assert result.scenarios == {}
        assert result.target is None
        assert result.target_year_base is None
        assert result.target_year_optimistic is None
        assert result.target_year_pessimistic is None
        assert result.required_monthly is None
        assert result.dividend_effect == 0.0
        assert result.dividend_effect_pct == 0.0
        d = result.to_dict()
        assert d["scenarios"] == {}
