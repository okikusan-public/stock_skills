"""Tests for src.core.portfolio.backtest module."""

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.core.portfolio.backtest import _get_benchmark_return, run_backtest
from src.data.history_store import save_screening


# ===================================================================
# Helpers
# ===================================================================

def _make_screening_file(tmp_path, screen_date, preset, region, stocks):
    """Manually create a screening history JSON file."""
    screen_dir = tmp_path / "screen"
    screen_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{screen_date}_{region}_{preset}.json"
    payload = {
        "category": "screen",
        "date": screen_date,
        "timestamp": f"{screen_date}T10:00:00",
        "preset": preset,
        "region": region,
        "sector": None,
        "count": len(stocks),
        "results": stocks,
        "_saved_at": f"{screen_date}T10:00:00",
    }
    path = screen_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return str(path)


def _mock_client(prices=None, price_history=None):
    """Create a mock yahoo_client module with get_stock_info and get_price_history."""
    mock = MagicMock()

    if prices is not None:
        def _get_info(symbol):
            if symbol in prices:
                return {"price": prices[symbol]}
            return None
        mock.get_stock_info.side_effect = _get_info
    else:
        mock.get_stock_info.return_value = None

    if price_history is not None:
        mock.get_price_history.return_value = price_history
    else:
        mock.get_price_history.return_value = None

    return mock


def _make_price_df(start_price, end_price, n=10):
    """Create a simple DataFrame with Close column."""
    import numpy as np
    closes = np.linspace(start_price, end_price, n)
    return pd.DataFrame({"Close": closes})


# ===================================================================
# run_backtest
# ===================================================================


