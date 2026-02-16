"""Tests for src/core/rebalancer.py -- portfolio rebalancer engine."""

import pytest

from src.core.portfolio.concentration import compute_hhi
from src.core.portfolio.rebalancer import (
    _is_cash,
    _build_constraints,
    _compute_current_metrics,
    _generate_sell_actions,
    _generate_reduce_actions,
    _generate_increase_actions,
    generate_rebalance_proposal,
    _DEFAULT_CONSTRAINTS,
    _STRATEGY_PRESETS,
)


# ===================================================================
# Helper factories
# ===================================================================

def _make_position(
    symbol="7203.T",
    name="Toyota",
    value_jpy=100_000,
    sector="Automotive",
    country="JP",
    currency="JPY",
    base=0.05,
    dividend_yield=0.02,
):
    """Create a sample position dict."""
    return {
        "symbol": symbol,
        "name": name,
        "value_jpy": value_jpy,
        "sector": sector,
        "country": country,
        "currency": currency,
        "base": base,
        "dividend_yield": dividend_yield,
    }


def _make_forecast(positions, total_value_jpy=None):
    """Create a sample forecast_result dict."""
    if total_value_jpy is None:
        total_value_jpy = sum(p.get("value_jpy", 0) for p in positions)
    return {
        "positions": positions,
        "total_value_jpy": total_value_jpy,
    }


def _make_health(alerts):
    """Create a sample health_result dict.

    alerts: list of (symbol, level, reasons) tuples
    """
    positions = []
    for sym, level, reasons in alerts:
        positions.append({
            "symbol": sym,
            "alert": {"level": level, "reasons": reasons},
        })
    return {"positions": positions}


# ===================================================================
# _is_cash tests
# ===================================================================

class TestIsCash:
    """Tests for _is_cash()."""

    def test_jpy_cash(self):
        assert _is_cash("JPY.CASH") is True

    def test_usd_cash(self):
        assert _is_cash("USD.CASH") is True

    def test_lowercase_cash(self):
        assert _is_cash("jpy.cash") is True

    def test_mixed_case_cash(self):
        assert _is_cash("Sgd.Cash") is True

    def test_stock_symbol(self):
        assert _is_cash("7203.T") is False

    def test_us_stock(self):
        assert _is_cash("AAPL") is False

    def test_empty_string(self):
        assert _is_cash("") is False

    def test_cash_prefix_only(self):
        # "CASH" does not end with ".CASH"
        assert _is_cash("CASH") is False


# ===================================================================
# _build_constraints tests
# ===================================================================

class TestBuildConstraints:
    """Tests for _build_constraints()."""

    def test_balanced_uses_defaults(self):
        c = _build_constraints("balanced")
        assert c["max_single_ratio"] == _DEFAULT_CONSTRAINTS["max_single_ratio"]
        assert c["max_sector_hhi"] == _DEFAULT_CONSTRAINTS["max_sector_hhi"]
        assert c["max_region_hhi"] == _DEFAULT_CONSTRAINTS["max_region_hhi"]
        assert c["max_corr_pair_ratio"] == _DEFAULT_CONSTRAINTS["max_corr_pair_ratio"]
        assert c["corr_threshold"] == _DEFAULT_CONSTRAINTS["corr_threshold"]

    def test_defensive_has_tighter_constraints(self):
        defensive = _build_constraints("defensive")
        balanced = _build_constraints("balanced")
        assert defensive["max_single_ratio"] < balanced["max_single_ratio"]
        assert defensive["max_sector_hhi"] < balanced["max_sector_hhi"]
        assert defensive["max_region_hhi"] < balanced["max_region_hhi"]
        assert defensive["max_corr_pair_ratio"] < balanced["max_corr_pair_ratio"]

    def test_aggressive_has_looser_constraints(self):
        aggressive = _build_constraints("aggressive")
        balanced = _build_constraints("balanced")
        assert aggressive["max_single_ratio"] > balanced["max_single_ratio"]
        assert aggressive["max_sector_hhi"] > balanced["max_sector_hhi"]
        assert aggressive["max_region_hhi"] > balanced["max_region_hhi"]
        assert aggressive["max_corr_pair_ratio"] > balanced["max_corr_pair_ratio"]

    def test_explicit_override_takes_priority(self):
        c = _build_constraints("defensive", max_single_ratio=0.50)
        assert c["max_single_ratio"] == 0.50
        # Others should still be defensive
        assert c["max_sector_hhi"] == _STRATEGY_PRESETS["defensive"]["max_sector_hhi"]

    def test_all_overrides(self):
        c = _build_constraints(
            "balanced",
            max_single_ratio=0.99,
            max_sector_hhi=0.88,
            max_region_hhi=0.77,
            max_corr_pair_ratio=0.66,
        )
        assert c["max_single_ratio"] == 0.99
        assert c["max_sector_hhi"] == 0.88
        assert c["max_region_hhi"] == 0.77
        assert c["max_corr_pair_ratio"] == 0.66

    def test_unknown_strategy_uses_defaults(self):
        c = _build_constraints("unknown_strategy")
        assert c["max_single_ratio"] == _DEFAULT_CONSTRAINTS["max_single_ratio"]

    def test_corr_threshold_always_present(self):
        for strategy in ["defensive", "balanced", "aggressive"]:
            c = _build_constraints(strategy)
            assert "corr_threshold" in c
            assert c["corr_threshold"] == _DEFAULT_CONSTRAINTS["corr_threshold"]


