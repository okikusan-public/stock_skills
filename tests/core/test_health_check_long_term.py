"""Tests for check_long_term_suitability() in health_check.py (KIK-371)."""

from src.core.health_check import check_long_term_suitability


class TestCheckLongTermSuitability:
    """Tests for the long-term suitability classification."""

    def test_ideal_long_term_stock(self):
        """All criteria met -> 長期向き."""
        detail = {
            "symbol": "7203.T",
            "roe": 0.18,
            "eps_growth": 0.15,
            "dividend_yield": 0.03,
            "per": 15.0,
            "sector": "Consumer Cyclical",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "長期向き"
        assert result["roe_status"] == "high"
        assert result["eps_growth_status"] == "growing"
        assert result["dividend_status"] == "high"
        assert result["per_risk"] == "safe"

    def test_overvalued_per_is_short_term(self):
        """PER > 40 -> 短期向き even with good fundamentals."""
        detail = {
            "symbol": "GROWTH.T",
            "roe": 0.20,
            "eps_growth": 0.20,
            "dividend_yield": 0.03,
            "per": 50.0,
            "sector": "Technology",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "短期向き"
        assert result["per_risk"] == "overvalued"

    def test_low_roe_is_short_term(self):
        """ROE < 10% -> 短期向き."""
        detail = {
            "symbol": "LOW.T",
            "roe": 0.05,
            "eps_growth": 0.15,
            "dividend_yield": 0.03,
            "per": 12.0,
            "sector": "Industrials",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "短期向き"
        assert result["roe_status"] == "low"

    def test_medium_roe_needs_review(self):
        """ROE 10-15% with other good metrics -> 要検討."""
        detail = {
            "symbol": "MID.T",
            "roe": 0.12,
            "eps_growth": 0.12,
            "dividend_yield": 0.03,
            "per": 15.0,
            "sector": "Technology",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "要検討"

    def test_declining_eps_needs_review(self):
        """Declining EPS with high ROE -> 要検討."""
        detail = {
            "symbol": "DEC.T",
            "roe": 0.18,
            "eps_growth": -0.05,
            "dividend_yield": 0.03,
            "per": 12.0,
            "sector": "Technology",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "要検討"
        assert result["eps_growth_status"] == "declining"

    def test_low_dividend_needs_review(self):
        """Low dividend with other good metrics -> 要検討."""
        detail = {
            "symbol": "LOWDIV.T",
            "roe": 0.18,
            "eps_growth": 0.15,
            "dividend_yield": 0.005,
            "per": 15.0,
            "sector": "Technology",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "要検討"
        assert result["dividend_status"] == "medium"

    def test_etf_returns_excluded(self):
        """ETF -> 対象外."""
        detail = {"quoteType": "ETF", "symbol": "1306.T"}
        result = check_long_term_suitability(detail)
        assert result["label"] == "対象外"
        assert result["summary"] == "ETF"

    def test_cash_returns_excluded(self):
        """Cash position -> 対象外."""
        detail = {"symbol": "JPY.CASH"}
        result = check_long_term_suitability(detail)
        assert result["label"] == "対象外"
        assert result["summary"] == "-"

    def test_all_none_values_is_short_term(self):
        """All metrics None -> 短期向き (safe side due to low ROE default)."""
        detail = {
            "symbol": "NODATA.T",
            "roe": None,
            "eps_growth": None,
            "dividend_yield": None,
            "per": None,
            "sector": "Technology",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "短期向き"

    # --- Boundary value tests ---

    def test_roe_exactly_15_is_high(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 25.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["roe_status"] == "high"
        assert result["label"] == "長期向き"

    def test_roe_just_below_15_is_medium(self):
        detail = {
            "symbol": "X.T", "roe": 0.149, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 25.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["roe_status"] == "medium"
        assert result["label"] == "要検討"

    def test_roe_exactly_10_is_medium(self):
        detail = {
            "symbol": "X.T", "roe": 0.10, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 25.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["roe_status"] == "medium"

    def test_roe_just_below_10_is_low(self):
        detail = {
            "symbol": "X.T", "roe": 0.099, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 25.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["roe_status"] == "low"
        assert result["label"] == "短期向き"

    def test_eps_exactly_10_is_growing(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 20.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["eps_growth_status"] == "growing"

    def test_eps_zero_is_flat(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.0,
            "dividend_yield": 0.02, "per": 20.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["eps_growth_status"] == "flat"

    def test_eps_negative_is_declining(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": -0.01,
            "dividend_yield": 0.02, "per": 20.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["eps_growth_status"] == "declining"

    def test_per_exactly_25_is_safe(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 25.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["per_risk"] == "safe"

    def test_per_26_is_moderate(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 26.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["per_risk"] == "moderate"

    def test_per_exactly_40_is_moderate(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 40.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["per_risk"] == "moderate"

    def test_per_41_is_overvalued(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 41.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["per_risk"] == "overvalued"
        assert result["label"] == "短期向き"

    def test_dividend_exactly_2pct_is_high(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 20.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["dividend_status"] == "high"

    def test_dividend_zero_is_low(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.0, "per": 20.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["dividend_status"] == "low"

    def test_result_keys(self):
        detail = {
            "symbol": "X.T", "roe": 0.15, "eps_growth": 0.10,
            "dividend_yield": 0.02, "per": 20.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        expected_keys = {
            "label", "roe_status", "eps_growth_status",
            "dividend_status", "per_risk", "score", "summary",
        }
        assert set(result.keys()) == expected_keys

    def test_summary_contains_key_traits(self):
        detail = {
            "symbol": "X.T", "roe": 0.18, "eps_growth": 0.15,
            "dividend_yield": 0.03, "per": 15.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert "高ROE" in result["summary"]
        assert "EPS成長" in result["summary"]
        assert "高配当" in result["summary"]

    def test_summary_shows_negative_traits(self):
        detail = {
            "symbol": "X.T", "roe": 0.05, "eps_growth": -0.10,
            "dividend_yield": 0.0, "per": 50.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert "低ROE" in result["summary"]
        assert "EPS減少" in result["summary"]
        assert "割高PER" in result["summary"]

    def test_moderate_per_allows_long_term(self):
        """PER between 25 and 40 should not block 長期向き."""
        detail = {
            "symbol": "X.T", "roe": 0.18, "eps_growth": 0.15,
            "dividend_yield": 0.03, "per": 35.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["label"] == "長期向き"
        assert result["per_risk"] == "moderate"

    # --- inf/nan guard tests ---

    def test_inf_roe_treated_as_none(self):
        """Infinite ROE should be treated as None (low)."""
        detail = {
            "symbol": "X.T", "roe": float("inf"), "eps_growth": 0.15,
            "dividend_yield": 0.03, "per": 15.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["roe_status"] == "low"
        assert result["label"] == "短期向き"

    def test_nan_per_treated_as_none(self):
        """NaN PER should be treated as None (moderate)."""
        detail = {
            "symbol": "X.T", "roe": 0.18, "eps_growth": 0.15,
            "dividend_yield": 0.03, "per": float("nan"), "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["per_risk"] == "moderate"

    def test_neg_inf_eps_growth_treated_as_none(self):
        """Negative infinity EPS growth -> declining."""
        detail = {
            "symbol": "X.T", "roe": 0.18, "eps_growth": float("-inf"),
            "dividend_yield": 0.03, "per": 15.0, "sector": "Tech",
        }
        result = check_long_term_suitability(detail)
        assert result["eps_growth_status"] == "declining"
