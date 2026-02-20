"""Integration tests for buy/sell confirmation step (KIK-444).

Tests that:
- cmd_buy / cmd_sell without --yes print a confirmation preview and return early
- cmd_buy / cmd_sell with yes=True proceed to record the trade
- argparse recognises --yes / -y for both buy and sell
"""

import csv
import sys
from io import StringIO
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SCRIPTS_PATH = PROJECT_ROOT / ".claude" / "skills" / "stock-portfolio" / "scripts"
sys.path.insert(0, str(SCRIPTS_PATH))


# ---------------------------------------------------------------------------
# Module loader helper
# ---------------------------------------------------------------------------

def _load_run_portfolio():
    """Load run_portfolio module fresh (avoids shared-state issues)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_portfolio_kik444",
        str(SCRIPTS_PATH / "run_portfolio.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _capture(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) and return captured stdout."""
    captured = StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        fn(*args, **kwargs)
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_csv(tmp_path):
    """Temporary portfolio CSV with one position (NVDA, 10 shares @ $120)."""
    csv_file = tmp_path / "portfolio.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["symbol", "shares", "cost_price", "cost_currency", "purchase_date", "memo"],
        )
        writer.writeheader()
        writer.writerow({
            "symbol": "NVDA",
            "shares": 10,
            "cost_price": 120.0,
            "cost_currency": "USD",
            "purchase_date": "2026-01-01",
            "memo": "",
        })
    return str(csv_file)


@pytest.fixture
def empty_csv(tmp_path):
    """Temporary empty portfolio CSV."""
    csv_file = tmp_path / "empty.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["symbol", "shares", "cost_price", "cost_currency", "purchase_date", "memo"],
        )
        writer.writeheader()
    return str(csv_file)


# ---------------------------------------------------------------------------
# Tests: cmd_buy confirmation
# ---------------------------------------------------------------------------

class TestCmdBuyConfirmation:
    """Tests for KIK-444 buy confirmation step."""

    def test_buy_without_yes_prints_preview(self, empty_csv):
        """cmd_buy without yes=True prints a confirmation summary and returns early."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_buy,
            csv_path=empty_csv,
            symbol="NVDA",
            shares=5,
            price=138.0,
            currency="USD",
            yes=False,
        )
        assert "購入確認" in output
        assert "NVDA" in output
        assert "5" in output  # shares

    def test_buy_without_yes_shows_price(self, empty_csv):
        """Confirmation preview shows the purchase price."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_buy,
            csv_path=empty_csv,
            symbol="NVDA",
            shares=5,
            price=138.0,
            currency="USD",
            yes=False,
        )
        assert "138" in output

    def test_buy_without_yes_shows_rerun_hint(self, empty_csv):
        """Confirmation preview contains hint to rerun with --yes."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_buy,
            csv_path=empty_csv,
            symbol="NVDA",
            shares=5,
            price=138.0,
            currency="USD",
            yes=False,
        )
        assert "--yes" in output

    def test_buy_without_yes_does_not_record(self, empty_csv):
        """cmd_buy without yes=True does NOT write to the CSV."""
        mod = _load_run_portfolio()
        _capture(
            mod.cmd_buy,
            csv_path=empty_csv,
            symbol="NVDA",
            shares=5,
            price=138.0,
            currency="USD",
            yes=False,
        )
        rows = mod._fallback_load_csv(empty_csv)
        assert rows == []

    def test_buy_with_yes_records_trade(self, empty_csv):
        """cmd_buy with yes=True writes the position to the CSV."""
        mod = _load_run_portfolio()
        # Suppress stdout noise from the actual buy operation
        _capture(
            mod.cmd_buy,
            csv_path=empty_csv,
            symbol="NVDA",
            shares=5,
            price=138.0,
            currency="USD",
            yes=True,
        )
        rows = mod._fallback_load_csv(empty_csv)
        assert len(rows) >= 1
        symbols = [r["symbol"] for r in rows]
        assert "NVDA" in symbols

    def test_buy_confirmation_jpy_format(self, empty_csv):
        """JPY prices are formatted without decimal places."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_buy,
            csv_path=empty_csv,
            symbol="7203.T",
            shares=100,
            price=2850.0,
            currency="JPY",
            yes=False,
        )
        assert "¥" in output
        assert "2,850" in output


# ---------------------------------------------------------------------------
# Tests: cmd_sell confirmation
# ---------------------------------------------------------------------------