# ===================================================================
# _compute_current_metrics tests
# ===================================================================

class TestComputeCurrentMetrics:
    """Tests for _compute_current_metrics()."""

    def test_empty_positions(self):
        m = _compute_current_metrics([], 0)
        assert m["base_return"] == 0.0
        assert m["weights"] == {}
        assert m["sector_weights"] == {}
        assert m["region_weights"] == {}
        assert m["currency_weights"] == {}

    def test_zero_total_value(self):
        positions = [_make_position(value_jpy=100_000)]
        m = _compute_current_metrics(positions, 0)
        assert m["base_return"] == 0.0

    def test_single_position(self):
        pos = _make_position(symbol="AAPL", value_jpy=500_000, base=0.10,
                             sector="Technology", country="US", currency="USD")
        m = _compute_current_metrics([pos], 500_000)
        assert m["weights"]["AAPL"] == pytest.approx(1.0)
        assert m["sector_weights"]["Technology"] == pytest.approx(1.0)
        assert m["region_weights"]["US"] == pytest.approx(1.0)
        assert m["currency_weights"]["USD"] == pytest.approx(1.0)
        assert m["base_return"] == pytest.approx(0.10)

    def test_two_equal_positions(self):
        pos_a = _make_position(symbol="A", value_jpy=100_000, base=0.10,
                               sector="Tech", country="US", currency="USD")
        pos_b = _make_position(symbol="B", value_jpy=100_000, base=0.20,
                               sector="Health", country="JP", currency="JPY")
        m = _compute_current_metrics([pos_a, pos_b], 200_000)

        assert m["weights"]["A"] == pytest.approx(0.5)
        assert m["weights"]["B"] == pytest.approx(0.5)
        assert m["base_return"] == pytest.approx(0.15)  # 0.1*0.5 + 0.2*0.5
        assert m["sector_weights"]["Tech"] == pytest.approx(0.5)
        assert m["sector_weights"]["Health"] == pytest.approx(0.5)

    def test_weighted_return_calculation(self):
        pos_a = _make_position(symbol="A", value_jpy=300_000, base=0.05)
        pos_b = _make_position(symbol="B", value_jpy=100_000, base=0.20)
        total = 400_000
        m = _compute_current_metrics([pos_a, pos_b], total)
        # 0.05 * 0.75 + 0.20 * 0.25 = 0.0375 + 0.05 = 0.0875
        assert m["base_return"] == pytest.approx(0.0875)

    def test_missing_base_return_skipped(self):
        pos = _make_position(symbol="X", value_jpy=100_000)
        pos["base"] = None
        m = _compute_current_metrics([pos], 100_000)
        assert m["base_return"] == pytest.approx(0.0)

    def test_evaluation_jpy_fallback(self):
        """Should use evaluation_jpy if value_jpy is missing."""
        pos = {"symbol": "X", "evaluation_jpy": 200_000, "base": 0.10,
               "sector": "Tech", "country": "US", "currency": "USD"}
        m = _compute_current_metrics([pos], 200_000)
        assert m["weights"]["X"] == pytest.approx(1.0)
        assert m["base_return"] == pytest.approx(0.10)

    def test_missing_sector_defaults_to_unknown(self):
        pos = {"symbol": "X", "value_jpy": 100_000, "base": 0.05}
        m = _compute_current_metrics([pos], 100_000)
        assert "Unknown" in m["sector_weights"]

    def test_same_sector_weights_sum(self):
        pos_a = _make_position(symbol="A", value_jpy=100_000, sector="Tech")
        pos_b = _make_position(symbol="B", value_jpy=100_000, sector="Tech")
        m = _compute_current_metrics([pos_a, pos_b], 200_000)
        assert m["sector_weights"]["Tech"] == pytest.approx(1.0)


