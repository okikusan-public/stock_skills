"""Tests for portfolio_simulation (KIK-376: What-If simulation)."""

import copy
import os
import tempfile

import pytest

from src.core.portfolio.portfolio_manager import merge_positions, save_portfolio
from src.core.portfolio.portfolio_simulation import (
    _compute_judgment,
    _compute_required_cash,
    _extract_metrics,
    parse_add_arg,
    run_what_if_simulation,
)


# =========================================================================
# TestParseAddArg
# =========================================================================


class TestParseAddArg:
    """Tests for parse_add_arg()."""

    def test_single_entry(self):
        result = parse_add_arg("7203.T:100:2850")
        assert len(result) == 1
        assert result[0]["symbol"] == "7203.T"
        assert result[0]["shares"] == 100
        assert result[0]["cost_price"] == 2850.0
        assert result[0]["cost_currency"] == "JPY"

    def test_multiple_entries(self):
        result = parse_add_arg("7203.T:100:2850,AAPL:10:250")
        assert len(result) == 2
        assert result[0]["symbol"] == "7203.T"
        assert result[1]["symbol"] == "AAPL"
        assert result[1]["cost_currency"] == "USD"

    def test_us_stock_currency(self):
        result = parse_add_arg("MSFT:5:400")
        assert result[0]["cost_currency"] == "USD"

    def test_singapore_stock_currency(self):
        result = parse_add_arg("D05.SI:200:35")
        assert result[0]["cost_currency"] == "SGD"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="空"):
            parse_add_arg("")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="不正な形式"):
            parse_add_arg("7203.T:100")

    def test_negative_shares_raises(self):
        with pytest.raises(ValueError, match="正の整数"):
            parse_add_arg("7203.T:-10:2850")

    def test_zero_price_raises(self):
        with pytest.raises(ValueError, match="正の数"):
            parse_add_arg("7203.T:100:0")

    def test_non_numeric_shares_raises(self):
        with pytest.raises(ValueError, match="株数が不正"):
            parse_add_arg("7203.T:abc:2850")

    def test_spaces_in_entries(self):
        result = parse_add_arg(" 7203.T : 100 : 2850 , AAPL : 10 : 250 ")
        assert len(result) == 2
        assert result[0]["symbol"] == "7203.T"
        assert result[1]["symbol"] == "AAPL"


# =========================================================================
# TestMergePositions
# =========================================================================


class TestMergePositions:
    """Tests for merge_positions()."""

    def test_add_new_symbol(self):
        current = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 2800.0,
             "cost_currency": "JPY", "purchase_date": "2024-01-01", "memo": ""},
        ]
        proposed = [
            {"symbol": "AAPL", "shares": 10, "cost_price": 250.0,
             "cost_currency": "USD"},
        ]
        merged = merge_positions(current, proposed)
        assert len(merged) == 2
        assert merged[1]["symbol"] == "AAPL"
        assert merged[1]["shares"] == 10
        assert merged[1]["memo"] == "(what-if)"

    def test_merge_existing_symbol(self):
        current = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 2800.0,
             "cost_currency": "JPY", "purchase_date": "2024-01-01", "memo": ""},
        ]
        proposed = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 3000.0,
             "cost_currency": "JPY"},
        ]
        merged = merge_positions(current, proposed)
        assert len(merged) == 1
        assert merged[0]["shares"] == 200
        # Weighted average: (100*2800 + 100*3000) / 200 = 2900
        assert merged[0]["cost_price"] == pytest.approx(2900.0)

    def test_case_insensitive_symbol_match(self):
        current = [
            {"symbol": "aapl", "shares": 10, "cost_price": 200.0,
             "cost_currency": "USD", "purchase_date": "", "memo": ""},
        ]
        proposed = [
            {"symbol": "AAPL", "shares": 5, "cost_price": 250.0,
             "cost_currency": "USD"},
        ]
        merged = merge_positions(current, proposed)
        assert len(merged) == 1
        assert merged[0]["shares"] == 15

    def test_input_not_mutated(self):
        current = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 2800.0,
             "cost_currency": "JPY", "purchase_date": "", "memo": ""},
        ]
        proposed = [
            {"symbol": "7203.T", "shares": 50, "cost_price": 3000.0,
             "cost_currency": "JPY"},
        ]
        original_current = copy.deepcopy(current)
        merge_positions(current, proposed)
        assert current == original_current

    def test_empty_current(self):
        proposed = [
            {"symbol": "AAPL", "shares": 10, "cost_price": 250.0,
             "cost_currency": "USD"},
        ]
        merged = merge_positions([], proposed)
        assert len(merged) == 1
        assert merged[0]["symbol"] == "AAPL"


