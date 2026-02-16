"""Tests for src.core.portfolio.portfolio_manager module."""

import os

import pytest

from src.core.portfolio.portfolio_manager import (
    load_portfolio,
    save_portfolio,
    add_position,
    sell_position,
    CSV_COLUMNS,
    _infer_country,
    _infer_currency,
    _is_cash,
    _cash_currency,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def csv_path(tmp_path):
    """Return a temporary CSV file path for testing."""
    return str(tmp_path / "test_portfolio.csv")


@pytest.fixture
def sample_portfolio():
    """Return a sample portfolio list."""
    return [
        {
            "symbol": "7203.T",
            "shares": 100,
            "cost_price": 2850.0,
            "cost_currency": "JPY",
            "purchase_date": "2025-01-15",
            "memo": "Toyota",
        },
        {
            "symbol": "AAPL",
            "shares": 10,
            "cost_price": 175.50,
            "cost_currency": "USD",
            "purchase_date": "2025-02-01",
            "memo": "Apple",
        },
    ]


# ===================================================================
# load_portfolio
# ===================================================================


class TestLoadPortfolio:
    def test_file_not_exists_returns_empty(self, tmp_path):
        """Non-existent file should return empty list."""
        path = str(tmp_path / "nonexistent.csv")
        result = load_portfolio(path)
        assert result == []

    def test_load_valid_csv(self, csv_path, sample_portfolio):
        """Load a valid CSV and verify shares=int, cost_price=float."""
        save_portfolio(sample_portfolio, csv_path)
        loaded = load_portfolio(csv_path)

        assert len(loaded) == 2
        assert loaded[0]["symbol"] == "7203.T"
        assert loaded[0]["shares"] == 100
        assert isinstance(loaded[0]["shares"], int)
        assert loaded[0]["cost_price"] == 2850.0
        assert isinstance(loaded[0]["cost_price"], float)
        assert loaded[0]["cost_currency"] == "JPY"
        assert loaded[0]["purchase_date"] == "2025-01-15"
        assert loaded[0]["memo"] == "Toyota"

    def test_load_second_position(self, csv_path, sample_portfolio):
        """Verify the second position is also loaded correctly."""
        save_portfolio(sample_portfolio, csv_path)
        loaded = load_portfolio(csv_path)

        assert loaded[1]["symbol"] == "AAPL"
        assert loaded[1]["shares"] == 10
        assert loaded[1]["cost_price"] == 175.50

    def test_zero_shares_excluded(self, csv_path):
        """Rows with shares=0 should be excluded from loaded portfolio."""
        portfolio = [
            {"symbol": "SKIP", "shares": 0, "cost_price": 100.0,
             "cost_currency": "JPY", "purchase_date": "", "memo": ""},
            {"symbol": "KEEP", "shares": 5, "cost_price": 200.0,
             "cost_currency": "USD", "purchase_date": "", "memo": ""},
        ]
        save_portfolio(portfolio, csv_path)
        loaded = load_portfolio(csv_path)

        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "KEEP"

    def test_empty_symbol_excluded(self, csv_path):
        """Rows with empty symbol should be excluded."""
        portfolio = [
            {"symbol": "", "shares": 10, "cost_price": 100.0,
             "cost_currency": "JPY", "purchase_date": "", "memo": ""},
        ]
        save_portfolio(portfolio, csv_path)
        loaded = load_portfolio(csv_path)
        assert len(loaded) == 0


# ===================================================================
# save_portfolio
# ===================================================================


class TestSavePortfolio:
    def test_save_and_load_roundtrip(self, csv_path, sample_portfolio):
        """Save then load should produce matching data."""
        save_portfolio(sample_portfolio, csv_path)
        loaded = load_portfolio(csv_path)

        assert len(loaded) == len(sample_portfolio)
        for orig, loaded_row in zip(sample_portfolio, loaded):
            assert loaded_row["symbol"] == orig["symbol"]
            assert loaded_row["shares"] == orig["shares"]
            assert loaded_row["cost_price"] == orig["cost_price"]
            assert loaded_row["cost_currency"] == orig["cost_currency"]

    def test_creates_directory_if_needed(self, tmp_path):
        """save_portfolio should create parent directories."""
        deep_path = str(tmp_path / "a" / "b" / "c" / "portfolio.csv")
        save_portfolio([], deep_path)
        assert os.path.exists(deep_path)

    def test_save_empty_portfolio(self, csv_path):
        """Saving empty portfolio should create a CSV with only headers."""
        save_portfolio([], csv_path)
        loaded = load_portfolio(csv_path)
        assert loaded == []
        # File should exist
        assert os.path.exists(csv_path)

    def test_overwrite_existing_file(self, csv_path, sample_portfolio):
        """Saving again should overwrite the file."""
        save_portfolio(sample_portfolio, csv_path)
        # Now save a different portfolio
        new_portfolio = [
            {"symbol": "NEW", "shares": 50, "cost_price": 300.0,
             "cost_currency": "USD", "purchase_date": "2025-06-01", "memo": "new"},
        ]
        save_portfolio(new_portfolio, csv_path)
        loaded = load_portfolio(csv_path)
        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "NEW"


# ===================================================================
# add_position
# ===================================================================


class TestAddPosition:
    def test_add_new_position(self, csv_path):
        """Adding a new symbol should create a new row."""
        result = add_position(
            csv_path,
            symbol="7203.T",
            shares=100,
            cost_price=2850.0,
            cost_currency="JPY",
            purchase_date="2025-06-15",
            memo="Toyota",
        )

        assert result["symbol"] == "7203.T"
        assert result["shares"] == 100
        assert result["cost_price"] == 2850.0

        # Verify it was saved
        loaded = load_portfolio(csv_path)
        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "7203.T"

    def test_add_additional_purchase_average_price(self, csv_path):
        """Adding to existing position should recalculate average cost price."""
        # First purchase: 100 shares at 2800
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")

        # Second purchase: 50 shares at 3100
        result = add_position(csv_path, "7203.T", 50, 3100.0, "JPY", "2025-06-01")

        # Expected average: (100*2800 + 50*3100) / 150 = (280000+155000)/150 = 2900
        expected_avg = (100 * 2800.0 + 50 * 3100.0) / 150
        assert result["shares"] == 150
        assert result["cost_price"] == pytest.approx(round(expected_avg, 4))

    def test_add_to_existing_updates_date(self, csv_path):
        """Additional purchase should update purchase_date to the latest."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")
        result = add_position(csv_path, "7203.T", 50, 3100.0, "JPY", "2025-06-01")

        assert result["purchase_date"] == "2025-06-01"

    def test_add_to_existing_updates_memo(self, csv_path):
        """Additional purchase with new memo should update memo."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01", "first buy")
        result = add_position(csv_path, "7203.T", 50, 3100.0, "JPY", "2025-06-01", "averaged down")

        assert result["memo"] == "averaged down"

    def test_add_multiple_different_symbols(self, csv_path):
        """Adding different symbols should create separate rows."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")
        add_position(csv_path, "AAPL", 10, 175.0, "USD", "2025-02-01")

        loaded = load_portfolio(csv_path)
        assert len(loaded) == 2
        symbols = {p["symbol"] for p in loaded}
        assert symbols == {"7203.T", "AAPL"}

    def test_case_insensitive_symbol_match(self, csv_path):
        """Symbol matching for additional purchase should be case-insensitive."""
        add_position(csv_path, "AAPL", 10, 175.0, "USD", "2025-01-01")
        result = add_position(csv_path, "aapl", 5, 180.0, "USD", "2025-06-01")

        # Should merge with existing AAPL position
        assert result["shares"] == 15
        loaded = load_portfolio(csv_path)
        assert len(loaded) == 1

    def test_default_purchase_date(self, csv_path):
        """If purchase_date is None, it should default to today's date."""
        result = add_position(csv_path, "7203.T", 100, 2800.0, "JPY")
        assert result["purchase_date"] != ""
        # Should be in YYYY-MM-DD format
        parts = result["purchase_date"].split("-")
        assert len(parts) == 3

    def test_us_symbol_uppercased(self, csv_path):
        """US symbols (no dot) should be uppercased."""
        result = add_position(csv_path, "aapl", 10, 175.0, "USD", "2025-01-01")
        assert result["symbol"] == "AAPL"

    def test_jp_symbol_preserves_suffix(self, csv_path):
        """JP symbols with dot should preserve case."""
        result = add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")
        assert result["symbol"] == "7203.T"