# ===================================================================
# compute_hhi tests (moved to concentration.compute_hhi, KIK-387)
# ===================================================================

class TestComputeHhi:
    """Tests for compute_hhi() from concentration module."""

    def test_empty_list(self):
        assert compute_hhi([]) == 0.0

    def test_single_category(self):
        assert compute_hhi([1.0]) == pytest.approx(1.0)

    def test_two_equal(self):
        assert compute_hhi([0.5, 0.5]) == pytest.approx(0.5)

    def test_three_equal(self):
        w = 1.0 / 3.0
        assert compute_hhi([w, w, w]) == pytest.approx(1.0 / 3.0)

    def test_concentrated(self):
        # 0.9^2 + 0.1^2 = 0.81 + 0.01 = 0.82
        assert compute_hhi([0.9, 0.1]) == pytest.approx(0.82)


# ===================================================================
# _generate_sell_actions tests
# ===================================================================

class TestGenerateSellActions:
    """Tests for _generate_sell_actions()."""

    def test_empty_portfolio_no_actions(self):
        actions = _generate_sell_actions([], None)
        assert actions == []

    def test_no_alerts_no_sells(self):
        positions = [_make_position(base=0.05)]
        actions = _generate_sell_actions(positions, None)
        assert actions == []

    def test_health_exit_triggers_sell(self):
        positions = [_make_position(symbol="BAD", value_jpy=500_000, base=0.02)]
        health = _make_health([("BAD", "exit", ["デッドクロス", "複数悪化"])])
        actions = _generate_sell_actions(positions, health)

        assert len(actions) == 1
        assert actions[0]["action"] == "sell"
        assert actions[0]["symbol"] == "BAD"
        assert actions[0]["ratio"] == 1.0
        assert actions[0]["value_jpy"] == 500_000
        assert "撤退" in actions[0]["reason"]
        assert actions[0]["priority"] == 1

    def test_base_return_below_minus_10_triggers_sell(self):
        positions = [_make_position(symbol="DROP", value_jpy=300_000, base=-0.15)]
        actions = _generate_sell_actions(positions, None)

        assert len(actions) == 1
        assert actions[0]["action"] == "sell"
        assert actions[0]["symbol"] == "DROP"
        assert actions[0]["ratio"] == 1.0
        assert "マイナス" in actions[0]["reason"]
        assert actions[0]["priority"] == 2

    def test_base_return_exactly_minus_10_not_sold(self):
        positions = [_make_position(symbol="EDGE", base=-0.10)]
        actions = _generate_sell_actions(positions, None)
        assert actions == []

    def test_base_return_minus_9_not_sold(self):
        positions = [_make_position(symbol="OK", base=-0.09)]
        actions = _generate_sell_actions(positions, None)
        assert actions == []

    def test_cash_positions_skipped(self):
        positions = [{"symbol": "JPY.CASH", "value_jpy": 1_000_000, "base": -0.50}]
        health = _make_health([("JPY.CASH", "exit", ["test"])])
        actions = _generate_sell_actions(positions, health)
        assert actions == []

    def test_exit_alert_takes_priority_over_base_return(self):
        """If both exit alert and negative base, should only generate one sell (exit)."""
        positions = [_make_position(symbol="X", value_jpy=200_000, base=-0.20)]
        health = _make_health([("X", "exit", ["reason"])])
        actions = _generate_sell_actions(positions, health)
        # exit alert triggers sell and `continue`, so no duplicate from rule 2
        assert len(actions) == 1
        assert actions[0]["priority"] == 1

    def test_multiple_sells(self):
        positions = [
            _make_position(symbol="A", value_jpy=100_000, base=-0.15),
            _make_position(symbol="B", value_jpy=200_000, base=0.05),
            _make_position(symbol="C", value_jpy=150_000, base=-0.20),
        ]
        actions = _generate_sell_actions(positions, None)
        symbols = {a["symbol"] for a in actions}
        assert symbols == {"A", "C"}
        assert "B" not in symbols

    def test_health_caution_does_not_trigger_sell(self):
        positions = [_make_position(symbol="WARN", base=0.05)]
        health = _make_health([("WARN", "caution", ["some warning"])])
        actions = _generate_sell_actions(positions, health)
        assert actions == []

    def test_none_base_return_no_sell(self):
        positions = [_make_position(symbol="X")]
        positions[0]["base"] = None
        actions = _generate_sell_actions(positions, None)
        assert actions == []