# =========================================================================
# TestExtractMetrics
# =========================================================================


class TestExtractMetrics:
    """Tests for _extract_metrics()."""

    def test_basic_extraction(self):
        snapshot = {
            "total_value_jpy": 10_000_000,
            "total_cost_jpy": 9_000_000,
            "total_pnl_jpy": 1_000_000,
            "total_pnl_pct": 0.1111,
        }
        structure = {
            "sector_hhi": 0.45,
            "region_hhi": 0.60,
            "currency_hhi": 0.50,
            "concentration_multiplier": 1.3,
            "risk_level": "やや集中",
        }
        forecast = {
            "portfolio": {
                "optimistic": 0.25,
                "base": 0.15,
                "pessimistic": -0.05,
            }
        }
        metrics = _extract_metrics(snapshot, structure, forecast)
        assert metrics["total_value_jpy"] == 10_000_000
        assert metrics["sector_hhi"] == 0.45
        assert metrics["forecast_base"] == 0.15


# =========================================================================
# TestComputeRequiredCash
# =========================================================================


class TestComputeRequiredCash:
    """Tests for _compute_required_cash()."""

    def test_jpy_only(self):
        proposed = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 2850.0,
             "cost_currency": "JPY"},
        ]
        fx_rates = {"JPY": 1.0}
        assert _compute_required_cash(proposed, fx_rates) == 285000.0

    def test_mixed_currencies(self):
        proposed = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 2850.0,
             "cost_currency": "JPY"},
            {"symbol": "AAPL", "shares": 10, "cost_price": 250.0,
             "cost_currency": "USD"},
        ]
        fx_rates = {"JPY": 1.0, "USD": 150.0}
        # 100*2850*1.0 + 10*250*150 = 285000 + 375000 = 660000
        assert _compute_required_cash(proposed, fx_rates) == 660000.0


# =========================================================================
# TestComputeJudgment
# =========================================================================


class TestComputeJudgment:
    """Tests for _compute_judgment()."""

    def test_recommend_when_improved(self):
        before = {"sector_hhi": 0.50, "region_hhi": 0.40, "forecast_base": 0.10}
        after = {"sector_hhi": 0.35, "region_hhi": 0.30, "forecast_base": 0.12}
        result = _compute_judgment(before, after, [])
        assert result["recommendation"] == "recommend"

    def test_not_recommended_with_exit_signal(self):
        before = {"sector_hhi": 0.50, "region_hhi": 0.40, "forecast_base": 0.10}
        after = {"sector_hhi": 0.35, "region_hhi": 0.30, "forecast_base": 0.12}
        proposed_health = [
            {"symbol": "BAD", "alert": {"level": "exit", "label": "撤退"}},
        ]
        result = _compute_judgment(before, after, proposed_health)
        assert result["recommendation"] == "not_recommended"

    def test_caution_with_warning(self):
        before = {"sector_hhi": 0.30, "region_hhi": 0.30, "forecast_base": 0.10}
        after = {"sector_hhi": 0.28, "region_hhi": 0.28, "forecast_base": 0.10}
        proposed_health = [
            {"symbol": "WARN", "alert": {"level": "early_warning", "label": "早期警告"}},
        ]
        result = _compute_judgment(before, after, proposed_health)
        assert result["recommendation"] == "caution"

    def test_not_recommended_both_worsened(self):
        before = {"sector_hhi": 0.30, "region_hhi": 0.30, "forecast_base": 0.10}
        after = {"sector_hhi": 0.40, "region_hhi": 0.40, "forecast_base": 0.04}
        result = _compute_judgment(before, after, [])
        assert result["recommendation"] == "not_recommended"


# =========================================================================
# TestRunWhatIfSimulation
# =========================================================================


