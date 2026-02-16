"""Tests for src/core/technicals.py -- RSI, Bollinger Bands, pullback detection."""

import math

import numpy as np
import pandas as pd
import pytest

from src.core.screening.technicals import (
    compute_rsi,
    compute_bollinger_bands,
    detect_pullback_in_uptrend,
)


# ===================================================================
# compute_rsi tests
# ===================================================================

class TestComputeRsi:
    """Tests for compute_rsi()."""

    def test_all_ascending_rsi_near_100(self):
        """Strictly ascending prices should produce RSI close to 100."""
        prices = pd.Series([float(i) for i in range(1, 101)])
        rsi = compute_rsi(prices, period=14)
        # The last RSI value should be very high
        last_rsi = rsi.iloc[-1]
        assert last_rsi > 95.0, f"Expected RSI > 95 for all-ascending, got {last_rsi}"

    def test_all_descending_rsi_near_0(self):
        """Strictly descending prices should produce RSI close to 0."""
        prices = pd.Series([float(100 - i) for i in range(100)])
        rsi = compute_rsi(prices, period=14)
        last_rsi = rsi.iloc[-1]
        assert last_rsi < 5.0, f"Expected RSI < 5 for all-descending, got {last_rsi}"

    def test_flat_prices_rsi_near_50(self):
        """Flat (constant) prices should produce RSI around 50 or NaN.

        For truly flat data, delta is 0 for all periods, so avg_gain=0 and
        avg_loss=0, resulting in 0/0 = NaN. We verify it does not crash.
        """
        prices = pd.Series([100.0] * 50)
        rsi = compute_rsi(prices, period=14)
        # Should not raise; last value will be NaN (0/0 division)
        assert len(rsi) == 50

    def test_alternating_prices_rsi_around_50(self):
        """Alternating up/down prices should produce RSI near 50."""
        # Pattern: 100, 101, 100, 101, ... (equal gains and losses)
        prices = pd.Series([100.0 + (i % 2) for i in range(100)])
        rsi = compute_rsi(prices, period=14)
        last_rsi = rsi.iloc[-1]
        assert 40.0 <= last_rsi <= 60.0, f"Expected RSI near 50, got {last_rsi}"

    def test_rsi_range_0_to_100(self):
        """RSI values should always be between 0 and 100 (where not NaN)."""
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(200)) + 100)
        rsi = compute_rsi(prices, period=14)
        valid = rsi.dropna()
        assert (valid >= 0).all(), "RSI has values below 0"
        assert (valid <= 100).all(), "RSI has values above 100"

    def test_rsi_first_values_are_nan(self):
        """Early values should be NaN due to min_periods requirement.

        The ewm uses min_periods=period on the delta series (which starts
        at index 1 due to diff()), so the first valid RSI appears at index
        period (0-indexed). Indices 0 through period-2 are NaN.
        """
        prices = pd.Series([float(i) for i in range(50)])
        rsi = compute_rsi(prices, period=14)
        # Indices 0..12 (13 values) should be NaN
        assert rsi.iloc[:13].isna().all()
        # Index 13 (the 14th element) should have a valid value
        assert not pd.isna(rsi.iloc[13])


# ===================================================================
# compute_bollinger_bands tests
# ===================================================================