# ===================================================================
# sell_position
# ===================================================================


class TestSellPosition:
    def test_partial_sell(self, csv_path):
        """Selling some shares should reduce the count."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")
        result = sell_position(csv_path, "7203.T", 30)

        assert result["shares"] == 70
        loaded = load_portfolio(csv_path)
        assert len(loaded) == 1
        assert loaded[0]["shares"] == 70

    def test_full_sell_removes_row(self, csv_path):
        """Selling all shares should remove the row from CSV."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")
        result = sell_position(csv_path, "7203.T", 100)

        assert result["shares"] == 0
        loaded = load_portfolio(csv_path)
        assert len(loaded) == 0

    def test_sell_more_than_owned_raises(self, csv_path):
        """Attempting to sell more shares than owned should raise ValueError."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")

        with pytest.raises(ValueError, match="保有数.*超える"):
            sell_position(csv_path, "7203.T", 200)

    def test_sell_nonexistent_symbol_raises(self, csv_path):
        """Selling a symbol not in portfolio should raise ValueError."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")

        with pytest.raises(ValueError, match="存在しません"):
            sell_position(csv_path, "MSFT", 10)

    def test_sell_preserves_cost_price(self, csv_path):
        """Partial sell should not change the cost_price."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")
        sell_position(csv_path, "7203.T", 30)

        loaded = load_portfolio(csv_path)
        assert loaded[0]["cost_price"] == 2800.0

    def test_sell_does_not_affect_other_positions(self, csv_path):
        """Selling one symbol should not affect other positions."""
        add_position(csv_path, "7203.T", 100, 2800.0, "JPY", "2025-01-01")
        add_position(csv_path, "AAPL", 10, 175.0, "USD", "2025-02-01")

        sell_position(csv_path, "7203.T", 50)

        loaded = load_portfolio(csv_path)
        assert len(loaded) == 2
        jp_pos = next(p for p in loaded if p["symbol"] == "7203.T")
        us_pos = next(p for p in loaded if p["symbol"] == "AAPL")
        assert jp_pos["shares"] == 50
        assert us_pos["shares"] == 10  # unchanged

    def test_sell_empty_portfolio_raises(self, csv_path):
        """Selling from an empty portfolio should raise ValueError."""
        # Create empty CSV
        save_portfolio([], csv_path)

        with pytest.raises(ValueError, match="存在しません"):
            sell_position(csv_path, "7203.T", 10)

    def test_case_insensitive_sell(self, csv_path):
        """Symbol matching for sell should be case-insensitive."""
        add_position(csv_path, "AAPL", 10, 175.0, "USD", "2025-01-01")
        result = sell_position(csv_path, "aapl", 5)
        assert result["shares"] == 5


# ===================================================================
# _infer_country / _infer_currency helpers
# ===================================================================


class TestInferCountry:
    def test_japan_suffix(self):
        assert _infer_country("7203.T") == "Japan"

    def test_singapore_suffix(self):
        assert _infer_country("D05.SI") == "Singapore"

    def test_us_no_suffix(self):
        assert _infer_country("AAPL") == "United States"

    def test_unknown_suffix(self):
        assert _infer_country("UNKNOWN.XX") == "Unknown"

    def test_hong_kong_suffix(self):
        assert _infer_country("0005.HK") == "Hong Kong"


class TestInferCurrency:
    def test_japan_suffix(self):
        assert _infer_currency("7203.T") == "JPY"

    def test_singapore_suffix(self):
        assert _infer_currency("D05.SI") == "SGD"

    def test_us_no_suffix(self):
        assert _infer_currency("AAPL") == "USD"

    def test_hong_kong_suffix(self):
        assert _infer_currency("0005.HK") == "HKD"

    def test_unknown_suffix_defaults_usd(self):
        assert _infer_currency("UNKNOWN.XX") == "USD"

    def test_cash_jpy(self):
        assert _infer_currency("JPY.CASH") == "JPY"

    def test_cash_usd(self):
        assert _infer_currency("USD.CASH") == "USD"


# ===================================================================
# _is_cash / _cash_currency helpers (KIK-361)
# ===================================================================


class TestIsCash:
    def test_jpy_cash(self):
        assert _is_cash("JPY.CASH") is True

    def test_usd_cash(self):
        assert _is_cash("USD.CASH") is True

    def test_lowercase_cash(self):
        assert _is_cash("jpy.cash") is True

    def test_normal_stock(self):
        assert _is_cash("7203.T") is False

    def test_us_stock(self):
        assert _is_cash("AAPL") is False


class TestCashCurrency:
    def test_jpy(self):
        assert _cash_currency("JPY.CASH") == "JPY"

    def test_usd(self):
        assert _cash_currency("USD.CASH") == "USD"

    def test_sgd(self):
        assert _cash_currency("SGD.CASH") == "SGD"


class TestInferCountryCash:
    def test_jpy_cash_country(self):
        assert _infer_country("JPY.CASH") == "Japan"

    def test_usd_cash_country(self):
        assert _infer_country("USD.CASH") == "United States"

    def test_sgd_cash_country(self):
        assert _infer_country("SGD.CASH") == "Singapore"


# ===================================================================
# get_snapshot with .CASH (KIK-361)
# ===================================================================


class TestGetSnapshotCash:
    def test_cash_position_skips_api(self, csv_path):
        """Cash positions should not trigger API calls."""
        from src.core.portfolio.portfolio_manager import get_snapshot

        portfolio = [
            {"symbol": "JPY.CASH", "shares": 1, "cost_price": 500000.0,
             "cost_currency": "JPY", "purchase_date": "2025-01-01", "memo": "現金"},
        ]
        save_portfolio(portfolio, csv_path)

        # Mock client that should NOT be called for cash
        class MockClient:
            def __init__(self):
                self.called = False

            def get_stock_info(self, symbol):
                if symbol.upper().endswith(".CASH"):
                    self.called = True
                    raise AssertionError(f"API should not be called for {symbol}")
                # Return FX rate data for USDJPY=X etc.
                return {"price": 150.0}

        client = MockClient()
        result = get_snapshot(csv_path, client)

        assert len(result["positions"]) == 1
        pos = result["positions"][0]
        assert pos["symbol"] == "JPY.CASH"
        assert pos["name"] == "現金 (JPY)"
        assert pos["sector"] == "Cash"
        assert pos["pnl"] == 0.0
        assert pos["pnl_pct"] == 0.0
        assert not client.called
