"""Tests for KIK-602: market-darling preset (high-PER, EPS rapid growth, large-cap)."""

import pytest
import yaml
from pathlib import Path
from yfinance import EquityQuery

from src.core.screening.query_builder import (
    load_preset,
    build_query,
    _build_criteria_conditions,
    _CRITERIA_FIELD_MAP,
)
from src.core.screening.filters import apply_filters


# ===================================================================
# Preset definition tests
# ===================================================================


class TestMarketDarlingPresetExists:
    """Verify market-darling preset is defined in screening_presets.yaml."""

    def test_preset_exists_in_yaml(self):
        """market-darling should be loadable from screening_presets.yaml."""
        criteria = load_preset("market-darling")
        assert isinstance(criteria, dict)
        assert len(criteria) > 0

    def test_preset_has_min_per(self):
        """market-darling should require min_per >= 30."""
        criteria = load_preset("market-darling")
        assert criteria.get("min_per") == 30

    def test_preset_has_min_earnings_growth(self):
        """market-darling should require min_earnings_growth >= 0.30."""
        criteria = load_preset("market-darling")
        assert criteria.get("min_earnings_growth") == 0.30

    def test_preset_has_min_revenue_growth(self):
        """market-darling should require min_revenue_growth >= 0.15."""
        criteria = load_preset("market-darling")
        assert criteria.get("min_revenue_growth") == 0.15

    def test_preset_has_max_psr(self):
        """market-darling should cap PSR at 30."""
        criteria = load_preset("market-darling")
        assert criteria.get("max_psr") == 30.0

    def test_preset_has_min_gross_margin(self):
        """market-darling should require min_gross_margin >= 0.20."""
        criteria = load_preset("market-darling")
        assert criteria.get("min_gross_margin") == 0.20

    def test_preset_has_min_market_cap(self):
        """market-darling should require min_market_cap >= 50B."""
        criteria = load_preset("market-darling")
        assert criteria.get("min_market_cap") == 50_000_000_000


# ===================================================================
# min_per in _CRITERIA_FIELD_MAP
# ===================================================================


class TestMinPerInCriteriaFieldMap:
    """Verify min_per is correctly mapped in query_builder."""

    def test_min_per_present(self):
        """min_per should be in _CRITERIA_FIELD_MAP."""
        assert "min_per" in _CRITERIA_FIELD_MAP

    def test_min_per_uses_gt_operator(self):
        """min_per should use 'gt' operator (greater-than)."""
        field, op = _CRITERIA_FIELD_MAP["min_per"]
        assert op == "gt"

    def test_min_per_uses_peratio_field(self):
        """min_per should use the same peratio field as max_per."""
        min_field, _ = _CRITERIA_FIELD_MAP["min_per"]
        max_field, _ = _CRITERIA_FIELD_MAP["max_per"]
        assert min_field == max_field

    def test_min_per_symmetric_with_max_per(self):
        """min_per (gt) and max_per (lt) should be symmetric on same field."""
        min_field, min_op = _CRITERIA_FIELD_MAP["min_per"]
        max_field, max_op = _CRITERIA_FIELD_MAP["max_per"]
        assert min_field == max_field
        assert min_op == "gt"
        assert max_op == "lt"

    def test_build_criteria_conditions_min_per(self):
        """_build_criteria_conditions with min_per should produce 1 condition."""
        conditions = _build_criteria_conditions({"min_per": 30})
        assert len(conditions) == 1
        assert isinstance(conditions[0], EquityQuery)


# ===================================================================
# min_per filter in apply_filters
# ===================================================================


class TestMinPerFilter:
    """Tests for min_per in apply_filters (local filter)."""

    def test_per_above_min_passes(self):
        """PER 50 should pass min_per 30."""
        stock = {"per": 50.0}
        criteria = {"min_per": 30}
        assert apply_filters(stock, criteria) is True

    def test_per_below_min_fails(self):
        """PER 20 should fail min_per 30."""
        stock = {"per": 20.0}
        criteria = {"min_per": 30}
        assert apply_filters(stock, criteria) is False

    def test_per_exactly_at_min_passes(self):
        """PER exactly at min_per should pass (not strictly less)."""
        stock = {"per": 30.0}
        criteria = {"min_per": 30.0}
        assert apply_filters(stock, criteria) is True

    def test_per_just_below_min_fails(self):
        """PER just below min_per should fail."""
        stock = {"per": 29.99}
        criteria = {"min_per": 30.0}
        assert apply_filters(stock, criteria) is False

    def test_per_none_skips_min_per_check(self):
        """None PER should skip min_per check (pass)."""
        stock = {"per": None}
        criteria = {"min_per": 30}
        assert apply_filters(stock, criteria) is True

    def test_per_missing_skips_min_per_check(self):
        """Missing per key should skip min_per check (pass)."""
        stock = {}
        criteria = {"min_per": 30}
        assert apply_filters(stock, criteria) is True


