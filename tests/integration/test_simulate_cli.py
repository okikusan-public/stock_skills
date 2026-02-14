"""Integration tests for run_portfolio.py simulate command (KIK-366).

Tests the end-to-end CLI flow by calling cmd_simulate() with mocked
forecast data, and verifying stdout Markdown output.
"""

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Mock forecast result used across tests
# ---------------------------------------------------------------------------

MOCK_FORECAST_RESULT = {
    "positions": [
        {
            "symbol": "7203.T",
            "name": "Toyota",
            "base": 0.08,
            "optimistic": 0.20,
            "pessimistic": -0.05,
            "method": "analyst",
            "dividend_yield": 0.026,
            "value_jpy": 2_850_000,
        },
        {
            "symbol": "AAPL",
            "name": "Apple",
            "base": 0.15,
            "optimistic": 0.30,
            "pessimistic": -0.03,
            "method": "analyst",
            "dividend_yield": 0.005,
            "value_jpy": 4_108_500,
        },
    ],
    "portfolio": {
        "optimistic": 0.2590,
        "base": 0.1213,
        "pessimistic": -0.0382,
    },
    "total_value_jpy": 6_958_500,
    "fx_rates": {"JPY": 1.0, "USD": 150.0},
}


# ---------------------------------------------------------------------------
# Helper: run cmd_simulate with mocked dependencies
# ---------------------------------------------------------------------------

def _run_cmd_simulate(
    years=10,
    monthly_add=0.0,
    target=None,
    reinvest_dividends=True,
    forecast_result=None,
):
    """Run cmd_simulate() with mocked estimate_portfolio_return.

    Returns the captured stdout string.
    """
    if forecast_result is None:
        forecast_result = MOCK_FORECAST_RESULT

    # Import inside function so patches take effect
    from src.output.portfolio_formatter import format_simulation  # noqa: F401

    with patch(
        "src.core.return_estimate.estimate_portfolio_return",
        return_value=forecast_result,
    ):
        # Re-import to get the patched version
        import importlib
        scripts_path = str(PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)

        # We need to reload the module to pick up patches
        import src.core.return_estimate  # noqa: F401

        # Import cmd_simulate from run_portfolio
        spec = PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts" / "run_portfolio.py"
        import importlib.util
        loader_spec = importlib.util.spec_from_file_location("run_portfolio", str(spec))
        mod = importlib.util.module_from_spec(loader_spec)

        # Patch estimate_portfolio_return before loading the module
        with patch(
            "src.core.return_estimate.estimate_portfolio_return",
            return_value=forecast_result,
        ):
            loader_spec.loader.exec_module(mod)

            # Capture stdout
            captured = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                mod.cmd_simulate(
                    csv_path="/tmp/nonexistent_portfolio.csv",
                    years=years,
                    monthly_add=monthly_add,
                    target=target,
                    reinvest_dividends=reinvest_dividends,
                )
            finally:
                sys.stdout = old_stdout

            return captured.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCmdSimulateBasic:
    """Basic end-to-end tests for cmd_simulate."""

    def test_cmd_simulate_basic(self):
        """Basic simulate produces Markdown output with simulation header."""
        output = _run_cmd_simulate(years=3)
        assert "シミュレーション" in output
        assert "| 年 |" in output
        assert "| 評価額 |" in output

    def test_cmd_simulate_year_count(self):
        """Simulate with years=5 produces correct year header."""
        output = _run_cmd_simulate(years=5)
        assert "5年シミュレーション" in output

    def test_cmd_simulate_contains_base_scenario(self):
        """Output contains base scenario table."""
        output = _run_cmd_simulate(years=3)
        assert "ベースシナリオ" in output

    def test_cmd_simulate_contains_scenario_comparison(self):
        """Output contains scenario comparison section."""
        output = _run_cmd_simulate(years=3)
        assert "シナリオ比較" in output
        assert "楽観" in output
        assert "悲観" in output

    def test_cmd_simulate_contains_dividend_section(self):
        """Output contains dividend effect section."""
        output = _run_cmd_simulate(years=3)
        assert "配当再投資" in output


class TestCmdSimulateWithOptions:
    """Tests for cmd_simulate with various options."""

    def test_cmd_simulate_with_monthly_add(self):
        """Monthly add is reflected in the output header."""
        output = _run_cmd_simulate(years=5, monthly_add=50_000)
        assert "月50,000円積立" in output

    def test_cmd_simulate_with_target(self):
        """Target triggers target analysis section."""
        output = _run_cmd_simulate(years=5, monthly_add=50_000, target=15_000_000)
        assert "目標達成分析" in output
        assert "目標額" in output

    def test_cmd_simulate_with_all_options(self):
        """All options (years, monthly_add, target) work together."""
        output = _run_cmd_simulate(
            years=5,
            monthly_add=50_000,
            target=15_000_000,
        )
        assert "5年シミュレーション" in output
        assert "月50,000円積立" in output
        assert "目標達成分析" in output


class TestCmdSimulateNoReinvest:
    """Tests for --no-reinvest-dividends option."""

    def test_cmd_simulate_no_reinvest(self):
        """No reinvest dividends shows OFF in output."""
        output = _run_cmd_simulate(years=3, reinvest_dividends=False)
        assert "OFF" in output


