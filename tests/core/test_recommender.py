"""Tests for src/core/recommender.py -- rule-based recommendation engine."""

import pytest

from src.core.risk.recommender import (
    generate_recommendations,
    _check_concentration,
    _check_correlations,
    _check_var,
    _check_stress,
    _check_sensitivities,
    _suggest_diversification_sector,
)


# ===================================================================
# Fixtures
# ===================================================================

def _make_concentration(
    sector_hhi=0.3, region_hhi=0.3, currency_hhi=0.3,
    sector_breakdown=None, region_breakdown=None, currency_breakdown=None,
):
    """Create sample concentration data."""
    return {
        "sector_hhi": sector_hhi,
        "region_hhi": region_hhi,
        "currency_hhi": currency_hhi,
        "sector_breakdown": sector_breakdown or {"Technology": 0.6, "Healthcare": 0.4},
        "region_breakdown": region_breakdown or {"US": 0.5, "JP": 0.5},
        "currency_breakdown": currency_breakdown or {"USD": 0.5, "JPY": 0.5},
        "max_hhi": max(sector_hhi, region_hhi, currency_hhi),
        "max_hhi_axis": "sector",
        "concentration_multiplier": 1.0,
        "risk_level": "分散",
    }


def _make_var_result(daily_95=-0.02, monthly_95=-0.09, portfolio_vol=0.20):
    """Create sample VaR data."""
    return {
        "daily_var": {0.95: daily_95, 0.99: daily_95 * 1.5},
        "monthly_var": {0.95: monthly_95, 0.99: monthly_95 * 1.5},
        "portfolio_volatility": portfolio_vol,
        "observation_days": 200,
    }


def _make_scenario_result(pf_impact=-0.15, judgment="認識"):
    """Create sample scenario result."""
    return {
        "scenario_name": "テスト",
        "trigger": "テスト",
        "portfolio_impact": pf_impact,
        "judgment": judgment,
        "stock_impacts": [],
    }


# ===================================================================
# generate_recommendations tests
# ===================================================================

class TestGenerateRecommendations:
    """Tests for generate_recommendations()."""

    def test_returns_list(self):
        """Should always return a list."""
        conc = _make_concentration()
        result = generate_recommendations(conc)
        assert isinstance(result, list)

    def test_sorted_by_priority(self):
        """Recommendations should be sorted high -> medium -> low."""
        conc = _make_concentration(
            sector_hhi=0.55,  # high priority
            region_hhi=0.55,  # high priority
        )
        pairs = [{"pair": ["A", "B"], "correlation": 0.75}]  # medium
        result = generate_recommendations(conc, correlation_pairs=pairs)
        priorities = [r["priority"] for r in result]
        order = {"high": 0, "medium": 1, "low": 2}
        for i in range(len(priorities) - 1):
            assert order[priorities[i]] <= order[priorities[i + 1]]

    def test_recommendation_structure(self):
        """Each recommendation should have required keys."""
        conc = _make_concentration(sector_hhi=0.55)
        result = generate_recommendations(conc)
        for rec in result:
            assert "priority" in rec
            assert "category" in rec
            assert "title" in rec
            assert "detail" in rec
            assert "action" in rec

    def test_all_sources_integrated(self):
        """Should include recommendations from all sources."""
        conc = _make_concentration(sector_hhi=0.55)
        pairs = [{"pair": ["A", "B"], "correlation": 0.90}]
        var = _make_var_result(monthly_95=-0.16)
        scenario = _make_scenario_result(pf_impact=-0.35, judgment="要対応")
        sensitivities = [{
            "symbol": "TEST",
            "integrated": {
                "quadrant": {"quadrant": "最危険", "description": "test"}
            },
        }]

        result = generate_recommendations(
            conc,
            correlation_pairs=pairs,
            var_result=var,
            scenario_result=scenario,
            sensitivities=sensitivities,
        )
        categories = {r["category"] for r in result}
        assert "concentration" in categories
        assert "correlation" in categories
        assert "var" in categories
        assert "stress" in categories
        assert "sensitivity" in categories

    def test_no_recommendations_for_healthy_portfolio(self):
        """Well-diversified, low-risk portfolio should have minimal recommendations."""
        conc = _make_concentration(
            sector_hhi=0.15, region_hhi=0.15, currency_hhi=0.15,
        )
        var = _make_var_result(monthly_95=-0.05, portfolio_vol=0.15)
        scenario = _make_scenario_result(pf_impact=-0.05, judgment="継続")
        result = generate_recommendations(
            conc, var_result=var, scenario_result=scenario,
        )
        # Should have no high-priority recommendations
        high = [r for r in result if r["priority"] == "high"]
        assert len(high) == 0


