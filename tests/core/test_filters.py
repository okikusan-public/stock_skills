"""Tests for src/core/filters.py -- apply_filters()."""

from src.core.filters import apply_filters


# ===================================================================
# Basic pass / fail tests
# ===================================================================

class TestApplyFiltersPassFail:
    """Tests for apply_filters() pass/fail logic."""

    def test_stock_passes_all_criteria(self):
        """A stock meeting all criteria should pass."""
        stock = {
            "per": 10.0,
            "pbr": 0.8,
            "dividend_yield": 0.04,
            "roe": 0.12,
            "revenue_growth": 0.10,
        }
        criteria = {
            "max_per": 15,
            "max_pbr": 1.5,
            "min_dividend_yield": 0.02,
            "min_roe": 0.05,
            "min_revenue_growth": 0.05,
        }
        assert apply_filters(stock, criteria) is True

    def test_per_too_high_fails(self):
        """PER exceeding max_per should fail."""
        stock = {"per": 20.0, "pbr": 0.8}
        criteria = {"max_per": 15}
        assert apply_filters(stock, criteria) is False

    def test_pbr_too_high_fails(self):
        """PBR exceeding max_pbr should fail."""
        stock = {"per": 10.0, "pbr": 2.0}
        criteria = {"max_pbr": 1.5}
        assert apply_filters(stock, criteria) is False

    def test_dividend_too_low_fails(self):
        """Dividend yield below min_dividend_yield should fail."""
        stock = {"dividend_yield": 0.01}
        criteria = {"min_dividend_yield": 0.03}
        assert apply_filters(stock, criteria) is False

    def test_roe_too_low_fails(self):
        """ROE below min_roe should fail."""
        stock = {"roe": 0.03}
        criteria = {"min_roe": 0.05}
        assert apply_filters(stock, criteria) is False

    def test_revenue_growth_too_low_fails(self):
        """Revenue growth below min_revenue_growth should fail."""
        stock = {"revenue_growth": 0.02}
        criteria = {"min_revenue_growth": 0.05}
        assert apply_filters(stock, criteria) is False


# ===================================================================
# None handling tests
# ===================================================================

class TestApplyFiltersNoneHandling:
    """Tests for how apply_filters handles None values."""

    def test_none_per_skips_per_check(self):
        """If per is None, max_per criterion should be skipped (passes)."""
        stock = {"per": None, "pbr": 0.8}
        criteria = {"max_per": 15, "max_pbr": 1.5}
        assert apply_filters(stock, criteria) is True

    def test_none_pbr_skips_pbr_check(self):
        """If pbr is None, max_pbr criterion should be skipped."""
        stock = {"per": 10.0, "pbr": None}
        criteria = {"max_per": 15, "max_pbr": 1.5}
        assert apply_filters(stock, criteria) is True

    def test_all_none_passes(self):
        """If all values are None, all criteria are skipped -> passes."""
        stock = {
            "per": None,
            "pbr": None,
            "dividend_yield": None,
            "roe": None,
            "revenue_growth": None,
        }
        criteria = {
            "max_per": 15,
            "max_pbr": 1.5,
            "min_dividend_yield": 0.02,
            "min_roe": 0.05,
            "min_revenue_growth": 0.05,
        }
        assert apply_filters(stock, criteria) is True

    def test_missing_key_treated_as_none(self):
        """Missing key in stock dict should behave like None (skip)."""
        stock = {"per": 10.0}  # no pbr key at all
        criteria = {"max_per": 15, "max_pbr": 1.5}
        assert apply_filters(stock, criteria) is True

    def test_none_dividend_skips_check(self):
        """None dividend_yield should skip min_dividend_yield check."""
        stock = {"dividend_yield": None}
        criteria = {"min_dividend_yield": 0.03}
        assert apply_filters(stock, criteria) is True


# ===================================================================
# Empty / edge cases
# ===================================================================

class TestApplyFiltersEdgeCases:
    """Edge cases for apply_filters."""

    def test_empty_criteria_always_passes(self):
        """No criteria means everything passes."""
        stock = {"per": 100.0, "pbr": 50.0}
        assert apply_filters(stock, {}) is True

    def test_empty_stock_empty_criteria(self):
        """Both empty -> passes."""
        assert apply_filters({}, {}) is True

    def test_empty_stock_with_criteria_passes(self):
        """Empty stock dict with criteria -> all values are None -> passes."""
        criteria = {"max_per": 15, "max_pbr": 1.5}
        assert apply_filters({}, criteria) is True

    def test_unknown_criteria_key_ignored(self):
        """Criteria keys not in the checks list should be ignored."""
        stock = {"per": 10.0}
        criteria = {"max_per": 15, "unknown_criterion": 999}
        assert apply_filters(stock, criteria) is True


# ===================================================================
# Boundary value tests
# ===================================================================

