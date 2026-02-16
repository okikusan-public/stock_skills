"""Tests for src/core/correlation.py -- correlation, factor decomposition, VaR."""

import math
import pytest
import numpy as np

from src.core.risk.correlation import (
    _compute_daily_returns,
    _safe_float,
    compute_correlation_matrix,
    find_high_correlation_pairs,
    decompose_factors,
    compute_var,
    _empty_var,
    _empty_factor_result,
    MACRO_FACTORS,
)


# ===================================================================
# _compute_daily_returns tests
# ===================================================================

class TestComputeDailyReturns:
    """Tests for _compute_daily_returns()."""

    def test_simple_returns(self):
        """Basic daily return calculation."""
        prices = [100, 110, 105]
        returns = _compute_daily_returns(prices)
        assert len(returns) == 2
        assert returns[0] == pytest.approx(0.10, abs=1e-9)
        assert returns[1] == pytest.approx(-0.04545, abs=1e-4)

    def test_single_price(self):
        """Single price -> empty returns."""
        assert _compute_daily_returns([100]) == []

    def test_empty_prices(self):
        """Empty list -> empty returns."""
        assert _compute_daily_returns([]) == []

    def test_zero_price_skipped(self):
        """Zero price should be skipped to avoid division by zero."""
        prices = [0, 100, 110]
        returns = _compute_daily_returns(prices)
        # First return skipped (0 price), second is (110-100)/100 = 0.1
        assert len(returns) == 1
        assert returns[0] == pytest.approx(0.10)

    def test_constant_prices(self):
        """Constant prices -> all zero returns."""
        prices = [50, 50, 50, 50]
        returns = _compute_daily_returns(prices)
        assert all(r == 0.0 for r in returns)


# ===================================================================
# _safe_float tests
# ===================================================================

class TestSafeFloat:
    """Tests for _safe_float()."""

    def test_normal_value(self):
        assert _safe_float(3.14) == 3.14

    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0
        assert _safe_float(None, default=1.0) == 1.0

    def test_nan_returns_default(self):
        assert _safe_float(float("nan")) == 0.0

    def test_inf_returns_default(self):
        assert _safe_float(float("inf")) == 0.0

    def test_string_returns_default(self):
        assert _safe_float("abc") == 0.0


# ===================================================================
# compute_correlation_matrix tests
# ===================================================================

class TestComputeCorrelationMatrix:
    """Tests for compute_correlation_matrix()."""

    def _make_portfolio(self, n_stocks=3, n_days=100, seed=42):
        """Generate synthetic portfolio data with price histories."""
        rng = np.random.RandomState(seed)
        stocks = []
        for i in range(n_stocks):
            base = 100 + i * 50
            # Random walk
            returns = rng.normal(0.001, 0.02, n_days)
            prices = [base]
            for r in returns:
                prices.append(prices[-1] * (1 + r))
            stocks.append({
                "symbol": f"STOCK{i}",
                "price_history": prices,
            })
        return stocks

    def test_basic_correlation_matrix(self):
        """Matrix should be NxN with 1.0 on diagonal."""
        portfolio = self._make_portfolio(3, 100)
        result = compute_correlation_matrix(portfolio)

        assert "symbols" in result
        assert "matrix" in result
        assert len(result["symbols"]) == 3
        matrix = result["matrix"]
        assert len(matrix) == 3
        for i in range(3):
            assert len(matrix[i]) == 3
            assert matrix[i][i] == 1.0

    def test_symmetric_matrix(self):
        """Correlation matrix should be symmetric."""
        portfolio = self._make_portfolio(4, 100)
        result = compute_correlation_matrix(portfolio)
        matrix = result["matrix"]
        for i in range(4):
            for j in range(4):
                assert matrix[i][j] == matrix[j][i]

    def test_values_in_range(self):
        """All correlations should be between -1 and 1."""
        portfolio = self._make_portfolio(5, 200)
        result = compute_correlation_matrix(portfolio)
        matrix = result["matrix"]
        for i in range(5):
            for j in range(5):
                v = matrix[i][j]
                if not math.isnan(v):
                    assert -1.0 <= v <= 1.0

    def test_perfectly_correlated_stocks(self):
        """Identical price histories should have correlation 1.0."""
        prices = list(range(100, 200))
        portfolio = [
            {"symbol": "A", "price_history": prices},
            {"symbol": "B", "price_history": prices},
        ]
        result = compute_correlation_matrix(portfolio)
        matrix = result["matrix"]
        assert matrix[0][1] == pytest.approx(1.0, abs=0.001)

    def test_single_stock(self):
        """Single stock portfolio returns 1x1 matrix."""
        portfolio = [{"symbol": "A", "price_history": list(range(100, 200))}]
        result = compute_correlation_matrix(portfolio)
        assert result["matrix"] == [[1.0]]

    def test_insufficient_data(self):
        """Short price history -> NaN correlation."""
        portfolio = [
            {"symbol": "A", "price_history": [100, 101, 102]},
            {"symbol": "B", "price_history": [50, 51, 52]},
        ]
        result = compute_correlation_matrix(portfolio)
        matrix = result["matrix"]
        # With only 2 returns, below 30-day threshold -> NaN
        assert math.isnan(matrix[0][1])

    def test_empty_portfolio(self):
        """Empty portfolio returns empty result."""
        result = compute_correlation_matrix([])
        assert result["symbols"] == []
        assert result["matrix"] == []


