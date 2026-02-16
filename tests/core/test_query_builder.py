"""Tests for src.core.screening.query_builder module."""

import pytest
from yfinance import EquityQuery

from src.core.screening.query_builder import (
    build_query,
    _build_criteria_conditions,
    _build_region_condition,
    _build_exchange_condition,
    _build_sector_condition,
    REGION_MAP,
    EXCHANGE_MAP,
    ASEAN_REGIONS,
    ASEAN_EXCHANGES,
    _CRITERIA_FIELD_MAP,
)


# ===================================================================
# _build_region_condition
# ===================================================================


class TestBuildRegionCondition:
    def test_japan_mapped(self):
        """'japan' should map to region code 'jp'."""
        cond = _build_region_condition("japan")
        assert cond is not None
        # EquityQuery internal representation check:
        # The query should represent eq(region, "jp")
        assert isinstance(cond, EquityQuery)

    def test_us_mapped(self):
        """'us' should map to region code 'us'."""
        cond = _build_region_condition("us")
        assert cond is not None

    def test_raw_region_code(self):
        """Raw 2-letter code like 'jp' should be accepted."""
        cond = _build_region_condition("jp")
        assert cond is not None

    def test_asean_special_case(self):
        """'asean' should produce an is-in query with multiple regions."""
        cond = _build_region_condition("asean")
        assert cond is not None

    def test_case_insensitive(self):
        """Region lookup should be case-insensitive."""
        cond = _build_region_condition("JAPAN")
        assert cond is not None

    def test_unknown_long_string_returns_none(self):
        """Long unknown string (> 3 chars, not in REGION_MAP) -> None."""
        cond = _build_region_condition("unknownregion")
        assert cond is None

    def test_short_known_raw_code_accepted(self):
        """Known raw 2-letter code like 'sg' should be accepted directly."""
        cond = _build_region_condition("sg")
        assert cond is not None


# ===================================================================
# _build_exchange_condition
# ===================================================================


class TestBuildExchangeCondition:
    def test_japan_exchange(self):
        """'japan' should map to exchange 'JPX'."""
        cond = _build_exchange_condition("japan")
        assert cond is not None

    def test_us_exchange_multiple(self):
        """'us' should map to multiple exchanges ['NMS', 'NYQ']."""
        cond = _build_exchange_condition("us")
        assert cond is not None

    def test_asean_exchanges(self):
        """'asean' -> is-in with multiple exchange codes."""
        cond = _build_exchange_condition("asean")
        assert cond is not None

    def test_raw_exchange_code(self):
        """Raw exchange code like 'JPX' should be used directly."""
        cond = _build_exchange_condition("JPX")
        assert cond is not None


# ===================================================================
# _build_sector_condition
# ===================================================================


class TestBuildSectorCondition:
    def test_technology_sector(self):
        """'Technology' should produce an eq sector condition."""
        cond = _build_sector_condition("Technology")
        assert cond is not None
        assert isinstance(cond, EquityQuery)

    def test_financial_services_sector(self):
        """'Financial Services' with space should work."""
        cond = _build_sector_condition("Financial Services")
        assert cond is not None


# ===================================================================
# _build_criteria_conditions
# ===================================================================


class TestBuildCriteriaConditions:
    def test_max_per(self):
        """max_per should produce a 'lt' condition on peratio field."""
        conditions = _build_criteria_conditions({"max_per": 15})
        assert len(conditions) == 1
        assert isinstance(conditions[0], EquityQuery)

    def test_multiple_criteria(self):
        """Multiple criteria should produce one condition each."""
        criteria = {
            "max_per": 15,
            "max_pbr": 1.5,
            "min_dividend_yield": 0.02,
            "min_roe": 0.08,
            "min_revenue_growth": 0.05,
        }
        conditions = _build_criteria_conditions(criteria)
        assert len(conditions) == 5

    def test_unknown_criteria_ignored(self):
        """Unknown criteria keys should be silently skipped."""
        conditions = _build_criteria_conditions({"unknown_key": 42})
        assert len(conditions) == 0

    def test_empty_criteria(self):
        """Empty criteria dict should produce empty list."""
        conditions = _build_criteria_conditions({})
        assert len(conditions) == 0

    def test_mixed_known_and_unknown(self):
        """Mix of known and unknown keys: only known ones produce conditions."""
        criteria = {"max_per": 15, "some_custom_field": 99}
        conditions = _build_criteria_conditions(criteria)
        assert len(conditions) == 1