class TestRunBacktest:
    def test_basic_backtest(self, tmp_path):
        screen_date = (date.today() - timedelta(days=30)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [{"symbol": "7203.T", "name": "Toyota", "price": 2850, "value_score": 72.5}],
        )

        mock = _mock_client(prices={"7203.T": 3100, "^N225": 40000, "^GSPC": 5200})
        mock.get_price_history.return_value = _make_price_df(38000, 40000)

        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        assert result["total_screens"] == 1
        assert result["total_stocks"] == 1
        assert len(result["stocks"]) == 1
        assert result["stocks"][0]["symbol"] == "7203.T"
        assert "period" in result
        assert "avg_return" in result
        assert "win_rate" in result

    def test_return_calculation(self, tmp_path):
        screen_date = (date.today() - timedelta(days=10)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [{"symbol": "A", "name": "StockA", "price": 100.0, "value_score": 60}],
        )

        mock = _mock_client(prices={"A": 120.0})
        mock.get_price_history.return_value = None

        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        assert result["total_stocks"] == 1
        stock = result["stocks"][0]
        expected_return = (120.0 - 100.0) / 100.0  # 0.2
        assert stock["return_pct"] == pytest.approx(expected_return)
        assert stock["price_at_screen"] == 100.0
        assert stock["price_now"] == 120.0

    def test_empty_history(self, tmp_path):
        mock = _mock_client()
        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        assert result["total_screens"] == 0
        assert result["total_stocks"] == 0
        assert result["stocks"] == []
        assert result["avg_return"] == 0.0
        assert result["win_rate"] == 0.0
        assert result["benchmark"]["nikkei"] is None
        assert result["benchmark"]["sp500"] is None

    def test_preset_filter(self, tmp_path):
        screen_date = (date.today() - timedelta(days=5)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [{"symbol": "A", "name": "A", "price": 100, "value_score": 50}],
        )
        _make_screening_file(
            tmp_path, screen_date, "alpha", "japan",
            [{"symbol": "B", "name": "B", "price": 200, "value_score": 70}],
        )

        mock = _mock_client(prices={"A": 110, "B": 220})
        mock.get_price_history.return_value = None

        # Filter to only "value"
        result = run_backtest(mock, preset="value", base_dir=str(tmp_path), days_back=90)
        symbols = [s["symbol"] for s in result["stocks"]]
        assert "A" in symbols
        assert "B" not in symbols

    def test_region_filter(self, tmp_path):
        screen_date = (date.today() - timedelta(days=5)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [{"symbol": "A", "name": "A", "price": 100, "value_score": 50}],
        )
        _make_screening_file(
            tmp_path, screen_date, "value", "us",
            [{"symbol": "B", "name": "B", "price": 200, "value_score": 70}],
        )

        mock = _mock_client(prices={"A": 110, "B": 220})
        mock.get_price_history.return_value = None

        result = run_backtest(mock, region="us", base_dir=str(tmp_path), days_back=90)
        symbols = [s["symbol"] for s in result["stocks"]]
        assert "B" in symbols
        assert "A" not in symbols

    def test_duplicate_symbol_uses_oldest(self, tmp_path):
        old_date = (date.today() - timedelta(days=30)).isoformat()
        new_date = (date.today() - timedelta(days=5)).isoformat()

        _make_screening_file(
            tmp_path, old_date, "value", "japan",
            [{"symbol": "7203.T", "name": "Toyota", "price": 2800, "value_score": 70}],
        )
        _make_screening_file(
            tmp_path, new_date, "value", "japan",
            [{"symbol": "7203.T", "name": "Toyota", "price": 3000, "value_score": 75}],
        )

        mock = _mock_client(prices={"7203.T": 3100})
        mock.get_price_history.return_value = None

        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        assert result["total_stocks"] == 1
        stock = result["stocks"][0]
        # Should use the oldest price (2800), not the newer one (3000)
        assert stock["price_at_screen"] == 2800
        assert stock["screen_date"] == old_date

    def test_win_rate_calculation(self, tmp_path):
        screen_date = (date.today() - timedelta(days=10)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [
                {"symbol": "W1", "name": "Win1", "price": 100, "value_score": 50},
                {"symbol": "W2", "name": "Win2", "price": 100, "value_score": 50},
                {"symbol": "L1", "name": "Lose1", "price": 100, "value_score": 50},
            ],
        )

        mock = _mock_client(prices={"W1": 120, "W2": 110, "L1": 80})
        mock.get_price_history.return_value = None

        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        # 2 winners out of 3
        assert result["win_rate"] == pytest.approx(2 / 3)

    def test_alpha_calculation(self, tmp_path):
        screen_date = (date.today() - timedelta(days=10)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [{"symbol": "A", "name": "A", "price": 100, "value_score": 60}],
        )

        # Stock return: (150 - 100) / 100 = 0.5
        mock = _mock_client(prices={"A": 150})
        # Benchmark: 100 -> 110 = 0.1 return
        mock.get_price_history.return_value = _make_price_df(100, 110)

        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        assert result["avg_return"] == pytest.approx(0.5)
        # Alpha = avg_return - benchmark
        assert result["alpha_nikkei"] == pytest.approx(0.5 - 0.1)
        assert result["alpha_sp500"] == pytest.approx(0.5 - 0.1)

    def test_missing_current_price_skips_stock(self, tmp_path):
        screen_date = (date.today() - timedelta(days=10)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [
                {"symbol": "GOOD", "name": "Good", "price": 100, "value_score": 50},
                {"symbol": "BAD", "name": "Bad", "price": 100, "value_score": 50},
            ],
        )

        def _get_info(symbol):
            if symbol == "GOOD":
                return {"price": 120}
            return None  # BAD and benchmarks return None

        mock = MagicMock()
        mock.get_stock_info.side_effect = _get_info
        mock.get_price_history.return_value = None

        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        assert result["total_stocks"] == 1
        assert result["stocks"][0]["symbol"] == "GOOD"

    def test_zero_price_at_screen_skipped(self, tmp_path):
        screen_date = (date.today() - timedelta(days=5)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [{"symbol": "ZERO", "name": "Zero", "price": 0, "value_score": 50}],
        )

        mock = _mock_client(prices={"ZERO": 100})
        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        assert result["total_stocks"] == 0

    def test_stocks_sorted_by_return_desc(self, tmp_path):
        screen_date = (date.today() - timedelta(days=10)).isoformat()
        _make_screening_file(
            tmp_path, screen_date, "value", "japan",
            [
                {"symbol": "LOW", "name": "Low", "price": 100, "value_score": 50},
                {"symbol": "HIGH", "name": "High", "price": 100, "value_score": 50},
                {"symbol": "MID", "name": "Mid", "price": 100, "value_score": 50},
            ],
        )

        mock = _mock_client(prices={"LOW": 90, "HIGH": 200, "MID": 120})
        mock.get_price_history.return_value = None

        result = run_backtest(mock, base_dir=str(tmp_path), days_back=90)

        symbols = [s["symbol"] for s in result["stocks"]]
        assert symbols == ["HIGH", "MID", "LOW"]

    def test_days_back_limits_scope(self, tmp_path):
        old_date = (date.today() - timedelta(days=100)).isoformat()
        recent_date = (date.today() - timedelta(days=5)).isoformat()

        _make_screening_file(
            tmp_path, old_date, "value", "japan",
            [{"symbol": "OLD", "name": "Old", "price": 100, "value_score": 50}],
        )
        _make_screening_file(
            tmp_path, recent_date, "value", "japan",
            [{"symbol": "NEW", "name": "New", "price": 100, "value_score": 50}],
        )

        mock = _mock_client(prices={"OLD": 110, "NEW": 120})
        mock.get_price_history.return_value = None

        result = run_backtest(mock, days_back=30, base_dir=str(tmp_path))

        symbols = [s["symbol"] for s in result["stocks"]]
        assert "NEW" in symbols
        assert "OLD" not in symbols