# ===================================================================
# find_high_correlation_pairs tests
# ===================================================================

class TestFindHighCorrelationPairs:
    """Tests for find_high_correlation_pairs()."""

    def test_finds_high_pairs(self):
        """Should detect pairs above threshold."""
        corr_result = {
            "symbols": ["A", "B", "C"],
            "matrix": [
                [1.0, 0.85, 0.30],
                [0.85, 1.0, 0.10],
                [0.30, 0.10, 1.0],
            ],
        }
        pairs = find_high_correlation_pairs(corr_result, threshold=0.7)
        assert len(pairs) == 1
        assert pairs[0]["pair"] == ["A", "B"]
        assert pairs[0]["correlation"] == 0.85

    def test_no_high_pairs(self):
        """No pairs above threshold returns empty list."""
        corr_result = {
            "symbols": ["A", "B"],
            "matrix": [[1.0, 0.50], [0.50, 1.0]],
        }
        pairs = find_high_correlation_pairs(corr_result, threshold=0.7)
        assert pairs == []

    def test_negative_correlation(self):
        """Negative correlation above threshold detected."""
        corr_result = {
            "symbols": ["A", "B"],
            "matrix": [[1.0, -0.80], [-0.80, 1.0]],
        }
        pairs = find_high_correlation_pairs(corr_result, threshold=0.7)
        assert len(pairs) == 1
        assert pairs[0]["correlation"] == -0.80
        assert "逆相関" in pairs[0]["label"]

    def test_sorted_by_absolute_correlation(self):
        """Pairs should be sorted by descending absolute correlation."""
        corr_result = {
            "symbols": ["A", "B", "C"],
            "matrix": [
                [1.0, 0.75, 0.90],
                [0.75, 1.0, 0.80],
                [0.90, 0.80, 1.0],
            ],
        }
        pairs = find_high_correlation_pairs(corr_result, threshold=0.7)
        assert len(pairs) == 3
        assert pairs[0]["correlation"] == 0.90  # A-C
        assert pairs[1]["correlation"] == 0.80  # B-C
        assert pairs[2]["correlation"] == 0.75  # A-B

    def test_nan_values_skipped(self):
        """NaN correlations should be skipped."""
        corr_result = {
            "symbols": ["A", "B"],
            "matrix": [[1.0, float("nan")], [float("nan"), 1.0]],
        }
        pairs = find_high_correlation_pairs(corr_result, threshold=0.7)
        assert pairs == []

    def test_label_very_strong(self):
        """r >= 0.85 should get 'very strong' label."""
        corr_result = {
            "symbols": ["A", "B"],
            "matrix": [[1.0, 0.90], [0.90, 1.0]],
        }
        pairs = find_high_correlation_pairs(corr_result, threshold=0.7)
        assert "非常に強い" in pairs[0]["label"]

    def test_custom_threshold(self):
        """Custom threshold should be respected."""
        corr_result = {
            "symbols": ["A", "B"],
            "matrix": [[1.0, 0.50], [0.50, 1.0]],
        }
        pairs = find_high_correlation_pairs(corr_result, threshold=0.4)
        assert len(pairs) == 1


# ===================================================================
# decompose_factors tests
# ===================================================================