# ===================================================================
# _check_concentration tests
# ===================================================================

class TestCheckConcentration:
    """Tests for _check_concentration()."""

    def test_high_sector_hhi(self):
        """Sector HHI > 0.50 generates high priority recommendation."""
        conc = _make_concentration(sector_hhi=0.55)
        recs = _check_concentration(conc)
        assert any(r["priority"] == "high" and "セクター集中" in r["title"] for r in recs)

    def test_moderate_sector_hhi(self):
        """Sector HHI 0.25-0.50 generates medium priority recommendation."""
        conc = _make_concentration(sector_hhi=0.35)
        recs = _check_concentration(conc)
        assert any(r["priority"] == "medium" and "セクター" in r["title"] for r in recs)

    def test_low_sector_hhi_no_recommendation(self):
        """Sector HHI < 0.25 generates no sector recommendation."""
        conc = _make_concentration(sector_hhi=0.20)
        recs = _check_concentration(conc)
        sector_recs = [r for r in recs if "セクター" in r.get("title", "")]
        assert len(sector_recs) == 0

    def test_high_region_hhi(self):
        """Region HHI > 0.50 generates high priority recommendation."""
        conc = _make_concentration(region_hhi=0.60)
        recs = _check_concentration(conc)
        assert any(r["priority"] == "high" and "地域集中" in r["title"] for r in recs)

    def test_high_currency_hhi(self):
        """Currency HHI > 0.50 generates medium priority recommendation."""
        conc = _make_concentration(currency_hhi=0.60)
        recs = _check_concentration(conc)
        assert any(r["priority"] == "medium" and "通貨集中" in r["title"] for r in recs)

    def test_empty_breakdown_no_crash(self):
        """Empty breakdowns should not crash."""
        conc = _make_concentration(
            sector_hhi=0.55,
            sector_breakdown={},
        )
        recs = _check_concentration(conc)
        # Should not crash, but may not produce sector rec due to empty breakdown
        assert isinstance(recs, list)


# ===================================================================
# _check_correlations tests
# ===================================================================

class TestCheckCorrelations:
    """Tests for _check_correlations()."""

    def test_very_high_correlation(self):
        """r >= 0.85 generates high priority recommendation."""
        pairs = [{"pair": ["A", "B"], "correlation": 0.90}]
        recs = _check_correlations(pairs)
        assert len(recs) == 1
        assert recs[0]["priority"] == "high"

    def test_high_correlation(self):
        """r >= 0.70 generates medium priority recommendation."""
        pairs = [{"pair": ["A", "B"], "correlation": 0.75}]
        recs = _check_correlations(pairs)
        assert len(recs) == 1
        assert recs[0]["priority"] == "medium"

    def test_empty_pairs(self):
        """No pairs -> no recommendations."""
        recs = _check_correlations([])
        assert recs == []

    def test_negative_very_high(self):
        """Strong negative correlation also generates high priority."""
        pairs = [{"pair": ["A", "B"], "correlation": -0.90}]
        recs = _check_correlations(pairs)
        assert len(recs) == 1
        assert recs[0]["priority"] == "high"


# ===================================================================
# _check_var tests
# ===================================================================

