"""Tests for src.core.screening.screener module."""

import pytest

from src.core.screening.screener import QueryScreener, PullbackScreener


# ===================================================================
# QueryScreener._normalize_quote
# ===================================================================


class TestNormalizeQuote:
    def test_basic_field_mapping(self):
        """trailingPE -> per, priceToBook -> pbr, etc."""
        quote = {
            "symbol": "7203.T",
            "shortName": "Toyota Motor",
            "sector": "Consumer Cyclical",
            "industry": "Auto Manufacturers",
            "currency": "JPY",
            "regularMarketPrice": 2850.0,
            "marketCap": 30_000_000_000_000,
            "trailingPE": 10.5,
            "forwardPE": 9.8,
            "priceToBook": 0.95,
            "returnOnEquity": 0.12,
            "dividendYield": 2.52,  # yfinance percentage: 2.52%
            "revenueGrowth": 0.08,
            "earningsGrowth": 0.15,
            "exchange": "JPX",
        }
        result = QueryScreener._normalize_quote(quote)

        assert result["symbol"] == "7203.T"
        assert result["name"] == "Toyota Motor"
        assert result["per"] == 10.5
        assert result["forward_per"] == 9.8
        assert result["pbr"] == 0.95
        assert result["roe"] == 0.12
        assert result["dividend_yield"] == pytest.approx(0.0252)
        assert result["price"] == 2850.0
        assert result["market_cap"] == 30_000_000_000_000
        assert result["sector"] == "Consumer Cyclical"
        assert result["exchange"] == "JPX"

    def test_dividend_yield_percentage_normalization(self):
        """dividendYield is always a percentage -> divided by 100."""
        quote = {"dividendYield": 3.5}  # 3.5%
        result = QueryScreener._normalize_quote(quote)
        assert result["dividend_yield"] == pytest.approx(0.035)

    def test_dividend_yield_sub_one_percent(self):
        """Sub-1% yields (e.g. AAPL 0.41%) are correctly converted."""
        quote = {"dividendYield": 0.41}  # 0.41%
        result = QueryScreener._normalize_quote(quote)
        assert result["dividend_yield"] == pytest.approx(0.0041)

    def test_dividend_yield_none(self):
        """If dividendYield is None, dividend_yield should be None."""
        quote = {"dividendYield": None}
        result = QueryScreener._normalize_quote(quote)
        assert result["dividend_yield"] is None

    def test_dividend_yield_missing(self):
        """If dividendYield key is absent, dividend_yield should be None."""
        quote = {}
        result = QueryScreener._normalize_quote(quote)
        assert result["dividend_yield"] is None

    def test_roe_percentage_normalization(self):
        """returnOnEquity > 1 should be divided by 100."""
        quote = {"returnOnEquity": 12.5}  # 12.5% as percentage
        result = QueryScreener._normalize_quote(quote)
        assert result["roe"] == pytest.approx(0.125)

    def test_roe_ratio_preserved(self):
        """returnOnEquity <= 1 stays as-is."""
        quote = {"returnOnEquity": 0.15}
        result = QueryScreener._normalize_quote(quote)
        assert result["roe"] == 0.15

    def test_revenue_growth_percentage_normalization(self):
        """revenueGrowth with abs > 5 should be divided by 100."""
        quote = {"revenueGrowth": 15.0}  # 15% as percentage
        result = QueryScreener._normalize_quote(quote)
        assert result["revenue_growth"] == pytest.approx(0.15)

    def test_revenue_growth_ratio_preserved(self):
        """revenueGrowth with abs <= 5 stays as-is (could be 500% growth)."""
        quote = {"revenueGrowth": 0.08}
        result = QueryScreener._normalize_quote(quote)
        assert result["revenue_growth"] == 0.08

    def test_none_fields_handled(self):
        """All None fields should not cause errors and pass through as None."""
        quote = {
            "symbol": "TEST",
            "trailingPE": None,
            "priceToBook": None,
            "dividendYield": None,
            "returnOnEquity": None,
            "revenueGrowth": None,
            "earningsGrowth": None,
            "regularMarketPrice": None,
        }
        result = QueryScreener._normalize_quote(quote)

        assert result["symbol"] == "TEST"
        assert result["per"] is None
        assert result["pbr"] is None
        assert result["dividend_yield"] is None
        assert result["roe"] is None
        assert result["revenue_growth"] is None
        assert result["price"] is None

    def test_longname_fallback(self):
        """If shortName is missing, longName should be used."""
        quote = {"longName": "Toyota Motor Corporation", "shortName": None}
        result = QueryScreener._normalize_quote(quote)
        assert result["name"] == "Toyota Motor Corporation"

    def test_shortname_priority(self):
        """shortName takes priority over longName."""
        quote = {"shortName": "Toyota", "longName": "Toyota Motor Corporation"}
        result = QueryScreener._normalize_quote(quote)
        assert result["name"] == "Toyota"

    def test_empty_quote(self):
        """Empty dict should produce a result with None/empty values without error."""
        result = QueryScreener._normalize_quote({})
        assert result["symbol"] == ""
        assert result["name"] is None
        assert result["per"] is None
        assert result["pbr"] is None

    def test_negative_revenue_growth_normalization(self):
        """Negative revenueGrowth with abs > 5 should also be normalized."""
        quote = {"revenueGrowth": -10.0}  # -10% as percentage
        result = QueryScreener._normalize_quote(quote)
        assert result["revenue_growth"] == pytest.approx(-0.10)