class TestDecomposeFactors:
    """Tests for decompose_factors()."""

    def _make_data(self, n_days=100, seed=42):
        """Generate stock + factor data for testing."""
        rng = np.random.RandomState(seed)
        # Stock with known factor exposure
        factor_prices = [100.0]
        for _ in range(n_days):
            factor_prices.append(factor_prices[-1] * (1 + rng.normal(0.001, 0.01)))

        # Stock = 1.5 * factor + noise
        stock_prices = [200.0]
        factor_returns = []
        for i in range(n_days):
            fr = (factor_prices[i + 1] - factor_prices[i]) / factor_prices[i]
            factor_returns.append(fr)
            noise = rng.normal(0, 0.005)
            stock_prices.append(stock_prices[-1] * (1 + 1.5 * fr + noise))

        portfolio = [{"symbol": "TEST", "price_history": stock_prices}]
        factor_histories = {"^GSPC": factor_prices}
        return portfolio, factor_histories

    def test_basic_factor_decomposition(self):
        """Should return results with expected structure."""
        portfolio, factor_histories = self._make_data()
        results = decompose_factors(portfolio, factor_histories)
        assert len(results) == 1
        r = results[0]
        assert r["symbol"] == "TEST"
        assert "factors" in r
        assert "r_squared" in r
        assert "residual_std" in r

    def test_r_squared_positive(self):
        """R² should be positive for a stock with known factor exposure."""
        portfolio, factor_histories = self._make_data()
        results = decompose_factors(portfolio, factor_histories)
        assert results[0]["r_squared"] > 0.1  # should have meaningful R²

    def test_insufficient_data(self):
        """Short data should return empty factor result."""
        portfolio = [{"symbol": "TEST", "price_history": [100, 101]}]
        factor_histories = {"^GSPC": [100, 101]}
        results = decompose_factors(portfolio, factor_histories)
        assert results[0]["factors"] == []
        assert results[0]["r_squared"] == 0.0

    def test_no_factor_data(self):
        """Empty factor histories should return empty result."""
        portfolio = [{"symbol": "TEST", "price_history": list(range(100, 200))}]
        results = decompose_factors(portfolio, {})
        assert results[0]["factors"] == []

    def test_multiple_stocks(self):
        """Should return one result per stock."""
        rng = np.random.RandomState(42)
        portfolio = []
        for i in range(3):
            prices = [100.0]
            for _ in range(100):
                prices.append(prices[-1] * (1 + rng.normal(0.001, 0.02)))
            portfolio.append({"symbol": f"S{i}", "price_history": prices})

        factor_prices = [100.0]
        for _ in range(100):
            factor_prices.append(factor_prices[-1] * (1 + rng.normal(0, 0.01)))

        results = decompose_factors(portfolio, {"^N225": factor_prices})
        assert len(results) == 3

    def test_factors_sorted_by_contribution(self):
        """Factors should be sorted by descending contribution."""
        portfolio, factor_histories = self._make_data()
        results = decompose_factors(portfolio, factor_histories)
        factors = results[0]["factors"]
        if len(factors) > 1:
            for i in range(len(factors) - 1):
                assert abs(factors[i]["contribution"]) >= abs(factors[i + 1]["contribution"])

    def test_constant_factor_column_skipped(self):
        """Factor with zero variance (constant prices) should be skipped without error (KIK-353)."""
        rng = np.random.RandomState(42)
        stock_prices = [100.0]
        for _ in range(100):
            stock_prices.append(stock_prices[-1] * (1 + rng.normal(0.001, 0.01)))

        # One normal factor, one constant factor
        normal_factor = [100.0]
        for _ in range(100):
            normal_factor.append(normal_factor[-1] * (1 + rng.normal(0, 0.01)))

        constant_factor = [50.0] * 101  # constant -> zero variance returns

        portfolio = [{"symbol": "TEST", "price_history": stock_prices}]
        factor_histories = {"^GSPC": normal_factor, "CL=F": constant_factor}
        results = decompose_factors(portfolio, factor_histories)
        assert len(results) == 1
        # Should not crash; should have result with at least the normal factor
        assert results[0]["symbol"] == "TEST"
        factor_names = [f["symbol"] for f in results[0]["factors"]]
        assert "CL=F" not in factor_names  # constant factor filtered out

    def test_all_constant_factors_returns_empty(self):
        """When all factors are constant, should return empty result (KIK-353)."""
        rng = np.random.RandomState(42)
        stock_prices = [100.0]
        for _ in range(100):
            stock_prices.append(stock_prices[-1] * (1 + rng.normal(0.001, 0.01)))

        portfolio = [{"symbol": "TEST", "price_history": stock_prices}]
        factor_histories = {
            "^GSPC": [100.0] * 101,
            "^N225": [200.0] * 101,
        }
        results = decompose_factors(portfolio, factor_histories)
        assert results[0]["factors"] == []
        assert results[0]["r_squared"] == 0.0

    def test_zero_variance_stock_returns_empty(self):
        """Stock with zero variance returns should return empty result (KIK-353)."""
        rng = np.random.RandomState(42)
        factor_prices = [100.0]
        for _ in range(100):
            factor_prices.append(factor_prices[-1] * (1 + rng.normal(0, 0.01)))

        # Stock with constant price -> zero variance returns
        portfolio = [{"symbol": "TEST", "price_history": [100.0] * 101}]
        factor_histories = {"^GSPC": factor_prices}
        results = decompose_factors(portfolio, factor_histories)
        assert results[0]["factors"] == []