# ===================================================================
# max_market_cap / max_psr / min_gross_margin filters
# ===================================================================


class TestAdditionalFilters:
    """Tests for max_market_cap, max_psr, min_gross_margin filters."""

    def test_max_market_cap_passes(self):
        stock = {"market_cap": 50_000_000_000}
        criteria = {"max_market_cap": 100_000_000_000}
        assert apply_filters(stock, criteria) is True

    def test_max_market_cap_fails(self):
        stock = {"market_cap": 200_000_000_000}
        criteria = {"max_market_cap": 100_000_000_000}
        assert apply_filters(stock, criteria) is False

    def test_max_psr_passes(self):
        stock = {"psr": 15.0}
        criteria = {"max_psr": 30.0}
        assert apply_filters(stock, criteria) is True

    def test_max_psr_fails(self):
        stock = {"psr": 35.0}
        criteria = {"max_psr": 30.0}
        assert apply_filters(stock, criteria) is False

    def test_min_gross_margin_passes(self):
        stock = {"gross_margin": 0.40}
        criteria = {"min_gross_margin": 0.20}
        assert apply_filters(stock, criteria) is True

    def test_min_gross_margin_fails(self):
        stock = {"gross_margin": 0.10}
        criteria = {"min_gross_margin": 0.20}
        assert apply_filters(stock, criteria) is False


# ===================================================================
# build_query integration with market-darling preset
# ===================================================================


class TestBuildQueryMarketDarling:
    """Integration test: build_query with market-darling preset criteria."""

    def test_build_query_with_market_darling_criteria(self):
        """build_query with full market-darling criteria should produce EquityQuery."""
        criteria = load_preset("market-darling")
        query = build_query(criteria, region="us")
        assert isinstance(query, EquityQuery)

    def test_build_query_market_darling_japan(self):
        """market-darling preset should work with japan region."""
        criteria = load_preset("market-darling")
        query = build_query(criteria, region="japan")
        assert isinstance(query, EquityQuery)


# ===================================================================
# Full market-darling filter integration
# ===================================================================


class TestMarketDarlingFilterIntegration:
    """End-to-end filter tests simulating market-darling screening."""

    def test_ideal_market_darling_passes(self):
        """A stock meeting all market-darling criteria should pass."""
        stock = {
            "per": 50.0,
            "earnings_growth": 0.45,
            "revenue_growth": 0.25,
            "psr": 15.0,
            "gross_margin": 0.35,
            "market_cap": 100_000_000_000,
        }
        criteria = load_preset("market-darling")
        assert apply_filters(stock, criteria) is True

    def test_low_per_stock_rejected(self):
        """A low PER stock (value stock) should be rejected by market-darling."""
        stock = {
            "per": 10.0,  # too low
            "earnings_growth": 0.45,
            "revenue_growth": 0.25,
            "psr": 15.0,
            "gross_margin": 0.35,
            "market_cap": 100_000_000_000,
        }
        criteria = load_preset("market-darling")
        assert apply_filters(stock, criteria) is False

    def test_slow_growth_stock_rejected(self):
        """A stock with slow earnings growth should be rejected."""
        stock = {
            "per": 50.0,
            "earnings_growth": 0.10,  # too low
            "revenue_growth": 0.25,
            "psr": 15.0,
            "gross_margin": 0.35,
            "market_cap": 100_000_000_000,
        }
        criteria = load_preset("market-darling")
        assert apply_filters(stock, criteria) is False

    def test_small_cap_rejected(self):
        """A small-cap stock should be rejected by market-darling."""
        stock = {
            "per": 50.0,
            "earnings_growth": 0.45,
            "revenue_growth": 0.25,
            "psr": 15.0,
            "gross_margin": 0.35,
            "market_cap": 10_000_000_000,  # too small
        }
        criteria = load_preset("market-darling")
        assert apply_filters(stock, criteria) is False
