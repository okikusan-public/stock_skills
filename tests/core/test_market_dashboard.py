"""Tests for market dashboard (KIK-567)."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


def _make_price_history(values, start_date=None):
    """Create a mock DataFrame mimicking yfinance price history."""
    if start_date is None:
        start_date = datetime.now() - timedelta(days=len(values))
    dates = pd.date_range(start=start_date, periods=len(values), freq="B")
    return pd.DataFrame({
        "Open": values,
        "High": [v * 1.01 for v in values],
        "Low": [v * 0.99 for v in values],
        "Close": values,
        "Volume": [1000000] * len(values),
    }, index=dates)


class TestComputeRSI:
    def test_basic(self):
        from src.core.market_dashboard import _compute_rsi
        # Create a series with known pattern
        values = list(range(100, 120))  # Steady increase -> RSI should be high
        series = pd.Series(values, dtype=float)
        rsi = _compute_rsi(series, 14)
        assert rsi is not None
        assert rsi > 50  # Uptrend -> RSI > 50

    def test_insufficient_data(self):
        from src.core.market_dashboard import _compute_rsi
        series = pd.Series([1.0, 2.0, 3.0])
        assert _compute_rsi(series, 14) is None

    def test_all_gains(self):
        from src.core.market_dashboard import _compute_rsi
        series = pd.Series([float(i) for i in range(1, 20)])
        rsi = _compute_rsi(series, 14)
        assert rsi == 100.0  # All gains, no losses


class TestFGLabel:
    def test_extreme_fear(self):
        from src.core.market_dashboard import _fg_label
        assert _fg_label(10) == "Extreme Fear"

    def test_neutral(self):
        from src.core.market_dashboard import _fg_label
        assert _fg_label(50) == "Neutral"

    def test_extreme_greed(self):
        from src.core.market_dashboard import _fg_label
        assert _fg_label(90) == "Extreme Greed"


class TestVIXPhase:
    def test_phases(self):
        from src.core.market_dashboard import _vix_phase
        assert "Low" in _vix_phase(12)
        assert "Normal" in _vix_phase(17)
        assert "Elevated" in _vix_phase(22)
        assert "High" in _vix_phase(27)
        assert "Crisis" in _vix_phase(35)


class TestComputeFearGreed:
    def test_returns_score_and_indicators(self):
        from src.core.market_dashboard import compute_fear_greed

        mock_client = MagicMock()
        # S&P500: 250 trading days of upward trend
        values = [4000 + i * 5 for i in range(250)]
        sp_hist = _make_price_history(values)
        # VIX: steady at 18
        vix_values = [18.0] * 22
        vix_hist = _make_price_history(vix_values)

        mock_client.get_price_history.side_effect = lambda sym, **kw: (
            sp_hist if sym == "^GSPC" else vix_hist
        )

        result = compute_fear_greed(client=mock_client)
        assert "score" in result
        assert "label" in result
        assert "indicators" in result
        assert 0 <= result["score"] <= 100
        assert len(result["indicators"]) > 0

    def test_empty_data(self):
        from src.core.market_dashboard import compute_fear_greed

        mock_client = MagicMock()
        mock_client.get_price_history.return_value = pd.DataFrame()

        result = compute_fear_greed(client=mock_client)
        assert result["score"] == 50
        assert result["label"] == "Neutral"


class TestGetVIXHistory:
    def test_returns_history(self):
        from src.core.market_dashboard import get_vix_history

        mock_client = MagicMock()
        values = [20.0, 21.0, 19.0, 18.0, 22.0, 20.0, 19.0]
        mock_client.get_price_history.return_value = _make_price_history(values)

        result = get_vix_history(client=mock_client)
        assert result["current"] is not None
        assert result["phase"] != "Unknown"
        assert len(result["history"]) > 0

    def test_empty_data(self):
        from src.core.market_dashboard import get_vix_history

        mock_client = MagicMock()
        mock_client.get_price_history.return_value = pd.DataFrame()

        result = get_vix_history(client=mock_client)
        assert result["current"] is None
        assert result["phase"] == "Unknown"


class TestGetYieldCurve:
    def test_returns_yields_and_spread(self):
        from src.core.market_dashboard import get_yield_curve

        mock_client = MagicMock()

        def mock_history(sym, **kw):
            rates = {
                "^IRX": 4.5,  # 3M
                "^FVX": 4.2,  # 5Y
                "^TNX": 4.3,  # 10Y
                "^TYX": 4.6,  # 30Y
            }
            rate = rates.get(sym, 4.0)
            return _make_price_history([rate] * 5)

        mock_client.get_price_history.side_effect = mock_history

        result = get_yield_curve(client=mock_client)
        assert "yields" in result
        assert "10Y" in result["yields"]
        assert result["spread_10y_3m"] is not None
        # 10Y(4.3) - 3M(4.5) = -0.2 → inverted
        assert result["spread_10y_3m"] < 0
        assert "逆イールド" in result["curve_status"]

    def test_normal_yield_curve(self):
        from src.core.market_dashboard import get_yield_curve

        mock_client = MagicMock()

        def mock_history(sym, **kw):
            rates = {
                "^IRX": 3.0,  # 3M
                "^FVX": 3.5,  # 5Y
                "^TNX": 4.0,  # 10Y
                "^TYX": 4.5,  # 30Y
            }
            rate = rates.get(sym, 3.5)
            return _make_price_history([rate] * 5)

        mock_client.get_price_history.side_effect = mock_history

        result = get_yield_curve(client=mock_client)
        assert result["spread_10y_3m"] > 0
        assert "順イールド" in result["curve_status"]

    def test_empty_data(self):
        from src.core.market_dashboard import get_yield_curve

        mock_client = MagicMock()
        mock_client.get_price_history.return_value = pd.DataFrame()

        result = get_yield_curve(client=mock_client)
        assert result["yields"] == {}
        assert result["curve_status"] == "不明"