# ===================================================================
# compute_var tests
# ===================================================================

class TestComputeVar:
    """Tests for compute_var()."""

    def _make_portfolio(self, n_stocks=2, n_days=200, seed=42):
        """Generate portfolio data for VaR testing."""
        rng = np.random.RandomState(seed)
        stocks = []
        for i in range(n_stocks):
            prices = [100.0]
            for _ in range(n_days):
                prices.append(prices[-1] * (1 + rng.normal(0.0005, 0.015)))
            stocks.append({
                "symbol": f"S{i}",
                "price_history": prices,
            })
        weights = [1.0 / n_stocks] * n_stocks
        return stocks, weights

    def test_basic_var_structure(self):
        """VaR result should have expected keys."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights)

        assert "daily_var" in result
        assert "monthly_var" in result
        assert "portfolio_volatility" in result
        assert "observation_days" in result

    def test_var_is_negative(self):
        """VaR (loss) should be negative."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights)
        for cl in [0.95, 0.99]:
            assert result["daily_var"][cl] < 0
            assert result["monthly_var"][cl] < 0

    def test_99_var_worse_than_95(self):
        """99% VaR should be more extreme than 95% VaR."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights)
        assert result["daily_var"][0.99] < result["daily_var"][0.95]
        assert result["monthly_var"][0.99] < result["monthly_var"][0.95]

    def test_monthly_var_worse_than_daily(self):
        """Monthly VaR should be more extreme than daily VaR."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights)
        for cl in [0.95, 0.99]:
            assert result["monthly_var"][cl] < result["daily_var"][cl]

    def test_var_with_total_value(self):
        """When total_value is provided, amount VaR should be present."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights, total_value=10_000_000)

        assert "daily_var_amount" in result
        assert "monthly_var_amount" in result
        assert result["daily_var_amount"][0.95] < 0
        assert result["total_value"] == 10_000_000

    def test_var_without_total_value(self):
        """When total_value is None, amount fields should be absent."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights, total_value=None)
        assert "daily_var_amount" not in result

    def test_insufficient_data(self):
        """Short data should return empty VaR."""
        stocks = [
            {"symbol": "A", "price_history": [100, 101, 102]},
            {"symbol": "B", "price_history": [50, 51, 52]},
        ]
        result = compute_var(stocks, [0.5, 0.5])
        assert result["observation_days"] == 0
        assert result["daily_var"] == {}

    def test_empty_portfolio(self):
        """Empty portfolio returns empty VaR."""
        result = compute_var([], [])
        assert result["observation_days"] == 0

    def test_observation_days(self):
        """Observation days should match aligned data length."""
        stocks = [
            {"symbol": "A", "price_history": list(range(100, 200))},  # 99 returns
            {"symbol": "B", "price_history": list(range(100, 180))},  # 79 returns
        ]
        result = compute_var(stocks, [0.5, 0.5])
        assert result["observation_days"] == 79

    def test_portfolio_volatility_positive(self):
        """Portfolio volatility should be positive."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights)
        assert result["portfolio_volatility"] > 0

    def test_custom_confidence_levels(self):
        """Custom confidence levels should be used."""
        stocks, weights = self._make_portfolio()
        result = compute_var(stocks, weights, confidence_levels=(0.90, 0.95))
        assert 0.90 in result["daily_var"]
        assert 0.95 in result["daily_var"]
        assert 0.99 not in result["daily_var"]


# ===================================================================
# _empty_var / _empty_factor_result tests
# ===================================================================

class TestEmptyResults:
    """Tests for empty result helpers."""

    def test_empty_var_structure(self):
        result = _empty_var()
        assert result["daily_var"] == {}
        assert result["monthly_var"] == {}
        assert result["portfolio_volatility"] == 0.0
        assert result["observation_days"] == 0

    def test_empty_factor_result_structure(self):
        result = _empty_factor_result("TEST")
        assert result["symbol"] == "TEST"
        assert result["factors"] == []
        assert result["r_squared"] == 0.0
        assert result["residual_std"] == 0.0


# ===================================================================
# MACRO_FACTORS constant test
# ===================================================================

class TestMacroFactors:
    """Tests for MACRO_FACTORS constant."""

    def test_has_expected_factors(self):
        symbols = [f["symbol"] for f in MACRO_FACTORS]
        assert "USDJPY=X" in symbols
        assert "^N225" in symbols
        assert "^GSPC" in symbols
        assert "CL=F" in symbols
        assert "^TNX" in symbols

    def test_each_factor_has_name_and_symbol(self):
        for f in MACRO_FACTORS:
            assert "symbol" in f
            assert "name" in f