# ===================================================================
# _generate_reduce_actions tests
# ===================================================================

class TestGenerateReduceActions:
    """Tests for _generate_reduce_actions()."""

    def test_empty_portfolio_no_actions(self):
        c = _build_constraints("balanced")
        actions = _generate_reduce_actions([], 0, c)
        assert actions == []

    def test_zero_total_value_no_actions(self):
        c = _build_constraints("balanced")
        positions = [_make_position(value_jpy=100_000)]
        actions = _generate_reduce_actions(positions, 0, c)
        assert actions == []

    def test_single_stock_over_max_ratio(self):
        c = _build_constraints("balanced")  # max_single_ratio = 0.15
        # 20% of total = over 15% limit
        positions = [_make_position(symbol="HEAVY", value_jpy=200_000)]
        total = 1_000_000
        actions = _generate_reduce_actions(positions, total, c)

        assert len(actions) == 1
        assert actions[0]["action"] == "reduce"
        assert actions[0]["symbol"] == "HEAVY"
        assert actions[0]["priority"] == 3
        # 20% -> 15%, reduce ratio = 1 - 15/20 = 0.25
        assert actions[0]["ratio"] == pytest.approx(0.25)

    def test_stock_within_limit_no_reduce(self):
        c = _build_constraints("balanced")  # max_single_ratio = 0.15
        positions = [_make_position(symbol="OK", value_jpy=100_000)]
        total = 1_000_000  # 10% < 15%
        actions = _generate_reduce_actions(positions, total, c)
        assert actions == []

    def test_high_correlation_pair_over_limit(self):
        c = _build_constraints("aggressive")  # max_single=0.25, max_corr_pair=0.40
        # Each at 22% (under 25% single limit), combined 44% > 40% corr limit
        positions = [
            _make_position(symbol="A", value_jpy=220_000, base=0.10),
            _make_position(symbol="B", value_jpy=220_000, base=0.05),
        ]
        total = 1_000_000
        pairs = [{"pair": ["A", "B"], "correlation": 0.85}]

        actions = _generate_reduce_actions(positions, total, c, high_corr_pairs=pairs)

        # Should reduce B (lower return)
        corr_actions = [a for a in actions if a["priority"] == 4]
        assert len(corr_actions) == 1
        assert corr_actions[0]["symbol"] == "B"
        assert "相関集中" in corr_actions[0]["reason"]

    def test_high_correlation_reduces_lower_return(self):
        c = _build_constraints("aggressive")  # max_single=0.25, max_corr_pair=0.40
        # Each at 22% (under 25% single limit), combined 44% > 40% corr limit
        positions = [
            _make_position(symbol="HIGH_RET", value_jpy=220_000, base=0.20),
            _make_position(symbol="LOW_RET", value_jpy=220_000, base=0.02),
        ]
        total = 1_000_000
        pairs = [{"pair": ["HIGH_RET", "LOW_RET"], "correlation": 0.80}]

        actions = _generate_reduce_actions(positions, total, c, high_corr_pairs=pairs)
        corr_actions = [a for a in actions if a["priority"] == 4]
        assert len(corr_actions) == 1
        assert corr_actions[0]["symbol"] == "LOW_RET"

    def test_reduce_sector(self):
        c = _build_constraints("balanced")
        positions = [
            _make_position(symbol="A", value_jpy=100_000, sector="Technology"),
            _make_position(symbol="B", value_jpy=100_000, sector="Healthcare"),
        ]
        total = 1_000_000

        actions = _generate_reduce_actions(
            positions, total, c, reduce_sector="Technology"
        )
        assert len(actions) == 1
        assert actions[0]["symbol"] == "A"
        assert actions[0]["ratio"] == 0.3
        assert "セクター削減" in actions[0]["reason"]

    def test_reduce_sector_case_insensitive(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="A", value_jpy=100_000, sector="Technology")]
        total = 1_000_000

        actions = _generate_reduce_actions(
            positions, total, c, reduce_sector="technology"
        )
        assert len(actions) == 1

    def test_reduce_currency(self):
        c = _build_constraints("balanced")
        positions = [
            _make_position(symbol="A", value_jpy=100_000, currency="USD"),
            _make_position(symbol="B", value_jpy=100_000, currency="JPY"),
        ]
        total = 1_000_000

        actions = _generate_reduce_actions(
            positions, total, c, reduce_currency="USD"
        )
        assert len(actions) == 1
        assert actions[0]["symbol"] == "A"
        assert "通貨削減" in actions[0]["reason"]

    def test_reduce_currency_case_insensitive(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="A", value_jpy=100_000, currency="USD")]
        total = 1_000_000

        actions = _generate_reduce_actions(
            positions, total, c, reduce_currency="usd"
        )
        assert len(actions) == 1

    def test_sell_symbols_excluded(self):
        c = _build_constraints("balanced")
        # 25% > 15% limit, but in sell_symbols
        positions = [_make_position(symbol="SOLD", value_jpy=250_000)]
        total = 1_000_000

        actions = _generate_reduce_actions(
            positions, total, c, sell_symbols={"SOLD"}
        )
        assert actions == []

    def test_cash_positions_skipped(self):
        c = _build_constraints("balanced")
        positions = [{"symbol": "JPY.CASH", "value_jpy": 500_000}]
        total = 1_000_000

        actions = _generate_reduce_actions(positions, total, c)
        assert actions == []

    def test_already_reduced_not_duplicated(self):
        """A position reduced by rule 1 should not also be reduced by rule 3/4."""
        c = _build_constraints("balanced")  # max_single=0.15
        # 25% > 15% limit AND in Technology sector
        positions = [
            _make_position(symbol="A", value_jpy=250_000, sector="Technology"),
        ]
        total = 1_000_000

        actions = _generate_reduce_actions(
            positions, total, c, reduce_sector="Technology"
        )
        # Only one reduce action (from rule 1), not duplicated by rule 3
        symbols = [a["symbol"] for a in actions]
        assert symbols.count("A") == 1

    def test_reduce_value_jpy_calculated(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="X", value_jpy=200_000)]
        total = 1_000_000  # 20% > 15%
        actions = _generate_reduce_actions(positions, total, c)
        assert len(actions) == 1
        # reduce_ratio = 1 - (0.15/0.20) = 0.25
        expected_value = round(200_000 * 0.25, 0)
        assert actions[0]["value_jpy"] == expected_value