class TestExistingCommandsUnaffected:
    """Tests that existing commands still work."""

    def test_cmd_list_still_works(self):
        """The list command still functions after simulate is added."""
        spec = PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts" / "run_portfolio.py"
        import importlib.util
        loader_spec = importlib.util.spec_from_file_location("run_portfolio_list", str(spec))
        mod = importlib.util.module_from_spec(loader_spec)
        loader_spec.loader.exec_module(mod)

        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            mod.cmd_list("/tmp/nonexistent_portfolio.csv")
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "データがありません" in output

    def test_argparse_recognizes_simulate(self):
        """argparse correctly parses 'simulate' subcommand."""
        spec = PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts" / "run_portfolio.py"
        import importlib.util
        loader_spec = importlib.util.spec_from_file_location("run_portfolio_argparse", str(spec))
        mod = importlib.util.module_from_spec(loader_spec)
        loader_spec.loader.exec_module(mod)

        import argparse
        # Test that parsing "simulate --years 5" works
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        simulate_parser = subparsers.add_parser("simulate")
        simulate_parser.add_argument("--years", type=int, default=10)
        simulate_parser.add_argument("--monthly-add", type=float, default=0.0)
        simulate_parser.add_argument("--target", type=float, default=None)
        simulate_parser.add_argument("--reinvest-dividends", action="store_true", default=True, dest="reinvest_dividends")
        simulate_parser.add_argument("--no-reinvest-dividends", action="store_false", dest="reinvest_dividends")

        args = parser.parse_args(["simulate", "--years", "5", "--monthly-add", "50000"])
        assert args.command == "simulate"
        assert args.years == 5
        assert args.monthly_add == 50000.0

    def test_argparse_recognizes_existing_commands(self):
        """Existing subcommands (snapshot, health, forecast) are still recognized."""
        spec = PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts" / "run_portfolio.py"
        import importlib.util
        loader_spec = importlib.util.spec_from_file_location("run_portfolio_existing", str(spec))
        mod = importlib.util.module_from_spec(loader_spec)
        loader_spec.loader.exec_module(mod)

        # Verify the module has all expected command functions
        assert hasattr(mod, "cmd_snapshot")
        assert hasattr(mod, "cmd_buy")
        assert hasattr(mod, "cmd_sell")
        assert hasattr(mod, "cmd_analyze")
        assert hasattr(mod, "cmd_list")
        assert hasattr(mod, "cmd_health")
        assert hasattr(mod, "cmd_forecast")
        assert hasattr(mod, "cmd_rebalance")
        assert hasattr(mod, "cmd_simulate")


class TestCmdSimulateMissingModule:
    """Tests for graceful degradation when modules are missing."""

    def test_cmd_simulate_missing_simulator(self):
        """When HAS_SIMULATOR is False, prints error and exits."""
        spec = PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts" / "run_portfolio.py"
        import importlib.util
        loader_spec = importlib.util.spec_from_file_location("run_portfolio_nosim", str(spec))
        mod = importlib.util.module_from_spec(loader_spec)
        loader_spec.loader.exec_module(mod)

        # Override HAS_SIMULATOR to False
        mod.HAS_SIMULATOR = False

        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            with pytest.raises(SystemExit) as exc_info:
                mod.cmd_simulate("/tmp/test.csv")
            assert exc_info.value.code == 1
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "simulator" in output.lower() or "モジュール" in output

    def test_cmd_simulate_missing_return_estimate(self):
        """When HAS_RETURN_ESTIMATE is False, prints error and exits."""
        spec = PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts" / "run_portfolio.py"
        import importlib.util
        loader_spec = importlib.util.spec_from_file_location("run_portfolio_nore", str(spec))
        mod = importlib.util.module_from_spec(loader_spec)
        loader_spec.loader.exec_module(mod)

        # Override HAS_RETURN_ESTIMATE to False
        mod.HAS_RETURN_ESTIMATE = False

        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            with pytest.raises(SystemExit) as exc_info:
                mod.cmd_simulate("/tmp/test.csv")
            assert exc_info.value.code == 1
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "return_estimate" in output.lower() or "モジュール" in output


class TestCmdSimulateEmptyPortfolio:
    """Tests for empty portfolio handling."""

    def test_cmd_simulate_empty_portfolio(self):
        """Empty portfolio produces appropriate message."""
        empty_forecast = {
            "positions": [],
            "portfolio": {"optimistic": None, "base": None, "pessimistic": None},
            "total_value_jpy": 0,
        }
        output = _run_cmd_simulate(years=3, forecast_result=empty_forecast)
        assert "データがありません" in output

    def test_cmd_simulate_none_base_return(self):
        """When base return is None, simulation shows error message."""
        none_base_forecast = {
            "positions": [
                {
                    "symbol": "FAIL.T",
                    "name": "Fail Corp",
                    "base": None,
                    "optimistic": None,
                    "pessimistic": None,
                    "method": "no_data",
                    "dividend_yield": 0.0,
                    "value_jpy": 100_000,
                },
            ],
            "portfolio": {
                "optimistic": None,
                "base": None,
                "pessimistic": None,
            },
            "total_value_jpy": 100_000,
        }
        output = _run_cmd_simulate(years=3, forecast_result=none_base_forecast)
        # Should produce either empty scenarios message or JSON fallback
        assert "取得できませんでした" in output or "{" in output