class TestRunWhatIfSimulation:
    """Tests for run_what_if_simulation() with mocked yahoo_client."""

    @pytest.fixture()
    def mock_client(self, monkeypatch):
        """Create a mock yahoo_client module."""
        import types
        client = types.ModuleType("mock_yahoo_client")

        stock_prices = {
            "7203.T": 3000.0,
            "AAPL": 250.0,
            "9984.T": 8000.0,
        }

        def get_stock_info(symbol):
            price = stock_prices.get(symbol)
            if price is None:
                return None
            return {
                "symbol": symbol,
                "price": price,
                "name": symbol,
                "sector": "Technology",
                "currency": "JPY" if symbol.endswith(".T") else "USD",
            }

        def get_stock_detail(symbol):
            price = stock_prices.get(symbol)
            if price is None:
                return None
            return {
                "symbol": symbol,
                "price": price,
                "name": symbol,
                "sector": "Technology",
                "market_cap": price * 1_000_000,
                "per": 15.0,
                "pbr": 1.5,
                "roe": 0.12,
                "dividend_yield": 0.02,
                "analyst_count": 10,
                "target_mean": price * 1.1,
                "forward_per": 13.0,
                "currency": "JPY" if symbol.endswith(".T") else "USD",
            }

        def get_stock_news(symbol, count=5):
            return []

        def get_price_history(symbol, period="1y"):
            import pandas as pd
            import numpy as np
            dates = pd.date_range("2024-01-01", periods=252, freq="B")
            base = stock_prices.get(symbol, 100)
            prices = base * (1 + np.random.randn(252) * 0.01).cumprod()
            return pd.DataFrame(
                {"Close": prices, "Volume": [1000000] * 252},
                index=dates,
            )

        client.get_stock_info = get_stock_info
        client.get_stock_detail = get_stock_detail
        client.get_stock_news = get_stock_news
        client.get_price_history = get_price_history

        return client

    @pytest.fixture()
    def portfolio_csv(self):
        """Create a temp portfolio CSV."""
        fd, path = tempfile.mkstemp(suffix=".csv", prefix="test_pf_")
        os.close(fd)
        portfolio = [
            {"symbol": "7203.T", "shares": 100, "cost_price": 2800.0,
             "cost_currency": "JPY", "purchase_date": "2024-01-01",
             "memo": "Toyota"},
        ]
        save_portfolio(portfolio, path)
        yield path
        if os.path.exists(path):
            os.remove(path)

    def test_basic_simulation(self, portfolio_csv, mock_client):
        proposed = [
            {"symbol": "9984.T", "shares": 50, "cost_price": 7500.0,
             "cost_currency": "JPY"},
        ]
        result = run_what_if_simulation(
            portfolio_csv, proposed, mock_client
        )

        assert "before" in result
        assert "after" in result
        assert "proposed" in result
        assert "judgment" in result
        assert "required_cash_jpy" in result

        # After should have higher total value
        assert (
            result["after"]["total_value_jpy"]
            > result["before"]["total_value_jpy"]
        )

        # Required cash for 50 shares @ 7500 JPY
        assert result["required_cash_jpy"] == pytest.approx(375000.0)

    def test_temp_csv_cleaned_up(self, portfolio_csv, mock_client):
        proposed = [
            {"symbol": "9984.T", "shares": 50, "cost_price": 7500.0,
             "cost_currency": "JPY"},
        ]

        # Track temp files before
        temp_dir = tempfile.gettempdir()
        before_files = set(os.listdir(temp_dir))

        run_what_if_simulation(portfolio_csv, proposed, mock_client)

        # Check no whatif_ temp files remain
        after_files = set(os.listdir(temp_dir))
        new_files = after_files - before_files
        whatif_files = [f for f in new_files if f.startswith("whatif_")]
        assert len(whatif_files) == 0

    def test_original_csv_unchanged(self, portfolio_csv, mock_client):
        from src.core.portfolio.portfolio_manager import load_portfolio

        original = load_portfolio(portfolio_csv)

        proposed = [
            {"symbol": "9984.T", "shares": 50, "cost_price": 7500.0,
             "cost_currency": "JPY"},
        ]
        run_what_if_simulation(portfolio_csv, proposed, mock_client)

        after = load_portfolio(portfolio_csv)
        assert len(after) == len(original)
        assert after[0]["symbol"] == original[0]["symbol"]
        assert after[0]["shares"] == original[0]["shares"]
