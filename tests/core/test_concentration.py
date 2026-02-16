"""Tests for src/core/concentration.py -- HHI, concentration analysis, multiplier."""

import pytest

from src.core.portfolio.concentration import (
    compute_hhi,
    get_concentration_multiplier,
    analyze_concentration,
    _classify_risk_level,
)


# ===================================================================
# compute_hhi tests
# ===================================================================

class TestComputeHhi:
    """Tests for compute_hhi()."""

    def test_single_asset_hhi_is_one(self):
        """One asset with weight 1.0 -> HHI = 1.0."""
        assert compute_hhi([1.0]) == pytest.approx(1.0)

    def test_two_equal_weights(self):
        """Two equal weights [0.5, 0.5] -> HHI = 0.5."""
        assert compute_hhi([0.5, 0.5]) == pytest.approx(0.5)

    def test_three_equal_weights(self):
        """Three equal weights [1/3, 1/3, 1/3] -> HHI = 1/3."""
        w = 1.0 / 3.0
        assert compute_hhi([w, w, w]) == pytest.approx(1.0 / 3.0)

    def test_four_equal_weights(self):
        """Four equal weights -> HHI = 0.25."""
        assert compute_hhi([0.25, 0.25, 0.25, 0.25]) == pytest.approx(0.25)

    def test_ten_equal_weights(self):
        """Ten equal weights -> HHI = 0.1."""
        weights = [0.1] * 10
        assert compute_hhi(weights) == pytest.approx(0.1)

    def test_empty_weights_returns_zero(self):
        """Empty list -> HHI = 0.0."""
        assert compute_hhi([]) == 0.0

    def test_concentrated_portfolio(self):
        """One dominant weight should give high HHI."""
        # 90% in one, 10% split among 10 others (1% each)
        weights = [0.90] + [0.01] * 10
        hhi = compute_hhi(weights)
        # 0.90^2 + 10 * 0.01^2 = 0.81 + 0.001 = 0.811
        assert hhi == pytest.approx(0.811, abs=0.001)

    def test_hhi_range(self):
        """HHI should be between 0 and 1 for any valid weights."""
        import random
        random.seed(42)
        for _ in range(20):
            n = random.randint(1, 20)
            raw = [random.random() for _ in range(n)]
            total = sum(raw)
            weights = [w / total for w in raw]
            hhi = compute_hhi(weights)
            assert 0.0 <= hhi <= 1.0


# ===================================================================
# get_concentration_multiplier tests
# ===================================================================

class TestGetConcentrationMultiplier:
    """Tests for get_concentration_multiplier()."""

    def test_low_hhi_returns_1(self):
        """HHI < 0.25 -> multiplier = 1.0."""
        assert get_concentration_multiplier(0.10) == 1.0
        assert get_concentration_multiplier(0.0) == 1.0
        assert get_concentration_multiplier(0.24) == 1.0

    def test_hhi_at_0_25_returns_1(self):
        """HHI = 0.25 -> start of interpolation, should be close to 1.0."""
        result = get_concentration_multiplier(0.25)
        assert result == pytest.approx(1.0)

    def test_hhi_at_0_50_returns_1_3(self):
        """HHI = 0.50 -> multiplier = 1.3."""
        result = get_concentration_multiplier(0.50)
        assert result == pytest.approx(1.3)

    def test_hhi_at_0_375_returns_midpoint(self):
        """HHI = 0.375 (midpoint of 0.25-0.50) -> multiplier ~= 1.15."""
        result = get_concentration_multiplier(0.375)
        assert result == pytest.approx(1.15)

    def test_hhi_at_1_0_returns_1_6(self):
        """HHI = 1.0 -> multiplier = 1.6 (cap)."""
        result = get_concentration_multiplier(1.0)
        assert result == pytest.approx(1.6)

    def test_hhi_at_0_75_returns_midpoint(self):
        """HHI = 0.75 (midpoint of 0.50-1.00) -> multiplier ~= 1.45."""
        result = get_concentration_multiplier(0.75)
        assert result == pytest.approx(1.45)

    def test_multiplier_never_exceeds_1_6(self):
        """Multiplier should be capped at 1.6 even for HHI > 1."""
        result = get_concentration_multiplier(1.5)
        assert result == 1.6

    def test_multiplier_monotonically_increasing(self):
        """Multiplier should increase as HHI increases."""
        prev = 0.0
        for hhi_x100 in range(0, 101, 5):
            hhi = hhi_x100 / 100.0
            m = get_concentration_multiplier(hhi)
            assert m >= prev, f"Non-monotonic at HHI={hhi}: {m} < {prev}"
            prev = m


# ===================================================================
# _classify_risk_level tests
# ===================================================================

class TestClassifyRiskLevel:
    """Tests for _classify_risk_level()."""

    def test_low_hhi_diversified(self):
        assert _classify_risk_level(0.10) == "分散"
        assert _classify_risk_level(0.24) == "分散"

    def test_medium_hhi_moderate(self):
        assert _classify_risk_level(0.25) == "やや集中"
        assert _classify_risk_level(0.49) == "やや集中"

    def test_high_hhi_dangerous(self):
        assert _classify_risk_level(0.50) == "危険な集中"
        assert _classify_risk_level(1.0) == "危険な集中"


# ===================================================================
# analyze_concentration tests
# ===================================================================

