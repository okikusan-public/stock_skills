"""Tests for format_simulation in portfolio_formatter.py (KIK-366)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.models import SimulationResult, YearlySnapshot
from src.output.portfolio_formatter import format_simulation


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

def _make_snapshots(values, cumulative_inputs, capital_gains, cumulative_dividends):
    """Helper to build a list of YearlySnapshot from parallel lists."""
    snapshots = []
    for i, (v, ci, cg, cd) in enumerate(
        zip(values, cumulative_inputs, capital_gains, cumulative_dividends)
    ):
        snapshots.append(YearlySnapshot(
            year=i,
            value=v,
            cumulative_input=ci,
            capital_gain=cg,
            cumulative_dividends=cd,
        ))
    return snapshots


@pytest.fixture
def basic_result():
    """A basic 3-year simulation result with all 3 scenarios."""
    base_snapshots = _make_snapshots(
        values=[5_000_000, 5_700_000, 6_498_000, 7_407_720],
        cumulative_inputs=[5_000_000, 5_000_000, 5_000_000, 5_000_000],
        capital_gains=[0, 570_000, 1_238_000, 2_017_720],
        cumulative_dividends=[0, 130_000, 278_100, 446_106],
    )
    opt_snapshots = _make_snapshots(
        values=[5_000_000, 6_500_000, 8_450_000, 10_985_000],
        cumulative_inputs=[5_000_000, 5_000_000, 5_000_000, 5_000_000],
        capital_gains=[0, 1_300_000, 3_060_000, 5_405_000],
        cumulative_dividends=[0, 130_000, 299_000, 518_700],
    )
    pess_snapshots = _make_snapshots(
        values=[5_000_000, 4_600_000, 4_232_000, 3_893_440],
        cumulative_inputs=[5_000_000, 5_000_000, 5_000_000, 5_000_000],
        capital_gains=[0, -530_000, -1_028_000, -1_496_560],
        cumulative_dividends=[0, 130_000, 249_600, 359_432],
    )
    return SimulationResult(
        scenarios={
            "optimistic": opt_snapshots,
            "base": base_snapshots,
            "pessimistic": pess_snapshots,
        },
        target=None,
        target_year_base=None,
        target_year_optimistic=None,
        target_year_pessimistic=None,
        required_monthly=None,
        dividend_effect=500_000,
        dividend_effect_pct=0.073,
        years=3,
        monthly_add=0.0,
        reinvest_dividends=True,
        current_value=5_000_000,
        portfolio_return_base=0.12,
        dividend_yield=0.026,
    )


@pytest.fixture
def target_reached_result():
    """Simulation where base scenario reaches target at ~2.5 years."""
    base_snapshots = _make_snapshots(
        values=[5_000_000, 6_300_000, 7_938_000, 9_981_540],
        cumulative_inputs=[5_000_000, 5_600_000, 6_200_000, 6_800_000],
        capital_gains=[0, 570_000, 1_478_000, 2_721_540],
        cumulative_dividends=[0, 130_000, 293_800, 500_288],
    )
    return SimulationResult(
        scenarios={"base": base_snapshots},
        target=7_500_000,
        target_year_base=1.8,
        target_year_optimistic=None,
        target_year_pessimistic=None,
        required_monthly=None,
        dividend_effect=300_000,
        dividend_effect_pct=0.05,
        years=3,
        monthly_add=50_000,
        reinvest_dividends=True,
        current_value=5_000_000,
        portfolio_return_base=0.12,
        dividend_yield=0.026,
    )


@pytest.fixture
def target_not_reached_result():
    """Simulation where target is not reached by base scenario."""
    base_snapshots = _make_snapshots(
        values=[5_000_000, 5_700_000, 6_498_000, 7_407_720],
        cumulative_inputs=[5_000_000, 5_000_000, 5_000_000, 5_000_000],
        capital_gains=[0, 570_000, 1_238_000, 2_017_720],
        cumulative_dividends=[0, 130_000, 278_100, 446_106],
    )
    return SimulationResult(
        scenarios={"base": base_snapshots},
        target=15_000_000,
        target_year_base=None,
        target_year_optimistic=None,
        target_year_pessimistic=None,
        required_monthly=83_000,
        dividend_effect=300_000,
        dividend_effect_pct=0.05,
        years=3,
        monthly_add=0.0,
        reinvest_dividends=True,
        current_value=5_000_000,
        portfolio_return_base=0.12,
        dividend_yield=0.026,
    )


@pytest.fixture
def no_reinvest_result():
    """Simulation with reinvest_dividends=False."""
    base_snapshots = _make_snapshots(
        values=[5_000_000, 5_600_000, 6_272_000, 7_024_640],
        cumulative_inputs=[5_000_000, 5_000_000, 5_000_000, 5_000_000],
        capital_gains=[0, 600_000, 1_272_000, 2_024_640],
        cumulative_dividends=[0, 130_000, 275_600, 438_752],
    )
    return SimulationResult(
        scenarios={"base": base_snapshots},
        target=None,
        target_year_base=None,
        target_year_optimistic=None,
        target_year_pessimistic=None,
        required_monthly=None,
        dividend_effect=0,
        dividend_effect_pct=0,
        years=3,
        monthly_add=0.0,
        reinvest_dividends=False,
        current_value=5_000_000,
        portfolio_return_base=0.12,
        dividend_yield=0.026,
    )


@pytest.fixture
def monthly_add_result():
    """Simulation with monthly_add > 0."""
    base_snapshots = _make_snapshots(
        values=[5_000_000, 6_360_000, 7_923_200, 9_714_784],
        cumulative_inputs=[5_000_000, 5_600_000, 6_200_000, 6_800_000],
        capital_gains=[0, 630_000, 1_445_100, 2_468_678],
        cumulative_dividends=[0, 130_000, 295_360, 506_106],
    )
    return SimulationResult(
        scenarios={"base": base_snapshots},
        target=None,
        target_year_base=None,
        target_year_optimistic=None,
        target_year_pessimistic=None,
        required_monthly=None,
        dividend_effect=400_000,
        dividend_effect_pct=0.06,
        years=3,
        monthly_add=50_000,
        reinvest_dividends=True,
        current_value=5_000_000,
        portfolio_return_base=0.12,
        dividend_yield=0.026,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFormatSimulationBasic:
    """Tests for basic format_simulation() output."""

    def test_format_simulation_basic(self, basic_result):
        """Basic simulation contains table headers and correct row count."""
        output = format_simulation(basic_result)

        # Header
        assert "3年シミュレーション" in output
        assert "積立なし" in output

        # Table headers
        assert "| 年 |" in output
        assert "| 評価額 |" in output
        assert "| 累計投入 |" in output
        assert "| 運用益 |" in output
        assert "| 配当累計 |" in output

        # Should have year 0-3 rows (4 rows in the table)
        # Count occurrences of "| 0 |", "| 1 |", "| 2 |", "| 3 |"
        assert "| 0 |" in output
        assert "| 1 |" in output
        assert "| 2 |" in output
        assert "| 3 |" in output

    def test_format_simulation_contains_scenario_comparison(self, basic_result):
        """Simulation with 3 scenarios includes comparison table."""
        output = format_simulation(basic_result)
        assert "シナリオ比較" in output
        assert "楽観" in output
        assert "ベース" in output
        assert "悲観" in output

    def test_format_simulation_contains_base_return_rate(self, basic_result):
        """Base scenario section shows the annual return rate."""
        output = format_simulation(basic_result)
        assert "ベースシナリオ" in output
        assert "+12.00%" in output

    def test_format_simulation_contains_dividend_section(self, basic_result):
        """Simulation includes dividend reinvestment effect section."""
        output = format_simulation(basic_result)
        assert "配当再投資の効果" in output
        assert "複利効果" in output


class TestFormatSimulationKNotation:
    """Tests for K-notation (thousands) formatting."""

    def test_format_simulation_k_notation(self, basic_result):
        """Values are displayed in K (thousands) notation."""
        output = format_simulation(basic_result)
        # 5,000,000 -> 5,000K
        assert "5,000K" in output

    def test_format_simulation_k_values_have_yen_prefix(self, basic_result):
        """K-notation values have the yen prefix."""
        output = format_simulation(basic_result)
        # Should contain values like \u00a55,000K
        assert "\u00a55,000K" in output

    def test_format_simulation_year_zero_dash_for_gains(self, basic_result):
        """Year 0 row shows '-' for capital gain and dividends."""
        output = format_simulation(basic_result)
        lines = output.split("\n")
        year_zero_lines = [l for l in lines if "| 0 |" in l]
        assert len(year_zero_lines) >= 1
        # Year 0 should have "-" for gain and dividends columns
        assert year_zero_lines[0].count("- |") >= 2


class TestFormatSimulationWithTarget:
    """Tests for target-reached simulation output."""

    def test_format_simulation_with_target(self, target_reached_result):
        """Target reached shows target analysis section."""
        output = format_simulation(target_reached_result)
        assert "目標達成分析" in output
        assert "目標額" in output
        assert "達成見込み" in output
        # target_year_base = 1.8
        assert "1.8年" in output

    def test_format_simulation_target_amount_in_k(self, target_reached_result):
        """Target amount is displayed in K notation."""
        output = format_simulation(target_reached_result)
        # 7,500,000 -> 7,500K
        assert "7,500K" in output

    def test_format_simulation_monthly_add_header(self, target_reached_result):
        """Header shows monthly add amount."""
        output = format_simulation(target_reached_result)
        assert "月50,000円積立" in output


class TestFormatSimulationTargetNotReached:
    """Tests for target-not-reached simulation output."""

    def test_format_simulation_target_not_reached(self, target_not_reached_result):
        """Target not reached shows '期間内未達' and required monthly."""
        output = format_simulation(target_not_reached_result)
        assert "目標達成分析" in output
        assert "期間内未達" in output

    def test_format_simulation_required_monthly(self, target_not_reached_result):
        """Required monthly contribution is displayed."""
        output = format_simulation(target_not_reached_result)
        assert "必要な月額積立" in output
        # 83,000
        assert "83,000" in output


class TestFormatSimulationNoReinvest:
    """Tests for no-reinvest simulation output."""

    def test_format_simulation_no_reinvest(self, no_reinvest_result):
        """No reinvest simulation shows 'OFF' for dividend reinvestment."""
        output = format_simulation(no_reinvest_result)
        assert "配当再投資" in output
        assert "OFF" in output


class TestFormatSimulationWithMonthlyAdd:
    """Tests for monthly-add simulation output."""

    def test_format_simulation_with_monthly_add(self, monthly_add_result):
        """Monthly add simulation shows add amount in header."""
        output = format_simulation(monthly_add_result)
        assert "月50,000円積立" in output


class TestFormatSimulationEmptyScenarios:
    """Tests for empty simulation result."""

    def test_format_simulation_empty(self):
        """Empty SimulationResult shows error message."""
        result = SimulationResult.empty()
        output = format_simulation(result)
        assert "シミュレーション" in output
        assert "取得できませんでした" in output

    def test_format_simulation_empty_dict(self):
        """Empty dict input also shows error message."""
        d = {
            "scenarios": {},
            "years": 0,
            "monthly_add": 0,
            "reinvest_dividends": True,
            "target": None,
            "dividend_effect": 0,
            "dividend_effect_pct": 0,
        }
        output = format_simulation(d)
        assert "取得できませんでした" in output


class TestFormatSimulationDictInput:
    """Tests that format_simulation handles dict input (to_dict() output)."""

    def test_format_simulation_dict_input(self, basic_result):
        """format_simulation works with dict input via to_dict()."""
        d = basic_result.to_dict()
        output = format_simulation(d)
        assert "3年シミュレーション" in output
        assert "| 年 |" in output
        assert "5,000K" in output
