"""Tests for 3-axis quality scoring (KIK-708)."""

import pytest

from src.data.scoring import (
    score_return,
    score_growth,
    score_durability,
    _classify_quadrant,
    _clamp,
    _load_config,
)


# ---------------------------------------------------------------------------
# Helper: build minimal info/detail dicts for testing
# ---------------------------------------------------------------------------

def _make_info(**kwargs):
    """Create a minimal stock_info dict with defaults."""
    defaults = {
        "symbol": "TEST",
        "sector": "Technology",
        "price": 100.0,
        "per": 20.0,
        "roe": 0.15,
        "roa": 0.08,
        "operating_margin": 0.20,
        "dividend_yield": 0.03,
        "payout_ratio": 0.40,
        "debt_to_equity": 50.0,
        "current_ratio": 2.0,
        "beta": 1.0,
        "earnings_growth": 0.10,
        "revenue_growth": 0.10,
        "free_cashflow": 1000000000,
    }
    defaults.update(kwargs)
    return defaults


def _make_detail(**kwargs):
    """Create a minimal stock_detail dict with defaults."""
    defaults = {
        "operating_cashflow": 2000000000,
        "net_income_stmt": 1000000000,
        "depreciation": -500000000,
        "interest_expense": -100000000,
        "operating_income_history": [500000000, 450000000, 400000000],
        "revenue_history": [5000000000, 4500000000, 4000000000],
        "total_debt": 2000000000,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# _clamp
# ---------------------------------------------------------------------------

class TestClamp:
    def test_within_range(self):
        assert _clamp(5.0) == 5.0

    def test_below_zero(self):
        assert _clamp(-2.0) == 0.0

    def test_above_ten(self):
        assert _clamp(12.0) == 10.0


# ---------------------------------------------------------------------------
# Return Score (還元性)
# ---------------------------------------------------------------------------

class TestScoreReturn:
    def test_high_yield(self):
        info = _make_info(dividend_yield=0.04)
        pf = {"div_yield": 4.0, "buyback_yield": 3.0}
        result = score_return(info, portfolio_entry=pf)
        assert result["score"] >= 6.0
        assert result["A"] == 7.0
        assert not result["capped"]

    def test_zero_dividend(self):
        info = _make_info(dividend_yield=0.0)
        result = score_return(info)
        assert result["score"] == 0.0
        assert result["B"] == 0.0
        assert result["C"] == 0.0

    def test_low_yield_below_threshold(self):
        info = _make_info(dividend_yield=0.005)
        result = score_return(info)
        assert result["score"] < 1.0

    def test_cap_rule_durability_low(self):
        info = _make_info(dividend_yield=0.05)
        pf = {"div_yield": 8.0, "buyback_yield": 0.0}
        result = score_return(info, portfolio_entry=pf, durability_score=2.5)
        assert result["score"] <= 4.0
        assert result["capped"]

    def test_cap_rule_durability_moderate(self):
        info = _make_info(dividend_yield=0.05)
        pf = {"div_yield": 8.0, "buyback_yield": 0.0}
        result = score_return(info, portfolio_entry=pf, durability_score=4.5)
        assert result["score"] <= 6.0

    def test_no_cap_when_durability_high(self):
        info = _make_info(dividend_yield=0.05)
        pf = {"div_yield": 8.0, "buyback_yield": 0.0}
        result = score_return(info, portfolio_entry=pf, durability_score=7.0)
        assert result["score"] > 6.0
        assert not result["capped"]

    def test_payout_consistency_healthy(self):
        info = _make_info(payout_ratio=0.30, dividend_yield=0.03)
        pf = {"div_yield": 3.0, "buyback_yield": 0.0}
        result = score_return(info, portfolio_entry=pf)
        assert result["C"] == 10.0

    def test_payout_consistency_risky(self):
        info = _make_info(payout_ratio=0.90, dividend_yield=0.03)
        pf = {"div_yield": 3.0, "buyback_yield": 0.0}
        result = score_return(info, portfolio_entry=pf)
        assert result["C"] == 2.0


# ---------------------------------------------------------------------------
# Growth Score (成長性)
# ---------------------------------------------------------------------------

class TestScoreGrowth:
    def test_high_growth(self):
        info = _make_info(earnings_growth=0.30, revenue_growth=0.25, roa=0.30)
        detail = _make_detail()
        result = score_growth(info, detail)
        assert result["score"] >= 5.0
        assert result["A"] == 10.0

    def test_negative_growth(self):
        info = _make_info(earnings_growth=-0.20, revenue_growth=-0.10, roa=0.05)
        result = score_growth(info)
        assert result["A"] == 0.0

    def test_acquisition_flag(self):
        info = _make_info(earnings_growth=0.0, revenue_growth=0.50, roa=0.05)
        result_normal = score_growth(info)
        result_flagged = score_growth(info, overrides={"acquisition_flag": True})
        assert result_flagged["A"] < result_normal["A"]

    def test_beta_asymmetry_low(self):
        info = _make_info(beta=0.5, earnings_growth=0.15, roa=0.10)
        result = score_growth(info)
        assert result["multiplier"] >= 0.90
        assert result["multiplier"] < 1.0

    def test_beta_asymmetry_high(self):
        info = _make_info(beta=2.0, earnings_growth=0.15, roa=0.10)
        result = score_growth(info)
        assert result["multiplier"] <= 0.85
        assert result["multiplier"] >= 0.75

    def test_beta_none(self):
        info = _make_info(beta=None, earnings_growth=0.15, roa=0.10)
        result = score_growth(info)
        assert result["multiplier"] == 1.0

    def test_nopat_zero_no_crash(self):
        info = _make_info(roa=0.05)
        detail = _make_detail(net_income_stmt=0, operating_cashflow=100)
        result = score_growth(info, detail)
        assert result["C"] == 5.0

    def test_score_within_range(self):
        info = _make_info()
        result = score_growth(info)
        assert 0.0 <= result["score"] <= 10.0


# ---------------------------------------------------------------------------
# Durability Score (持続性)
# ---------------------------------------------------------------------------

class TestScoreDurability:
    def test_strong_company(self):
        info = _make_info(debt_to_equity=30.0, operating_margin=0.20, current_ratio=2.5)
        detail = _make_detail(interest_expense=-50000000)
        result = score_durability(info, detail)
        assert result["score"] >= 5.0

    def test_high_leverage_penalty_level2(self):
        info = _make_info(debt_to_equity=250.0, operating_margin=0.40)
        detail = _make_detail(interest_expense=-100000000)
        result = score_durability(info, detail)
        assert result["A"] <= 3.0
        assert result["de_penalty"] is not None

    def test_hard_cap_de_250(self):
        info = _make_info(debt_to_equity=304.0, operating_margin=0.46)
        detail = _make_detail(interest_expense=-100000000)
        result = score_durability(info, detail)
        assert result["score"] <= 3.0
        assert "hard cap" in (result["de_penalty"] or "")

    def test_no_debt_high_score(self):
        info = _make_info(debt_to_equity=0.0, operating_margin=0.20, current_ratio=3.0)
        detail = _make_detail(interest_expense=None, total_debt=0)
        result = score_durability(info, detail)
        assert result["A"] == 10.0

    def test_interest_expense_none_with_debt(self):
        info = _make_info(debt_to_equity=80.0)
        detail = _make_detail(interest_expense=None, total_debt=5000000000)
        result = score_durability(info, detail)
        assert result["A"] == 7.0

    def test_stability_calculation(self):
        info = _make_info(operating_margin=0.20)
        detail = _make_detail(
            operating_income_history=[1000, 980, 960],
            revenue_history=[5000, 5000, 5000],
        )
        result = score_durability(info, detail)
        assert result["B"] > 0

    def test_score_within_range(self):
        info = _make_info()
        result = score_durability(info)
        assert 0.0 <= result["score"] <= 10.0


# ---------------------------------------------------------------------------
# Quadrant Classification (4象限)
# ---------------------------------------------------------------------------

class TestQuadrantClassification:
    @pytest.fixture
    def cfg(self):
        return _load_config()

    def test_sell_low_durability(self, cfg):
        q = _classify_quadrant(5.0, 8.0, 5.0, 2.5, False, cfg)
        assert q == "売却検討"

    def test_sell_capped(self, cfg):
        q = _classify_quadrant(5.0, 4.0, 5.0, 4.0, True, cfg)
        assert q == "売却検討"

    def test_watch_low_total(self, cfg):
        q = _classify_quadrant(4.0, 5.0, 3.0, 5.0, False, cfg)
        assert q == "要監視"

    def test_watch_moderate_durability(self, cfg):
        q = _classify_quadrant(5.5, 5.0, 5.0, 4.5, False, cfg)
        assert q == "要監視"

    def test_add(self, cfg):
        q = _classify_quadrant(7.5, 5.0, 6.0, 7.0, False, cfg)
        assert q == "買い増し"

    def test_add_fails_axis_below_min(self, cfg):
        q = _classify_quadrant(7.5, 3.5, 6.0, 7.0, False, cfg)
        assert q == "保有継続"

    def test_hold_default(self, cfg):
        q = _classify_quadrant(6.0, 5.0, 5.0, 6.0, False, cfg)
        assert q == "保有継続"

    def test_sell_takes_priority_over_watch(self, cfg):
        q = _classify_quadrant(6.0, 8.0, 5.0, 2.0, False, cfg)
        assert q == "売却検討"

    def test_exclusive_coverage(self, cfg):
        quadrants_seen = set()
        for total in [2.0, 5.0, 7.5]:
            for dur in [2.0, 4.5, 6.0, 8.0]:
                for ret in [2.0, 5.0, 8.0]:
                    for growth in [2.0, 5.0, 8.0]:
                        for capped in [True, False]:
                            q = _classify_quadrant(total, ret, growth, dur, capped, cfg)
                            assert q in {"売却検討", "要監視", "買い増し", "保有継続"}
                            quadrants_seen.add(q)
        assert len(quadrants_seen) == 4