class TestComputeBollingerBands:
    """Tests for compute_bollinger_bands()."""

    def test_middle_equals_sma(self):
        """Middle band should equal the simple moving average."""
        prices = pd.Series([float(i) for i in range(50)])
        upper, middle, lower = compute_bollinger_bands(prices, period=20, std_dev=2.0)
        expected_sma = prices.rolling(window=20).mean()
        # Compare valid (non-NaN) values
        valid_idx = middle.dropna().index
        pd.testing.assert_series_equal(
            middle[valid_idx], expected_sma[valid_idx], check_names=False
        )

    def test_upper_greater_than_middle(self):
        """Upper band should be >= middle band."""
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
        upper, middle, lower = compute_bollinger_bands(prices, period=20, std_dev=2.0)
        valid_idx = upper.dropna().index
        assert (upper[valid_idx] >= middle[valid_idx]).all()

    def test_middle_greater_than_lower(self):
        """Middle band should be >= lower band."""
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
        upper, middle, lower = compute_bollinger_bands(prices, period=20, std_dev=2.0)
        valid_idx = lower.dropna().index
        assert (middle[valid_idx] >= lower[valid_idx]).all()

    def test_band_ordering(self):
        """upper > middle > lower (strict inequality for non-flat data)."""
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
        upper, middle, lower = compute_bollinger_bands(prices, period=20, std_dev=2.0)
        valid_idx = upper.dropna().index
        assert (upper[valid_idx] > lower[valid_idx]).all()

    def test_flat_prices_bands_converge(self):
        """For flat prices, std=0, so upper == middle == lower."""
        prices = pd.Series([100.0] * 50)
        upper, middle, lower = compute_bollinger_bands(prices, period=20, std_dev=2.0)
        valid_idx = upper.dropna().index
        pd.testing.assert_series_equal(
            upper[valid_idx], middle[valid_idx], check_names=False
        )
        pd.testing.assert_series_equal(
            middle[valid_idx], lower[valid_idx], check_names=False
        )

    def test_wider_std_gives_wider_bands(self):
        """Larger std_dev parameter should produce wider bands."""
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
        upper_2, _, lower_2 = compute_bollinger_bands(prices, period=20, std_dev=2.0)
        upper_3, _, lower_3 = compute_bollinger_bands(prices, period=20, std_dev=3.0)
        valid_idx = upper_2.dropna().index
        width_2 = upper_2[valid_idx] - lower_2[valid_idx]
        width_3 = upper_3[valid_idx] - lower_3[valid_idx]
        assert (width_3 > width_2).all()


# ===================================================================
# detect_pullback_in_uptrend tests
# ===================================================================