class TestApplyFiltersBoundary:
    """Boundary value tests for apply_filters."""

    def test_per_exactly_at_max(self):
        """PER exactly at max_per should pass (not strictly greater)."""
        stock = {"per": 15.0}
        criteria = {"max_per": 15.0}
        assert apply_filters(stock, criteria) is True

    def test_per_just_above_max(self):
        """PER just above max_per should fail."""
        stock = {"per": 15.01}
        criteria = {"max_per": 15.0}
        assert apply_filters(stock, criteria) is False

    def test_dividend_exactly_at_min(self):
        """Dividend yield exactly at min should pass (not strictly less)."""
        stock = {"dividend_yield": 0.03}
        criteria = {"min_dividend_yield": 0.03}
        assert apply_filters(stock, criteria) is True

    def test_dividend_just_below_min(self):
        """Dividend yield just below min should fail."""
        stock = {"dividend_yield": 0.0299}
        criteria = {"min_dividend_yield": 0.03}
        assert apply_filters(stock, criteria) is False

    def test_roe_exactly_at_min(self):
        """ROE exactly at min should pass."""
        stock = {"roe": 0.05}
        criteria = {"min_roe": 0.05}
        assert apply_filters(stock, criteria) is True

    def test_pbr_exactly_at_max(self):
        """PBR exactly at max should pass."""
        stock = {"pbr": 1.5}
        criteria = {"max_pbr": 1.5}
        assert apply_filters(stock, criteria) is True

    def test_one_criterion_fails_rest_pass(self):
        """If any single criterion fails, the entire filter fails."""
        stock = {
            "per": 10.0,
            "pbr": 0.8,
            "dividend_yield": 0.01,  # This fails
            "roe": 0.12,
        }
        criteria = {
            "max_per": 15,
            "max_pbr": 1.5,
            "min_dividend_yield": 0.03,
            "min_roe": 0.05,
        }
        assert apply_filters(stock, criteria) is False


# ===================================================================
# Earnings growth filter tests (KIK-371)
# ===================================================================

class TestApplyFiltersEarningsGrowth:
    """Tests for min_earnings_growth filter."""

    def test_earnings_growth_passes(self):
        stock = {"earnings_growth": 0.15}
        criteria = {"min_earnings_growth": 0.10}
        assert apply_filters(stock, criteria) is True

    def test_earnings_growth_fails(self):
        stock = {"earnings_growth": 0.05}
        criteria = {"min_earnings_growth": 0.10}
        assert apply_filters(stock, criteria) is False

    def test_earnings_growth_none_skips(self):
        stock = {"earnings_growth": None}
        criteria = {"min_earnings_growth": 0.10}
        assert apply_filters(stock, criteria) is True

    def test_earnings_growth_exactly_at_min(self):
        stock = {"earnings_growth": 0.10}
        criteria = {"min_earnings_growth": 0.10}
        assert apply_filters(stock, criteria) is True


# ===================================================================
# Market cap filter tests (KIK-371)
# ===================================================================

class TestApplyFiltersMarketCap:
    """Tests for min_market_cap filter."""

    def test_market_cap_passes(self):
        stock = {"market_cap": 200_000_000_000}
        criteria = {"min_market_cap": 100_000_000_000}
        assert apply_filters(stock, criteria) is True

    def test_market_cap_fails(self):
        stock = {"market_cap": 50_000_000_000}
        criteria = {"min_market_cap": 100_000_000_000}
        assert apply_filters(stock, criteria) is False

    def test_market_cap_none_skips(self):
        stock = {"market_cap": None}
        criteria = {"min_market_cap": 100_000_000_000}
        assert apply_filters(stock, criteria) is True

    def test_market_cap_exactly_at_min(self):
        stock = {"market_cap": 100_000_000_000}
        criteria = {"min_market_cap": 100_000_000_000}
        assert apply_filters(stock, criteria) is True


# ===================================================================
# Total shareholder return filter tests (KIK-378)
# ===================================================================

class TestApplyFiltersTotalShareholderReturn:
    """Tests for min_total_shareholder_return filter."""

    def test_shareholder_return_passes(self):
        stock = {"total_shareholder_return": 0.07}
        criteria = {"min_total_shareholder_return": 0.05}
        assert apply_filters(stock, criteria) is True

    def test_shareholder_return_fails(self):
        stock = {"total_shareholder_return": 0.03}
        criteria = {"min_total_shareholder_return": 0.05}
        assert apply_filters(stock, criteria) is False

    def test_shareholder_return_none_skips(self):
        stock = {"total_shareholder_return": None}
        criteria = {"min_total_shareholder_return": 0.05}
        assert apply_filters(stock, criteria) is True

    def test_shareholder_return_exactly_at_min(self):
        stock = {"total_shareholder_return": 0.05}
        criteria = {"min_total_shareholder_return": 0.05}
        assert apply_filters(stock, criteria) is True