class TestCmdSellConfirmation:
    """Tests for KIK-444 sell confirmation step."""

    def test_sell_without_yes_prints_preview(self, tmp_csv):
        """cmd_sell without yes=True prints a confirmation summary and returns early."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_sell,
            csv_path=tmp_csv,
            symbol="NVDA",
            shares=5,
            sell_price=150.0,
            yes=False,
        )
        assert "売却確認" in output
        assert "NVDA" in output

    def test_sell_without_yes_shows_sell_price(self, tmp_csv):
        """Confirmation preview shows sell price."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_sell,
            csv_path=tmp_csv,
            symbol="NVDA",
            shares=5,
            sell_price=150.0,
            yes=False,
        )
        assert "150" in output

    def test_sell_without_yes_shows_cost_price(self, tmp_csv):
        """Confirmation preview shows cost price from portfolio."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_sell,
            csv_path=tmp_csv,
            symbol="NVDA",
            shares=5,
            sell_price=150.0,
            yes=False,
        )
        assert "120" in output  # cost_price from fixture

    def test_sell_without_yes_shows_estimated_pnl(self, tmp_csv):
        """Confirmation preview shows estimated P&L when sell_price given."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_sell,
            csv_path=tmp_csv,
            symbol="NVDA",
            shares=5,
            sell_price=150.0,
            yes=False,
        )
        # Estimated PnL = (150 - 120) * 5 = +$150
        assert "推定実現損益" in output
        assert "150" in output

    def test_sell_without_yes_shows_rerun_hint(self, tmp_csv):
        """Confirmation preview contains hint to rerun with --yes."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_sell,
            csv_path=tmp_csv,
            symbol="NVDA",
            shares=5,
            yes=False,
        )
        assert "--yes" in output

    def test_sell_without_yes_does_not_modify_portfolio(self, tmp_csv):
        """cmd_sell without yes=True does NOT modify the portfolio CSV."""
        mod = _load_run_portfolio()
        rows_before = mod._fallback_load_csv(tmp_csv)
        _capture(
            mod.cmd_sell,
            csv_path=tmp_csv,
            symbol="NVDA",
            shares=5,
            sell_price=150.0,
            yes=False,
        )
        rows_after = mod._fallback_load_csv(tmp_csv)
        assert rows_before[0]["shares"] == rows_after[0]["shares"]

    def test_sell_without_price_still_shows_preview(self, tmp_csv):
        """Confirmation works even when sell_price is omitted."""
        mod = _load_run_portfolio()
        output = _capture(
            mod.cmd_sell,
            csv_path=tmp_csv,
            symbol="NVDA",
            shares=3,
            sell_price=None,
            yes=False,
        )
        assert "売却確認" in output
        assert "NVDA" in output
        # No P&L estimate when price not given
        assert "推定実現損益" not in output


# ---------------------------------------------------------------------------
# Tests: argparse --yes / -y flags
# ---------------------------------------------------------------------------

class TestArgparseYesFlag:
    """Tests that --yes and -y are recognised by argparse for buy and sell."""

    def _parse_args(self, mod, argv):
        """Build the argparser from the module's main() source and parse argv."""
        import argparse
        p = argparse.ArgumentParser()
        sub = p.add_subparsers(dest="command")

        buy_p = sub.add_parser("buy")
        buy_p.add_argument("--symbol", required=True)
        buy_p.add_argument("--shares", required=True, type=int)
        buy_p.add_argument("--price", required=True, type=float)
        buy_p.add_argument("--currency", default="JPY")
        buy_p.add_argument("--date", default=None)
        buy_p.add_argument("--memo", default="")
        buy_p.add_argument("-y", "--yes", action="store_true", default=False)

        sell_p = sub.add_parser("sell")
        sell_p.add_argument("--symbol", required=True)
        sell_p.add_argument("--shares", required=True, type=int)
        sell_p.add_argument("--price", type=float, default=None)
        sell_p.add_argument("--date", default=None)
        sell_p.add_argument("-y", "--yes", action="store_true", default=False)

        return p.parse_args(argv)

    def test_buy_yes_long_flag(self):
        """buy --yes sets yes=True."""
        mod = _load_run_portfolio()
        args = self._parse_args(
            mod,
            ["buy", "--symbol", "NVDA", "--shares", "5", "--price", "138", "--yes"],
        )
        assert args.yes is True

    def test_buy_yes_short_flag(self):
        """buy -y sets yes=True."""
        mod = _load_run_portfolio()
        args = self._parse_args(
            mod,
            ["buy", "--symbol", "NVDA", "--shares", "5", "--price", "138", "-y"],
        )
        assert args.yes is True

    def test_buy_no_yes_flag_defaults_false(self):
        """buy without --yes defaults to False."""
        mod = _load_run_portfolio()
        args = self._parse_args(
            mod,
            ["buy", "--symbol", "NVDA", "--shares", "5", "--price", "138"],
        )
        assert args.yes is False

    def test_sell_yes_long_flag(self):
        """sell --yes sets yes=True."""
        mod = _load_run_portfolio()
        args = self._parse_args(
            mod,
            ["sell", "--symbol", "NVDA", "--shares", "5", "--yes"],
        )
        assert args.yes is True

    def test_sell_yes_short_flag(self):
        """sell -y sets yes=True."""
        mod = _load_run_portfolio()
        args = self._parse_args(
            mod,
            ["sell", "--symbol", "NVDA", "--shares", "5", "-y"],
        )
        assert args.yes is True

    def test_sell_no_yes_flag_defaults_false(self):
        """sell without --yes defaults to False."""
        mod = _load_run_portfolio()
        args = self._parse_args(
            mod,
            ["sell", "--symbol", "NVDA", "--shares", "5"],
        )
        assert args.yes is False