# ===================================================================
# _get_benchmark_return
# ===================================================================


class TestBenchmark:
    def test_benchmark_returns(self):
        mock = MagicMock()
        mock.get_price_history.return_value = _make_price_df(100, 120, n=20)

        result = _get_benchmark_return(mock, "^N225", "2026-01-01")

        expected = (120.0 - 100.0) / 100.0  # 0.2
        assert result == pytest.approx(expected)

    def test_benchmark_failure_returns_none(self):
        mock = MagicMock()
        mock.get_price_history.return_value = None

        result = _get_benchmark_return(mock, "^N225", "2026-01-01")
        assert result is None

    def test_benchmark_empty_df_returns_none(self):
        mock = MagicMock()
        mock.get_price_history.return_value = pd.DataFrame()

        result = _get_benchmark_return(mock, "^N225", "2026-01-01")
        assert result is None

    def test_benchmark_single_row_returns_none(self):
        mock = MagicMock()
        mock.get_price_history.return_value = pd.DataFrame({"Close": [100.0]})

        result = _get_benchmark_return(mock, "^N225", "2026-01-01")
        assert result is None

    def test_benchmark_zero_start_price_returns_none(self):
        mock = MagicMock()
        mock.get_price_history.return_value = pd.DataFrame({"Close": [0.0, 100.0]})

        result = _get_benchmark_return(mock, "^N225", "2026-01-01")
        assert result is None

    def test_benchmark_negative_return(self):
        mock = MagicMock()
        mock.get_price_history.return_value = _make_price_df(200, 180, n=10)

        result = _get_benchmark_return(mock, "^GSPC", "2026-01-01")

        expected = (180.0 - 200.0) / 200.0  # -0.1
        assert result == pytest.approx(expected)

    def test_benchmark_no_close_column(self):
        mock = MagicMock()
        mock.get_price_history.return_value = pd.DataFrame({"Open": [100, 110]})

        result = _get_benchmark_return(mock, "^N225", "2026-01-01")
        assert result is None