class TestAnalyzeConcentration:
    """Tests for analyze_concentration()."""

    def test_diversified_portfolio(self):
        """A well-diversified portfolio should have low HHI on all axes."""
        portfolio = [
            {"sector": "Technology", "country": "US", "currency": "USD"},
            {"sector": "Healthcare", "country": "JP", "currency": "JPY"},
            {"sector": "Financial Services", "country": "SG", "currency": "SGD"},
            {"sector": "Energy", "country": "GB", "currency": "GBP"},
        ]
        weights = [0.25, 0.25, 0.25, 0.25]
        result = analyze_concentration(portfolio, weights)

        assert result["sector_hhi"] == pytest.approx(0.25)
        assert result["region_hhi"] == pytest.approx(0.25)
        assert result["currency_hhi"] == pytest.approx(0.25)
        assert result["risk_level"] == "やや集中"  # HHI=0.25 is borderline

    def test_single_stock_portfolio(self):
        """Single stock -> HHI=1.0 on all axes."""
        portfolio = [{"sector": "Technology", "country": "US", "currency": "USD"}]
        weights = [1.0]
        result = analyze_concentration(portfolio, weights)

        assert result["sector_hhi"] == pytest.approx(1.0)
        assert result["region_hhi"] == pytest.approx(1.0)
        assert result["currency_hhi"] == pytest.approx(1.0)
        assert result["max_hhi"] == pytest.approx(1.0)
        assert result["concentration_multiplier"] == pytest.approx(1.6)
        assert result["risk_level"] == "危険な集中"

    def test_sector_concentrated_but_region_diversified(self):
        """All same sector but different regions."""
        portfolio = [
            {"sector": "Technology", "country": "US", "currency": "USD"},
            {"sector": "Technology", "country": "JP", "currency": "JPY"},
            {"sector": "Technology", "country": "SG", "currency": "SGD"},
        ]
        weights = [1.0 / 3, 1.0 / 3, 1.0 / 3]
        result = analyze_concentration(portfolio, weights)

        # Sector is fully concentrated
        assert result["sector_hhi"] == pytest.approx(1.0)
        # Region is diversified
        assert result["region_hhi"] == pytest.approx(1.0 / 3, abs=0.01)
        # Max HHI should be from sector axis
        assert result["max_hhi_axis"] == "sector"
        assert result["max_hhi"] == pytest.approx(1.0)

    def test_missing_keys_use_defaults(self):
        """Missing sector/country/currency should use default labels."""
        portfolio = [
            {},  # all keys missing
            {"sector": "Technology"},  # only sector present
        ]
        weights = [0.5, 0.5]
        result = analyze_concentration(portfolio, weights)

        # Should not crash; defaults should be used
        assert "sector_hhi" in result
        assert "region_hhi" in result
        assert "currency_hhi" in result

    def test_region_key_fallback(self):
        """If 'country' key is missing, should fall back to 'region' key."""
        portfolio = [
            {"sector": "Tech", "region": "Asia", "currency": "JPY"},
            {"sector": "Finance", "region": "Europe", "currency": "EUR"},
        ]
        weights = [0.5, 0.5]
        result = analyze_concentration(portfolio, weights)

        # Region should be diversified (0.5 each)
        assert result["region_hhi"] == pytest.approx(0.5)
        # Breakdown should use the region names
        assert "Asia" in result["region_breakdown"]
        assert "Europe" in result["region_breakdown"]

    def test_result_structure(self):
        """Verify all expected keys in result dict."""
        portfolio = [{"sector": "Tech", "country": "US", "currency": "USD"}]
        weights = [1.0]
        result = analyze_concentration(portfolio, weights)

        expected_keys = [
            "sector_hhi", "region_hhi", "currency_hhi",
            "max_hhi", "max_hhi_axis", "concentration_multiplier",
            "sector_breakdown", "region_breakdown", "currency_breakdown",
            "risk_level",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_breakdown_sums_to_one(self):
        """Each axis breakdown should sum to approximately 1.0."""
        portfolio = [
            {"sector": "Technology", "country": "US", "currency": "USD"},
            {"sector": "Healthcare", "country": "JP", "currency": "JPY"},
            {"sector": "Technology", "country": "US", "currency": "USD"},
        ]
        weights = [0.4, 0.3, 0.3]
        result = analyze_concentration(portfolio, weights)

        for axis in ["sector_breakdown", "region_breakdown", "currency_breakdown"]:
            total = sum(result[axis].values())
            assert total == pytest.approx(1.0, abs=0.001), (
                f"{axis} sums to {total}, expected ~1.0"
            )

    def test_hhi_values_are_rounded(self):
        """HHI values should be rounded to 4 decimal places."""
        portfolio = [
            {"sector": "A", "country": "X", "currency": "C1"},
            {"sector": "B", "country": "Y", "currency": "C2"},
            {"sector": "C", "country": "Z", "currency": "C3"},
        ]
        weights = [1.0 / 3, 1.0 / 3, 1.0 / 3]
        result = analyze_concentration(portfolio, weights)

        # 1/3 squared * 3 = 0.33333... -> should be rounded to 0.3333
        for key in ["sector_hhi", "region_hhi", "currency_hhi"]:
            val = result[key]
            # Check it has at most 4 decimal places
            assert val == round(val, 4)