# ===================================================================
# PullbackScreener.DEFAULT_CRITERIA
# ===================================================================


class TestPullbackScreenerDefaults:
    def test_default_criteria_values(self):
        """DEFAULT_CRITERIA should have the expected keys and values."""
        expected = {
            "max_per": 20,
            "min_roe": 0.08,
            "min_revenue_growth": 0.05,
        }
        assert PullbackScreener.DEFAULT_CRITERIA == expected

    def test_default_criteria_keys(self):
        """DEFAULT_CRITERIA should contain exactly the expected keys."""
        expected_keys = {"max_per", "min_roe", "min_revenue_growth"}
        assert set(PullbackScreener.DEFAULT_CRITERIA.keys()) == expected_keys

    def test_default_criteria_is_not_mutated_across_instances(self):
        """Accessing DEFAULT_CRITERIA from different instances should be the same."""
        # Create a mock yahoo_client
        class MockClient:
            pass

        s1 = PullbackScreener(MockClient())
        s2 = PullbackScreener(MockClient())
        assert s1.DEFAULT_CRITERIA is s2.DEFAULT_CRITERIA


# ===================================================================
# _normalize_quote anomaly guards
# ===================================================================


class TestNormalizeQuoteAnomalyGuard:
    """Tests for anomaly value guards in _normalize_quote()."""

    def test_extreme_dividend_yield_sanitized(self):
        quote = {"dividendYield": 20.0}  # 20% -> /100 -> 0.20 > 0.15 -> None
        assert QueryScreener._normalize_quote(quote)["dividend_yield"] is None

    def test_extreme_dividend_yield_special_div_sanitized(self):
        quote = {"dividendYield": 78.0}  # 78% -> /100 -> 0.78 -> sanitized
        assert QueryScreener._normalize_quote(quote)["dividend_yield"] is None

    def test_normal_dividend_yield_preserved(self):
        quote = {"dividendYield": 3.5}  # 3.5% -> /100 -> 0.035
        assert QueryScreener._normalize_quote(quote)["dividend_yield"] == pytest.approx(0.035)

    def test_sub_one_percent_dividend_preserved(self):
        """Sub-1% yields like AAPL (0.41%) must NOT be sanitized."""
        quote = {"dividendYield": 0.41}  # 0.41% -> /100 -> 0.0041
        assert QueryScreener._normalize_quote(quote)["dividend_yield"] == pytest.approx(0.0041)

    def test_extreme_low_pbr_sanitized(self):
        quote = {"priceToBook": 0.01}
        assert QueryScreener._normalize_quote(quote)["pbr"] is None

    def test_normal_pbr_preserved(self):
        quote = {"priceToBook": 0.85}
        assert QueryScreener._normalize_quote(quote)["pbr"] == 0.85

    def test_anomalous_low_per_sanitized(self):
        quote = {"trailingPE": 0.3}
        assert QueryScreener._normalize_quote(quote)["per"] is None

    def test_normal_per_preserved(self):
        quote = {"trailingPE": 10.5}
        assert QueryScreener._normalize_quote(quote)["per"] == 10.5

    def test_extreme_roe_as_percentage_normalized_then_valid(self):
        # returnOnEquity=2.5 -> >1 so /100 -> 0.025 -> valid
        quote = {"returnOnEquity": 2.5}
        assert QueryScreener._normalize_quote(quote)["roe"] == pytest.approx(0.025)

    def test_combined_anomalies(self):
        quote = {
            "symbol": "ANOMALY",
            "dividendYield": 68.0,  # 68% -> /100 -> 0.68 > 0.15 -> None
            "priceToBook": 0.01,
            "trailingPE": 0.5,
            "returnOnEquity": 0.15,
            "regularMarketPrice": 100.0,
        }
        result = QueryScreener._normalize_quote(quote)
        assert result["dividend_yield"] is None
        assert result["pbr"] is None
        assert result["per"] is None
        assert result["roe"] == 0.15  # normal
        assert result["price"] == 100.0

    def test_boundary_dividend_yield_15_percent(self):
        quote = {"dividendYield": 15.0}  # 15% -> /100 -> 0.15, NOT > 0.15 -> kept
        assert QueryScreener._normalize_quote(quote)["dividend_yield"] == pytest.approx(0.15)

    def test_boundary_pbr_005(self):
        quote = {"priceToBook": 0.05}
        assert QueryScreener._normalize_quote(quote)["pbr"] == 0.05

    def test_boundary_per_1(self):
        quote = {"trailingPE": 1.0}
        assert QueryScreener._normalize_quote(quote)["per"] == 1.0

    def test_roe_ratio_exceeding_bounds_sanitized(self):
        """ROE already in ratio form but exceeding bounds should be sanitized."""
        # returnOnEquity: -1.5 is NOT > 1, so no percentage normalization.
        # Anomaly guard catches it: -1.5 < -1.0 -> None
        quote = {"returnOnEquity": -1.5}
        assert QueryScreener._normalize_quote(quote)["roe"] is None