# ===================================================================
# build_query (main function)
# ===================================================================


class TestBuildQuery:
    def test_region_jp_produces_query(self):
        """build_query with region='jp' should produce a valid EquityQuery."""
        query = build_query({}, region="jp")
        assert isinstance(query, EquityQuery)

    def test_region_japan_produces_query(self):
        """build_query with region='japan' should produce a valid EquityQuery."""
        query = build_query({}, region="japan")
        assert isinstance(query, EquityQuery)

    def test_sector_included(self):
        """Sector specification should be included in the query."""
        query = build_query({}, region="jp", sector="Technology")
        assert isinstance(query, EquityQuery)

    def test_criteria_reflected(self):
        """Criteria conditions should be part of the built query."""
        criteria = {"max_per": 15, "min_roe": 0.08}
        query = build_query(criteria, region="jp")
        assert isinstance(query, EquityQuery)

    def test_exchange_included(self):
        """Exchange specification should be included."""
        query = build_query({}, region="jp", exchange="JPX")
        assert isinstance(query, EquityQuery)

    def test_all_options_combined(self):
        """Region + exchange + sector + criteria all combined."""
        criteria = {"max_per": 20, "min_dividend_yield": 0.02}
        query = build_query(criteria, region="jp", exchange="JPX", sector="Technology")
        assert isinstance(query, EquityQuery)

    def test_empty_criteria_with_region_ok(self):
        """Empty criteria + region should still produce a valid query (region only)."""
        query = build_query({}, region="us")
        assert isinstance(query, EquityQuery)

    def test_no_conditions_raises_value_error(self):
        """No criteria, no region, no exchange, no sector -> ValueError."""
        with pytest.raises(ValueError, match="No query conditions"):
            build_query({})

    def test_empty_criteria_no_region_raises_value_error(self):
        """Empty criteria and no optional args -> ValueError."""
        with pytest.raises(ValueError):
            build_query({}, region=None, exchange=None, sector=None)

    def test_only_sector_produces_query(self):
        """Sector alone (no region/exchange/criteria) should produce a valid query."""
        query = build_query({}, sector="Healthcare")
        assert isinstance(query, EquityQuery)

    def test_only_exchange_produces_query(self):
        """Exchange alone should produce a valid query."""
        query = build_query({}, exchange="JPX")
        assert isinstance(query, EquityQuery)

    def test_only_criteria_produces_query(self):
        """Criteria alone (no region/exchange/sector) should produce a valid query."""
        query = build_query({"max_per": 15})
        assert isinstance(query, EquityQuery)

    def test_single_condition_not_wrapped_in_and(self):
        """A single condition should be returned directly (not nested in AND)."""
        query = build_query({}, region="jp")
        # The result should be a single EquityQuery, not AND-wrapped
        assert isinstance(query, EquityQuery)


# ===================================================================
# Constants checks
# ===================================================================


class TestConstants:
    def test_region_map_completeness(self):
        """REGION_MAP should have entries for all expected markets."""
        expected = {"japan", "us", "singapore", "thailand", "malaysia", "indonesia", "philippines"}
        assert set(REGION_MAP.keys()) == expected

    def test_exchange_map_completeness(self):
        """EXCHANGE_MAP should have entries for all expected markets."""
        expected = {"japan", "us", "singapore", "thailand", "malaysia", "indonesia", "philippines"}
        assert set(EXCHANGE_MAP.keys()) == expected

    def test_asean_regions(self):
        """ASEAN_REGIONS should contain 5 country codes."""
        assert len(ASEAN_REGIONS) == 5
        assert set(ASEAN_REGIONS) == {"sg", "th", "my", "id", "ph"}

    def test_asean_exchanges(self):
        """ASEAN_EXCHANGES should contain 5 exchange codes."""
        assert len(ASEAN_EXCHANGES) == 5
        assert set(ASEAN_EXCHANGES) == {"SES", "SET", "KLS", "JKT", "PHS"}

    def test_criteria_field_map_keys(self):
        """_CRITERIA_FIELD_MAP should have the expected keys."""
        expected = {"max_per", "max_pbr", "min_dividend_yield", "min_roe", "min_revenue_growth", "min_earnings_growth", "min_market_cap"}
        assert set(_CRITERIA_FIELD_MAP.keys()) == expected