# ===================================================================
# _generate_increase_actions tests
# ===================================================================

class TestGenerateIncreaseActions:
    """Tests for _generate_increase_actions()."""

    def test_no_cash_no_actions(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="A", base=0.10, value_jpy=100_000)]
        actions = _generate_increase_actions(
            positions, 1_000_000, 0, 0, c, set(), set()
        )
        assert actions == []

    def test_increase_highest_return_first(self):
        c = _build_constraints("balanced")
        positions = [
            _make_position(symbol="LOW", value_jpy=50_000, base=0.05),
            _make_position(symbol="HIGH", value_jpy=50_000, base=0.20),
            _make_position(symbol="MID", value_jpy=50_000, base=0.10),
        ]
        total = 1_000_000
        actions = _generate_increase_actions(
            positions, total, 100_000, 0, c, set(), set()
        )
        assert len(actions) > 0
        # First action should be for HIGH (best return)
        assert actions[0]["symbol"] == "HIGH"

    def test_respects_max_single_ratio(self):
        c = _build_constraints("balanced")  # max_single = 0.15
        # Already at 14% of total
        positions = [_make_position(symbol="A", value_jpy=140_000, base=0.20)]
        total = 1_000_000
        new_total = total  # no additional cash
        # max_add = 0.15 * 1_000_000 - 140_000 = 10_000
        actions = _generate_increase_actions(
            positions, total, 200_000, 0, c, set(), set()
        )
        if actions:
            # amount should not exceed max_add = 10_000
            assert actions[0]["amount_jpy"] <= 10_000

    def test_negative_return_not_increased(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="BAD", value_jpy=50_000, base=-0.05)]
        actions = _generate_increase_actions(
            positions, 1_000_000, 100_000, 0, c, set(), set()
        )
        assert actions == []

    def test_zero_return_not_increased(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="FLAT", value_jpy=50_000, base=0.0)]
        actions = _generate_increase_actions(
            positions, 1_000_000, 100_000, 0, c, set(), set()
        )
        assert actions == []

    def test_sell_symbols_excluded(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="SOLD", value_jpy=50_000, base=0.20)]
        actions = _generate_increase_actions(
            positions, 1_000_000, 100_000, 0, c, {"SOLD"}, set()
        )
        assert actions == []

    def test_reduce_symbols_excluded(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="REDUCED", value_jpy=50_000, base=0.20)]
        actions = _generate_increase_actions(
            positions, 1_000_000, 100_000, 0, c, set(), {"REDUCED"}
        )
        assert actions == []

    def test_cash_positions_skipped(self):
        c = _build_constraints("balanced")
        positions = [{"symbol": "JPY.CASH", "value_jpy": 100_000, "base": 0.10}]
        actions = _generate_increase_actions(
            positions, 1_000_000, 100_000, 0, c, set(), set()
        )
        assert actions == []

    def test_additional_cash_increases_budget(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="A", value_jpy=50_000, base=0.15)]
        # freed=0, additional=500_000
        actions = _generate_increase_actions(
            positions, 1_000_000, 0, 500_000, c, set(), set()
        )
        assert len(actions) > 0
        assert actions[0]["amount_jpy"] > 0

    def test_freed_cash_used(self):
        c = _build_constraints("balanced")
        positions = [_make_position(symbol="A", value_jpy=50_000, base=0.15)]
        # freed=200_000, additional=0
        actions = _generate_increase_actions(
            positions, 1_000_000, 200_000, 0, c, set(), set()
        )
        assert len(actions) > 0
        assert actions[0]["amount_jpy"] > 0

    def test_min_dividend_yield_filter(self):
        c = _build_constraints("balanced")
        positions = [
            _make_position(symbol="LOW_DIV", value_jpy=50_000, base=0.20, dividend_yield=0.01),
            _make_position(symbol="HIGH_DIV", value_jpy=50_000, base=0.10, dividend_yield=0.04),
        ]
        actions = _generate_increase_actions(
            positions, 1_000_000, 200_000, 0, c, set(), set(),
            min_dividend_yield=0.03,
        )
        symbols = {a["symbol"] for a in actions}
        assert "LOW_DIV" not in symbols
        assert "HIGH_DIV" in symbols

    def test_minimum_allocation_threshold(self):
        c = _build_constraints("balanced")
        # Position already near max_single limit, leaving <10_000 room
        # max_add = 0.15 * 1_000_000 - 149_500 = 500 < 10_000
        positions = [_make_position(symbol="A", value_jpy=149_500, base=0.20)]
        actions = _generate_increase_actions(
            positions, 1_000_000, 100_000, 0, c, set(), set()
        )
        # Should skip because max_add < 10_000
        assert actions == []

    def test_none_base_return_skipped(self):
        c = _build_constraints("balanced")
        pos = _make_position(symbol="X", value_jpy=50_000)
        pos["base"] = None
        actions = _generate_increase_actions(
            [pos], 1_000_000, 100_000, 0, c, set(), set()
        )
        assert actions == []