class TestCheckVar:
    """Tests for _check_var()."""

    def test_high_monthly_var(self):
        """Monthly VaR(95%) < -15% generates high priority."""
        var = _make_var_result(monthly_95=-0.18)
        recs = _check_var(var)
        assert any(r["priority"] == "high" and "VaR" in r["title"] for r in recs)

    def test_moderate_monthly_var(self):
        """Monthly VaR(95%) between -10% and -15% generates medium priority."""
        var = _make_var_result(monthly_95=-0.12)
        recs = _check_var(var)
        assert any(r["priority"] == "medium" and "VaR" in r["title"] for r in recs)

    def test_low_monthly_var(self):
        """Monthly VaR(95%) > -10% generates no VaR recommendation."""
        var = _make_var_result(monthly_95=-0.05)
        recs = _check_var(var)
        var_recs = [r for r in recs if "VaR" in r.get("title", "")]
        assert len(var_recs) == 0

    def test_high_volatility(self):
        """Portfolio volatility > 30% generates medium priority."""
        var = _make_var_result(portfolio_vol=0.35)
        recs = _check_var(var)
        assert any(r["priority"] == "medium" and "ボラティリティ" in r["title"] for r in recs)


# ===================================================================
# _check_stress tests
# ===================================================================

class TestCheckStress:
    """Tests for _check_stress()."""

    def test_critical_judgment(self):
        """'要対応' judgment generates high priority."""
        scenario = _make_scenario_result(pf_impact=-0.35, judgment="要対応")
        recs = _check_stress(scenario)
        assert any(r["priority"] == "high" and "要対応" in r["title"] for r in recs)

    def test_stock_impact_over_30(self):
        """Individual stock impact < -30% generates high priority."""
        scenario = _make_scenario_result()
        scenario["stock_impacts"] = [
            {"symbol": "TEST", "total_impact": -0.35},
        ]
        recs = _check_stress(scenario)
        assert any(r["priority"] == "high" and "TEST" in r["title"] for r in recs)

    def test_normal_judgment(self):
        """'継続' judgment with no extreme stocks -> no stress recommendation."""
        scenario = _make_scenario_result(pf_impact=-0.05, judgment="継続")
        scenario["stock_impacts"] = [
            {"symbol": "TEST", "total_impact": -0.10},
        ]
        recs = _check_stress(scenario)
        assert len(recs) == 0


# ===================================================================
# _check_sensitivities tests
# ===================================================================

class TestCheckSensitivities:
    """Tests for _check_sensitivities()."""

    def test_most_dangerous_quadrant(self):
        """'最危険' quadrant generates high priority."""
        sensitivities = [{
            "symbol": "TEST",
            "integrated": {
                "quadrant": {"quadrant": "最危険", "description": "desc"}
            },
        }]
        recs = _check_sensitivities(sensitivities)
        assert len(recs) == 1
        assert recs[0]["priority"] == "high"

    def test_bottom_risk_quadrant(self):
        """'底抜けリスク' quadrant generates medium priority."""
        sensitivities = [{
            "symbol": "TEST",
            "integrated": {
                "quadrant": {"quadrant": "底抜けリスク", "description": "desc"}
            },
        }]
        recs = _check_sensitivities(sensitivities)
        assert len(recs) == 1
        assert recs[0]["priority"] == "medium"

    def test_neutral_quadrant(self):
        """Neutral quadrant generates no recommendation."""
        sensitivities = [{
            "symbol": "TEST",
            "integrated": {
                "quadrant": {"quadrant": "中立", "description": "desc"}
            },
        }]
        recs = _check_sensitivities(sensitivities)
        assert len(recs) == 0

    def test_empty_sensitivities(self):
        """Empty list -> no recommendations."""
        recs = _check_sensitivities([])
        assert recs == []


# ===================================================================
# _suggest_diversification_sector tests
# ===================================================================

class TestSuggestDiversificationSector:
    """Tests for _suggest_diversification_sector()."""

    def test_suggests_missing_sectors(self):
        """Should suggest sectors not in portfolio."""
        breakdown = {"Technology": 0.5, "Healthcare": 0.3, "Energy": 0.2}
        suggestion = _suggest_diversification_sector(breakdown)
        assert "Technology" not in suggestion
        assert "Healthcare" not in suggestion

    def test_all_sectors_present(self):
        """When all sectors present, falls back to generic suggestion."""
        breakdown = {s: 0.09 for s in [
            "Technology", "Healthcare", "Financial Services",
            "Consumer Defensive", "Industrials", "Energy",
            "Basic Materials", "Utilities", "Real Estate",
            "Communication Services", "Consumer Cyclical",
        ]}
        suggestion = _suggest_diversification_sector(breakdown)
        assert suggestion == "他セクター"