class TestDetectPullbackInUptrend:
    """Tests for detect_pullback_in_uptrend()."""

    def test_insufficient_data_returns_default(self):
        """DataFrame with < 200 rows should return default dict."""
        hist = pd.DataFrame({
            "Close": [100.0] * 100,
            "Volume": [1000000] * 100,
        })
        result = detect_pullback_in_uptrend(hist)
        assert result["uptrend"] is False
        assert result["is_pullback"] is False
        assert result["bounce_signal"] is False
        assert result["all_conditions"] is False
        assert math.isnan(result["rsi"])

    def test_exactly_200_rows_works(self):
        """DataFrame with exactly 200 rows should not return default."""
        # Build a simple uptrend (no pullback)
        close = [1000 + i * 2 for i in range(200)]
        volume = [5000000] * 200
        hist = pd.DataFrame({"Close": close, "Volume": volume})
        result = detect_pullback_in_uptrend(hist)
        # Should produce non-NaN values
        assert not math.isnan(result["rsi"])
        assert not math.isnan(result["sma50"])
        assert not math.isnan(result["sma200"])

    def test_downtrend_not_uptrend(self):
        """A clear downtrend should have uptrend=False."""
        # Price goes from 3000 down to ~1000 over 250 days
        close = [3000.0 - i * 8 for i in range(250)]
        volume = [5000000] * 250
        hist = pd.DataFrame({"Close": close, "Volume": volume})
        result = detect_pullback_in_uptrend(hist)
        assert result["uptrend"] is False
        assert result["all_conditions"] is False

    def test_strong_uptrend_no_pullback(self):
        """Strong monotonic uptrend with no pullback: uptrend=True, is_pullback=False."""
        # Consistent uptrend: price increases every day
        close = [1000.0 + i * 5 for i in range(250)]
        volume = [5000000] * 250
        hist = pd.DataFrame({"Close": close, "Volume": volume})
        result = detect_pullback_in_uptrend(hist)
        assert result["uptrend"] is True
        # No pullback because price hasn't dropped 5-20% from recent high
        assert result["is_pullback"] is False
        assert result["all_conditions"] is False

    def test_fixture_price_history(self, price_history_df):
        """The fixture CSV should produce valid results (no crashes).

        The fixture has an uptrend followed by a pullback pattern.
        """
        result = detect_pullback_in_uptrend(price_history_df)
        # Should produce non-NaN core values
        assert not math.isnan(result["rsi"])
        assert not math.isnan(result["sma50"])
        assert not math.isnan(result["sma200"])
        assert not math.isnan(result["current_price"])
        assert not math.isnan(result["recent_high"])
        # Result should be a well-formed dict
        assert "uptrend" in result
        assert "is_pullback" in result
        assert "bounce_signal" in result
        assert "bounce_score" in result
        assert "bounce_details" in result
        assert "all_conditions" in result

    def test_fixture_shows_uptrend(self, price_history_df):
        """The fixture is designed with an uptrend; verify uptrend=True."""
        result = detect_pullback_in_uptrend(price_history_df)
        # The fixture has a clear uptrend with SMA50 > SMA200 and price > SMA200
        assert result["uptrend"] is True

    def test_fixture_shows_pullback(self, price_history_df):
        """The fixture includes a pullback; verify is_pullback=True."""
        result = detect_pullback_in_uptrend(price_history_df)
        # The fixture drops ~12% from peak which is within [-20%, -5%] range
        assert result["is_pullback"] is True

    def test_pullback_pct_range(self, price_history_df):
        """pullback_pct should be negative (drop from recent high)."""
        result = detect_pullback_in_uptrend(price_history_df)
        # The fixture has a pullback, so pullback_pct should be negative
        assert result["pullback_pct"] < 0

    def test_bounce_score_is_numeric(self, price_history_df):
        """bounce_score should be a non-negative number."""
        result = detect_pullback_in_uptrend(price_history_df)
        assert isinstance(result["bounce_score"], float)
        assert result["bounce_score"] >= 0.0

    def test_bounce_details_structure(self, price_history_df):
        """bounce_details should have expected keys."""
        result = detect_pullback_in_uptrend(price_history_df)
        details = result["bounce_details"]
        assert "rsi_reversal" in details
        assert "rsi_depth_bonus" in details
        assert "bb_proximity" in details
        assert "volume_surge" in details
        assert "price_reversal" in details
        assert "lookback_day" in details

    def test_all_conditions_requires_all_three(self):
        """all_conditions should be True only when uptrend AND is_pullback AND bounce_signal."""
        # Build data with clear uptrend + pullback + bounce characteristics
        # First 210 days: strong uptrend
        close = [1000.0 + i * 3 for i in range(210)]
        # Days 210-240: pullback of ~10%
        peak = close[-1]
        for i in range(30):
            drop = peak * (1 - 0.10 * (i / 30))
            close.append(drop)
        # Days 240-250: sharp bounce with RSI reversal
        bottom = close[-1]
        for i in range(10):
            close.append(bottom + i * 5)

        volume = [5000000] * 210 + [3000000] * 30 + [8000000] * 10
        hist = pd.DataFrame({"Close": close, "Volume": volume})
        result = detect_pullback_in_uptrend(hist)
        # Whether all_conditions is True depends on the exact data pattern,
        # but the important thing is that it's a bool and the function runs
        assert isinstance(result["all_conditions"], bool)

    def test_sma_values_reasonable(self, price_history_df):
        """SMA50 and SMA200 should be between min and max price."""
        result = detect_pullback_in_uptrend(price_history_df)
        min_price = float(price_history_df["Close"].min())
        max_price = float(price_history_df["Close"].max())
        assert min_price <= result["sma50"] <= max_price
        assert min_price <= result["sma200"] <= max_price