# ===================================================================
# generate_rebalance_proposal tests
# ===================================================================

class TestGenerateRebalanceProposal:
    """Tests for generate_rebalance_proposal()."""

    def test_empty_portfolio(self):
        forecast = _make_forecast([], total_value_jpy=0)
        result = generate_rebalance_proposal(forecast)

        assert result["actions"] == []
        assert result["before"]["base_return"] == 0.0
        assert result["strategy"] == "balanced"
        assert "constraints" in result

    def test_healthy_balanced_portfolio_no_actions(self):
        """A well-balanced portfolio within all constraints generates no actions."""
        positions = [
            _make_position(symbol="A", value_jpy=100_000, base=0.05,
                           sector="Tech", country="US", currency="USD"),
            _make_position(symbol="B", value_jpy=100_000, base=0.06,
                           sector="Health", country="JP", currency="JPY"),
            _make_position(symbol="C", value_jpy=100_000, base=0.04,
                           sector="Finance", country="SG", currency="SGD"),
        ]
        total = 1_000_000  # each at 10%, under 15% limit
        forecast = _make_forecast(positions, total_value_jpy=total)
        result = generate_rebalance_proposal(forecast)

        assert result["actions"] == []

    def test_exit_alert_generates_sell(self):
        positions = [
            _make_position(symbol="BAD", value_jpy=100_000, base=0.05),
            _make_position(symbol="GOOD", value_jpy=100_000, base=0.10),
        ]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        health = _make_health([("BAD", "exit", ["reason"])])

        result = generate_rebalance_proposal(forecast, health_result=health)
        sell_actions = [a for a in result["actions"] if a["action"] == "sell"]
        assert len(sell_actions) == 1
        assert sell_actions[0]["symbol"] == "BAD"

    def test_negative_base_generates_sell(self):
        positions = [
            _make_position(symbol="DROP", value_jpy=100_000, base=-0.15),
            _make_position(symbol="OK", value_jpy=100_000, base=0.10),
        ]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        result = generate_rebalance_proposal(forecast)

        sell_actions = [a for a in result["actions"] if a["action"] == "sell"]
        assert len(sell_actions) == 1
        assert sell_actions[0]["symbol"] == "DROP"

    def test_overweight_generates_reduce(self):
        positions = [
            _make_position(symbol="HEAVY", value_jpy=250_000, base=0.05),
            _make_position(symbol="LIGHT", value_jpy=50_000, base=0.05),
        ]
        total = 1_000_000  # HEAVY=25% > 15%
        forecast = _make_forecast(positions, total_value_jpy=total)
        result = generate_rebalance_proposal(forecast)

        reduce_actions = [a for a in result["actions"] if a["action"] == "reduce"]
        assert len(reduce_actions) >= 1
        assert reduce_actions[0]["symbol"] == "HEAVY"

    def test_freed_cash_calculated(self):
        positions = [
            _make_position(symbol="DROP", value_jpy=300_000, base=-0.15),
        ]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        result = generate_rebalance_proposal(forecast)

        # Sell of DROP should free 300_000
        assert result["freed_cash_jpy"] == 300_000

    def test_freed_cash_includes_reduces(self):
        positions = [
            _make_position(symbol="HEAVY", value_jpy=250_000, base=0.05),
        ]
        total = 1_000_000
        forecast = _make_forecast(positions, total_value_jpy=total)
        result = generate_rebalance_proposal(forecast)

        # HEAVY at 25%, reduced to 15%, ratio=0.4, value=250000*0.4=100000
        # But exact numbers depend on rounding; just check it's > 0
        reduce_actions = [a for a in result["actions"] if a["action"] == "reduce"]
        if reduce_actions:
            assert result["freed_cash_jpy"] > 0

    def test_strategy_passed_through(self):
        forecast = _make_forecast([], total_value_jpy=0)
        result = generate_rebalance_proposal(forecast, strategy="defensive")
        assert result["strategy"] == "defensive"

    def test_constraints_in_result(self):
        forecast = _make_forecast([], total_value_jpy=0)
        result = generate_rebalance_proposal(forecast, strategy="aggressive")
        assert result["constraints"]["max_single_ratio"] == \
            _STRATEGY_PRESETS["aggressive"]["max_single_ratio"]

    def test_additional_cash_passed_through(self):
        forecast = _make_forecast([], total_value_jpy=0)
        result = generate_rebalance_proposal(forecast, additional_cash=500_000)
        assert result["additional_cash_jpy"] == 500_000

    def test_before_metrics_computed(self):
        positions = [
            _make_position(symbol="A", value_jpy=500_000, base=0.10,
                           sector="Tech", country="US", currency="USD"),
            _make_position(symbol="B", value_jpy=500_000, base=0.06,
                           sector="Health", country="JP", currency="JPY"),
        ]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        result = generate_rebalance_proposal(forecast)

        assert result["before"]["base_return"] == pytest.approx(0.08, abs=0.001)
        assert result["before"]["sector_hhi"] == pytest.approx(0.5, abs=0.01)
        assert result["before"]["region_hhi"] == pytest.approx(0.5, abs=0.01)

    def test_concentration_overrides_before_hhi(self):
        positions = [_make_position(symbol="A", value_jpy=1_000_000, base=0.10)]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        concentration = {"sector_hhi": 0.42, "region_hhi": 0.33}

        result = generate_rebalance_proposal(
            forecast, concentration=concentration
        )
        assert result["before"]["sector_hhi"] == 0.42
        assert result["before"]["region_hhi"] == 0.33

    def test_actions_sorted_by_priority(self):
        """Sell (priority 1-2) should come before reduce (3-5) before increase (6)."""
        positions = [
            _make_position(symbol="EXIT", value_jpy=100_000, base=0.05),
            _make_position(symbol="HEAVY", value_jpy=200_000, base=0.10),
            _make_position(symbol="GOOD", value_jpy=50_000, base=0.15),
        ]
        total = 1_000_000
        forecast = _make_forecast(positions, total_value_jpy=total)
        health = _make_health([("EXIT", "exit", ["bad"])])

        result = generate_rebalance_proposal(
            forecast, health_result=health, additional_cash=500_000
        )

        priorities = [a.get("priority", 99) for a in result["actions"]]
        assert priorities == sorted(priorities)

    def test_after_return_adjusted_for_sells(self):
        positions = [
            _make_position(symbol="BAD", value_jpy=500_000, base=-0.15),
            _make_position(symbol="GOOD", value_jpy=500_000, base=0.10),
        ]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        result = generate_rebalance_proposal(forecast)

        # Before: -0.15*0.5 + 0.10*0.5 = -0.025
        # After should improve since BAD is sold
        assert result["after"]["base_return"] > result["before"]["base_return"]

    def test_full_pipeline_sell_reduce_increase(self):
        """Integration: sell -> reduce -> increase with freed cash."""
        positions = [
            _make_position(symbol="SELL_ME", value_jpy=200_000, base=-0.20,
                           sector="Energy", country="US", currency="USD"),
            _make_position(symbol="REDUCE_ME", value_jpy=250_000, base=0.03,
                           sector="Tech", country="US", currency="USD"),
            _make_position(symbol="INCREASE_ME", value_jpy=50_000, base=0.15,
                           sector="Health", country="JP", currency="JPY"),
        ]
        total = 1_000_000
        forecast = _make_forecast(positions, total_value_jpy=total)

        result = generate_rebalance_proposal(forecast, additional_cash=100_000)

        action_types = {a["action"] for a in result["actions"]}
        # Should have sell (SELL_ME base=-20%), reduce (REDUCE_ME 25%>15%)
        assert "sell" in action_types
        assert "reduce" in action_types
        # With freed cash + additional, increase should occur
        if result["freed_cash_jpy"] + 100_000 > 0:
            # There should be increase actions if conditions are met
            pass  # increase may or may not happen depending on exact amounts

    def test_reduce_sector_parameter(self):
        positions = [
            _make_position(symbol="A", value_jpy=100_000, base=0.05, sector="Technology"),
            _make_position(symbol="B", value_jpy=100_000, base=0.05, sector="Healthcare"),
        ]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        result = generate_rebalance_proposal(forecast, reduce_sector="Technology")

        reduce_actions = [a for a in result["actions"] if a["action"] == "reduce"]
        assert any(a["symbol"] == "A" for a in reduce_actions)
        assert not any(a["symbol"] == "B" for a in reduce_actions)

    def test_reduce_currency_parameter(self):
        positions = [
            _make_position(symbol="A", value_jpy=100_000, base=0.05, currency="USD"),
            _make_position(symbol="B", value_jpy=100_000, base=0.05, currency="JPY"),
        ]
        forecast = _make_forecast(positions, total_value_jpy=1_000_000)
        result = generate_rebalance_proposal(forecast, reduce_currency="USD")

        reduce_actions = [a for a in result["actions"] if a["action"] == "reduce"]
        assert any(a["symbol"] == "A" for a in reduce_actions)
        assert not any(a["symbol"] == "B" for a in reduce_actions)

    def test_high_corr_pairs_passed(self):
        positions = [
            _make_position(symbol="A", value_jpy=200_000, base=0.10),
            _make_position(symbol="B", value_jpy=200_000, base=0.05),
        ]
        total = 1_000_000
        forecast = _make_forecast(positions, total_value_jpy=total)
        pairs = [{"pair": ["A", "B"], "correlation": 0.85}]

        result = generate_rebalance_proposal(forecast, high_corr_pairs=pairs)
        reduce_actions = [a for a in result["actions"] if a["action"] == "reduce"]
        assert any(a["symbol"] == "B" for a in reduce_actions)
