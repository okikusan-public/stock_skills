"""Tests for src.core.scenario_analysis module."""

import pytest

from src.core.scenario_analysis import (
    SCENARIOS,
    SCENARIO_ALIASES,
    resolve_scenario,
    compute_stock_scenario_impact,
    analyze_portfolio_scenario,
    _infer_currency,
    _infer_region,
    _match_target,
)


# ===================================================================
# resolve_scenario
# ===================================================================


class TestResolveScenario:
    def test_direct_key(self):
        """Direct scenario key lookup should work."""
        result = resolve_scenario("triple_decline")
        assert result is not None
        assert result["name"] == "トリプル安（株安・債券安・円安）"

    def test_japanese_alias_triple_decline(self):
        """Japanese alias 'トリプル安' -> triple_decline."""
        result = resolve_scenario("トリプル安")
        assert result is not None
        assert result["base_shock"] == -0.20

    def test_japanese_alias_recession(self):
        """'リセッション' -> us_recession."""
        result = resolve_scenario("リセッション")
        assert result is not None
        assert "リセッション" in result["name"]

    def test_english_alias(self):
        """English alias 'recession' -> us_recession."""
        result = resolve_scenario("recession")
        assert result is not None
        assert result["base_shock"] == -0.25

    def test_case_insensitive(self):
        """Lookup should be case-insensitive for keys."""
        result = resolve_scenario("TRIPLE_DECLINE")
        assert result is not None

    def test_nonexistent_scenario_returns_none(self):
        """Unknown scenario name should return None."""
        result = resolve_scenario("nonexistent_scenario")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        result = resolve_scenario("")
        assert result is None

    def test_all_predefined_scenarios_resolvable(self):
        """Every key in SCENARIOS should be resolvable."""
        for key in SCENARIOS:
            result = resolve_scenario(key)
            assert result is not None, f"Scenario '{key}' should be resolvable"

    def test_all_aliases_resolvable(self):
        """Every alias in SCENARIO_ALIASES should resolve to a valid scenario."""
        for alias in SCENARIO_ALIASES:
            result = resolve_scenario(alias)
            assert result is not None, f"Alias '{alias}' should resolve"

    def test_boj_aliases(self):
        """'利上げ', '日銀', 'boj' -> boj_rate_hike."""
        for alias in ("利上げ", "日銀", "boj"):
            result = resolve_scenario(alias)
            assert result is not None
            assert result["trigger"] == "インフレ持続で追加利上げ"

    def test_yen_depreciation_aliases(self):
        """'ドル高', '円安', 'yen' -> yen_depreciation."""
        for alias in ("ドル高", "円安", "yen"):
            result = resolve_scenario(alias)
            assert result is not None
            assert result["base_shock"] == -0.10


# ===================================================================
# _infer_currency / _infer_region helpers
# ===================================================================


class TestInferCurrency:
    def test_from_stock_info(self):
        """stock_info['currency'] takes priority."""
        assert _infer_currency("7203.T", {"currency": "EUR"}) == "EUR"

    def test_from_suffix_japan(self):
        assert _infer_currency("7203.T", {}) == "JPY"

    def test_from_suffix_singapore(self):
        assert _infer_currency("D05.SI", {}) == "SGD"

    def test_no_suffix_defaults_usd(self):
        assert _infer_currency("AAPL", {}) == "USD"


class TestInferRegion:
    def test_from_stock_info_country(self):
        assert _infer_region("AAPL", {"country": "Japan"}) == "Japan"

    def test_from_suffix(self):
        assert _infer_region("7203.T", {}) == "Japan"

    def test_no_suffix_defaults_us(self):
        assert _infer_region("AAPL", {}) == "US"


# ===================================================================
# compute_stock_scenario_impact
# ===================================================================


class TestStockScenarioImpact:
    def _make_japan_stock(self, **overrides):
        base = {
            "symbol": "7203.T",
            "name": "Toyota",
            "sector": "Consumer Cyclical",
            "price": 2800.0,
            "beta": 1.0,
            "currency": "JPY",
            "country": "Japan",
        }
        base.update(overrides)
        return base

    def _make_us_stock(self, **overrides):
        base = {
            "symbol": "AAPL",
            "name": "Apple",
            "sector": "Technology",
            "price": 180.0,
            "beta": 1.2,
            "currency": "USD",
            "country": "US",
        }
        base.update(overrides)
        return base

    def test_basic_impact_calculation(self):
        """Base shock * beta should be the starting direct_impact."""
        stock = self._make_japan_stock(beta=1.0)
        scenario = resolve_scenario("triple_decline")
        result = compute_stock_scenario_impact(stock, {}, scenario)

        assert result["symbol"] == "7203.T"
        assert "direct_impact" in result
        assert "currency_impact" in result
        assert "total_impact" in result
        assert "causal_chain" in result

    def test_beta_amplifies_shock(self):
        """Higher beta should increase the magnitude of direct_impact."""
        stock_low_beta = self._make_us_stock(beta=0.5)
        stock_high_beta = self._make_us_stock(beta=2.0)
        scenario = resolve_scenario("us_recession")

        result_low = compute_stock_scenario_impact(stock_low_beta, {}, scenario)
        result_high = compute_stock_scenario_impact(stock_high_beta, {}, scenario)

        # Higher beta -> more negative direct impact (in absolute terms)
        assert result_high["direct_impact"] < result_low["direct_impact"]

    def test_japan_stock_triple_decline_currency_impact(self):
        """JPY stock in triple_decline: currency_impact should be 0 (JPY asset)."""
        stock = self._make_japan_stock()
        scenario = resolve_scenario("triple_decline")
        result = compute_stock_scenario_impact(stock, {}, scenario)

        # JPY currency -> no foreign currency impact
        assert result["currency_impact"] == 0.0

    def test_us_stock_triple_decline_currency_impact(self):
        """USD stock in triple_decline: should have currency impact (impact_on_foreign)."""
        stock = self._make_us_stock()
        scenario = resolve_scenario("triple_decline")
        result = compute_stock_scenario_impact(stock, {}, scenario)

        # USD stock should receive currency effect from triple_decline
        # impact_on_foreign = +0.097 (yen depreciation benefits foreign assets)
        assert result["currency_impact"] != 0.0

    def test_causal_chain_populated(self):
        """causal_chain should be a non-empty list of strings."""
        stock = self._make_japan_stock()
        scenario = resolve_scenario("triple_decline")
        result = compute_stock_scenario_impact(stock, {}, scenario)

        assert isinstance(result["causal_chain"], list)
        assert len(result["causal_chain"]) > 0
        assert all(isinstance(s, str) for s in result["causal_chain"])

    def test_sensitivity_adjustment(self):
        """When composite_shock is provided, it should adjust the direct_impact."""
        stock = self._make_japan_stock()
        scenario = resolve_scenario("triple_decline")

        result_no_sens = compute_stock_scenario_impact(stock, {}, scenario)
        result_with_sens = compute_stock_scenario_impact(
            stock, {"composite_shock": -0.5}, scenario
        )

        # With negative composite_shock, the adjustment factor < 1.0
        # so impact should differ
        assert result_no_sens["direct_impact"] != result_with_sens["direct_impact"]

    def test_price_impact_calculated(self):
        """price_impact = price * total_impact."""
        stock = self._make_japan_stock(price=1000.0, beta=1.0)
        scenario = resolve_scenario("triple_decline")
        result = compute_stock_scenario_impact(stock, {}, scenario)

        expected_price_impact = stock["price"] * result["total_impact"]
        assert abs(result["price_impact"] - round(expected_price_impact, 2)) < 0.05

    def test_sector_matching(self):
        """A Technology stock should match 'グロース株' target (Technology sector)."""
        stock = self._make_us_stock(sector="Technology")
        scenario = resolve_scenario("boj_rate_hike")  # has グロース株 in primary
        result = compute_stock_scenario_impact(stock, {}, scenario)

        # Should have matched some sector-based effects
        assert len(result["causal_chain"]) > 1  # base + at least one match


# ===================================================================
# analyze_portfolio_scenario
# ===================================================================


class TestPortfolioScenario:
    def test_single_stock_portfolio(self):
        """Single stock with weight=1.0."""
        portfolio = [{
            "symbol": "7203.T",
            "name": "Toyota",
            "sector": "Consumer Cyclical",
            "price": 2800.0,
            "beta": 1.0,
            "currency": "JPY",
            "country": "Japan",
        }]
        scenario = resolve_scenario("triple_decline")
        result = analyze_portfolio_scenario(portfolio, [{}], [1.0], scenario)

        assert result["scenario_name"] == "トリプル安（株安・債券安・円安）"
        assert "portfolio_impact" in result
        assert "judgment" in result
        assert result["judgment"] in ("継続", "認識", "要対応")

    def test_multi_stock_weighted_impact(self):
        """Portfolio impact is the weighted average of per-stock impacts."""
        stock_jp = {
            "symbol": "7203.T", "name": "Toyota",
            "sector": "Consumer Cyclical", "price": 2800.0,
            "beta": 1.0, "currency": "JPY", "country": "Japan",
        }
        stock_us = {
            "symbol": "AAPL", "name": "Apple",
            "sector": "Technology", "price": 180.0,
            "beta": 1.2, "currency": "USD", "country": "US",
        }
        scenario = resolve_scenario("triple_decline")
        weights = [0.6, 0.4]

        result = analyze_portfolio_scenario(
            [stock_jp, stock_us], [{}, {}], weights, scenario
        )

        assert len(result["stock_impacts"]) == 2
        assert result["stock_impacts"][0]["weight"] == 0.6
        assert result["stock_impacts"][1]["weight"] == 0.4
        assert isinstance(result["portfolio_impact"], float)

    def test_judgment_severe_scenario(self):
        """Very negative portfolio_impact -> '要対応'."""
        # Use a stock with high beta to maximize impact
        stock = {
            "symbol": "RISKY",
            "sector": "Consumer Cyclical",
            "price": 100.0,
            "beta": 3.0,
            "currency": "JPY",
            "country": "Japan",
        }
        scenario = resolve_scenario("us_recession")  # base_shock = -0.25
        result = analyze_portfolio_scenario([stock], [{}], [1.0], scenario)

        # With beta=3.0, direct_impact starts at -0.75, likely > -0.30 total
        if result["portfolio_impact"] <= -0.30:
            assert result["judgment"] == "要対応"
        elif result["portfolio_impact"] <= -0.15:
            assert result["judgment"] == "認識"
        else:
            assert result["judgment"] == "継続"

    def test_judgment_mild_scenario(self):
        """Mild impact -> '継続'."""
        stock = {
            "symbol": "SAFE",
            "sector": "Consumer Defensive",
            "price": 100.0,
            "beta": 0.3,
            "currency": "JPY",
            "country": "Japan",
        }
        # yen_depreciation has base_shock = -0.10
        scenario = resolve_scenario("yen_depreciation")
        result = analyze_portfolio_scenario([stock], [{}], [1.0], scenario)

        # With low beta and JPY, impact should be mild
        if result["portfolio_impact"] > -0.15:
            assert result["judgment"] == "継続"

    def test_causal_chain_summary_generated(self):
        """causal_chain_summary should be a non-empty string."""
        stock = {
            "symbol": "7203.T", "sector": "Industrials",
            "price": 2800.0, "beta": 1.0, "currency": "JPY", "country": "Japan",
        }
        scenario = resolve_scenario("triple_decline")
        result = analyze_portfolio_scenario([stock], [{}], [1.0], scenario)

        assert isinstance(result["causal_chain_summary"], str)
        assert len(result["causal_chain_summary"]) > 0
        assert "トリガー" in result["causal_chain_summary"]

    def test_offset_factors_included(self):
        """offset_factors should come from the scenario definition."""
        scenario = resolve_scenario("triple_decline")
        stock = {
            "symbol": "7203.T", "sector": "Industrials",
            "price": 2800.0, "beta": 1.0, "currency": "JPY", "country": "Japan",
        }
        result = analyze_portfolio_scenario([stock], [{}], [1.0], scenario)

        assert isinstance(result["offset_factors"], list)
        # triple_decline has offset factors
        assert len(result["offset_factors"]) > 0

    def test_time_axis_included(self):
        """time_axis should come from the scenario definition."""
        scenario = resolve_scenario("triple_decline")
        stock = {
            "symbol": "7203.T", "sector": "Industrials",
            "price": 2800.0, "beta": 1.0, "currency": "JPY", "country": "Japan",
        }
        result = analyze_portfolio_scenario([stock], [{}], [1.0], scenario)

        assert isinstance(result["time_axis"], str)
        assert len(result["time_axis"]) > 0

    def test_missing_sensitivities_padded(self):
        """If sensitivities list is shorter than portfolio, it should be padded with {}."""
        stocks = [
            {"symbol": "A", "price": 100.0, "beta": 1.0, "currency": "JPY", "country": "Japan"},
            {"symbol": "B", "price": 200.0, "beta": 1.0, "currency": "JPY", "country": "Japan"},
        ]
        scenario = resolve_scenario("triple_decline")

        # Only one sensitivity for two stocks
        result = analyze_portfolio_scenario(stocks, [{}], [0.5, 0.5], scenario)
        assert len(result["stock_impacts"]) == 2

    def test_missing_weights_filled(self):
        """If weights list is shorter than portfolio, remaining weight is distributed equally."""
        stocks = [
            {"symbol": "A", "price": 100.0, "beta": 1.0, "currency": "JPY", "country": "Japan"},
            {"symbol": "B", "price": 200.0, "beta": 1.0, "currency": "JPY", "country": "Japan"},
        ]
        scenario = resolve_scenario("triple_decline")

        # Only one weight for two stocks
        result = analyze_portfolio_scenario(stocks, [{}, {}], [0.5], scenario)
        assert len(result["stock_impacts"]) == 2
        # Second stock should get the remaining weight
        assert result["stock_impacts"][1]["weight"] == 0.5


# ===================================================================
# KIK-354: New scenarios and alias improvements
# ===================================================================


class TestKIK354NewScenarios:
    """Tests for tech_crash and yen_appreciation scenarios (KIK-354)."""

    def test_scenarios_count_is_8(self):
        """Should have 8 predefined scenarios after adding 2 new ones."""
        assert len(SCENARIOS) == 8

    def test_tech_crash_defined(self):
        """tech_crash scenario should exist with correct base_shock."""
        assert "tech_crash" in SCENARIOS
        sc = SCENARIOS["tech_crash"]
        assert sc["base_shock"] == -0.30
        assert "テック暴落" in sc["name"]

    def test_yen_appreciation_defined(self):
        """yen_appreciation scenario should exist with correct base_shock."""
        assert "yen_appreciation" in SCENARIOS
        sc = SCENARIOS["yen_appreciation"]
        assert sc["base_shock"] == -0.10
        assert "円高ドル安" in sc["name"]

    def test_tech_crash_effects_structure(self):
        """tech_crash should have proper effects structure."""
        effects = SCENARIOS["tech_crash"]["effects"]
        assert len(effects["primary"]) >= 2
        assert len(effects["secondary"]) >= 2
        assert "currency" in effects
        assert effects["currency"]["usd_jpy_change"] < 0  # risk-off yen strengthening

    def test_yen_appreciation_effects_structure(self):
        """yen_appreciation should have proper effects structure."""
        effects = SCENARIOS["yen_appreciation"]["effects"]
        assert len(effects["primary"]) >= 2
        assert "currency" in effects
        assert effects["currency"]["usd_jpy_change"] == -20

    def test_tech_crash_hits_tech_sector(self):
        """Tech stock should receive significant damage in tech_crash."""
        stock = {
            "symbol": "NVDA", "name": "NVIDIA", "sector": "Technology",
            "country": "United States", "currency": "USD",
            "price": 900, "beta": 1.8,
        }
        scenario = SCENARIOS["tech_crash"]
        result = compute_stock_scenario_impact(stock, {}, scenario)
        assert result["total_impact"] < -0.30

    def test_tech_crash_spares_defensive(self):
        """Defensive stock should be less impacted in tech_crash."""
        stock = {
            "symbol": "2914.T", "name": "ツムラ", "sector": "Healthcare",
            "country": "Japan", "currency": "JPY",
            "price": 3000, "beta": 0.4,
        }
        scenario = SCENARIOS["tech_crash"]
        result = compute_stock_scenario_impact(stock, {}, scenario)
        # Defensive should be less impacted
        assert result["direct_impact"] > -0.30

    def test_yen_appreciation_hurts_usd_assets(self):
        """USD-denominated assets should lose value in yen_appreciation."""
        stock = {
            "symbol": "AAPL", "name": "Apple", "sector": "Technology",
            "country": "United States", "currency": "USD",
            "price": 200, "beta": 1.2,
        }
        scenario = SCENARIOS["yen_appreciation"]
        result = compute_stock_scenario_impact(stock, {}, scenario)
        assert result["currency_impact"] < 0

    def test_yen_appreciation_no_currency_impact_jpy(self):
        """JPY stocks should have no currency impact in yen_appreciation."""
        stock = {
            "symbol": "9501.T", "name": "関西電力", "sector": "Utilities",
            "country": "Japan", "currency": "JPY",
            "price": 2000, "beta": 0.5,
        }
        scenario = SCENARIOS["yen_appreciation"]
        result = compute_stock_scenario_impact(stock, {}, scenario)
        assert result["currency_impact"] == 0.0

    def test_portfolio_tech_crash_scenario_name(self):
        """Portfolio analysis should report tech_crash scenario name."""
        stock = {
            "symbol": "NVDA", "sector": "Technology",
            "price": 900, "beta": 1.8, "currency": "USD", "country": "US",
        }
        scenario = SCENARIOS["tech_crash"]
        result = analyze_portfolio_scenario([stock], [{}], [1.0], scenario)
        assert result["scenario_name"] == "テック暴落"

    def test_portfolio_yen_appreciation_scenario_name(self):
        """Portfolio analysis should report yen_appreciation scenario name."""
        stock = {
            "symbol": "7203.T", "sector": "Industrials",
            "price": 2800, "beta": 1.0, "currency": "JPY", "country": "Japan",
        }
        scenario = SCENARIOS["yen_appreciation"]
        result = analyze_portfolio_scenario([stock], [{}], [1.0], scenario)
        assert result["scenario_name"] == "円高ドル安"


class TestKIK354Aliases:
    """Tests for improved alias resolution (KIK-354)."""

    def test_tech_crash_aliases(self):
        """Various tech crash aliases should resolve."""
        for alias in ["テック暴落", "tech暴落", "AI暴落", "ナスダック暴落", "tech"]:
            result = resolve_scenario(alias)
            assert result is not None, f"Alias '{alias}' failed"
            assert result["name"] == "テック暴落"

    def test_yen_appreciation_aliases(self):
        """Various yen appreciation aliases should resolve."""
        for alias in ["円高ドル安", "円高", "ドル安"]:
            result = resolve_scenario(alias)
            assert result is not None, f"Alias '{alias}' failed"
            assert result["name"] == "円高ドル安"

    def test_existing_aliases_not_broken(self):
        """Existing aliases must still work after adding new ones."""
        cases = {
            "トリプル安": "トリプル安（株安・債券安・円安）",
            "リセッション": "米国リセッション",
            "景気後退": "米国リセッション",
            "利上げ": "日銀利上げ加速",
            "米中": "米中対立激化",
            "インフレ": "インフレ再燃",
            "ドル高": "ドル高円安",
            "円安": "ドル高円安",
        }
        for alias, expected_name in cases.items():
            result = resolve_scenario(alias)
            assert result is not None, f"Alias '{alias}' failed"
            assert result["name"] == expected_name

    def test_new_explicit_aliases(self):
        """New explicit aliases for existing scenarios should work."""
        cases = {
            "日銀利上げ": "日銀利上げ加速",
            "金利上昇": "日銀利上げ加速",
            "米中対立": "米中対立激化",
            "地政学リスク": "米中対立激化",
            "貿易戦争": "米中対立激化",
            "インフレ再燃": "インフレ再燃",
            "物価上昇": "インフレ再燃",
            "米国リセッション": "米国リセッション",
            "為替ショック": "ドル高円安",
            "ドル高円安": "ドル高円安",
            "株安・円安・債券安": "トリプル安（株安・債券安・円安）",
        }
        for alias, expected_name in cases.items():
            result = resolve_scenario(alias)
            assert result is not None, f"Alias '{alias}' failed"
            assert result["name"] == expected_name

    def test_partial_match_with_suffix(self):
        """Partial match should work when input contains alias."""
        result = resolve_scenario("テック暴落シナリオ")
        assert result is not None
        assert result["name"] == "テック暴落"

    def test_partial_match_with_prefix(self):
        """Partial match should work when alias contains input."""
        result = resolve_scenario("円高")
        assert result is not None


class TestMatchTargetKIK354:
    """Tests for new _match_target entries (KIK-354)."""

    def test_tech_stock_matches_tech(self):
        assert _match_target("テック株", "Technology", "USD", "US") is True
        assert _match_target("テック株", "Communication Services", "USD", "US") is True

    def test_non_tech_matches(self):
        assert _match_target("非テック株", "Healthcare", "USD", "US") is True
        assert _match_target("非テック株", "Financial Services", "JPY", "Japan") is True

    def test_non_tech_excludes_tech(self):
        assert _match_target("非テック株", "Technology", "USD", "US") is False
        assert _match_target("非テック株", "Communication Services", "USD", "US") is False


# ===================================================================
# KIK-358: ETF asset class matching
# ===================================================================


class TestETFAssetClassMapping:
    """Tests for ETF asset class detection (KIK-358)."""

    def test_gldm_is_gold(self):
        from src.core.scenario_analysis import _get_etf_asset_class
        assert _get_etf_asset_class("GLDM", {}) == "金・安全資産"

    def test_tlt_is_bond(self):
        from src.core.scenario_analysis import _get_etf_asset_class
        assert _get_etf_asset_class("TLT", {}) == "長期債"

    def test_jepi_is_equity_income(self):
        from src.core.scenario_analysis import _get_etf_asset_class
        assert _get_etf_asset_class("JEPI", {}) == "株式インカム"

    def test_regular_stock_returns_none(self):
        from src.core.scenario_analysis import _get_etf_asset_class
        assert _get_etf_asset_class("AAPL", {}) is None

    def test_unknown_etf_falls_back_to_equity_income(self):
        from src.core.scenario_analysis import _get_etf_asset_class
        assert _get_etf_asset_class("XYZ", {"quoteType": "ETF"}) == "株式インカム"

    def test_match_target_gold_etf(self):
        assert _match_target("金・安全資産", None, "USD", "US", etf_asset_class="金・安全資産") is True

    def test_match_target_bond_etf(self):
        assert _match_target("長期債", None, "USD", "US", etf_asset_class="長期債") is True

    def test_match_target_equity_income_as_cyclical(self):
        """株式インカムETF should also match シクリカル株."""
        assert _match_target("シクリカル株", None, "USD", "US", etf_asset_class="株式インカム") is True

    def test_match_target_no_etf_class_no_match(self):
        """Without etf_asset_class, 金・安全資産 should not match sector=None."""
        assert _match_target("金・安全資産", None, "USD", "US") is False


class TestETFScenarioImpact:
    """Tests for ETF scenario impact calculations (KIK-358)."""

    def _make_etf(self, symbol, **overrides):
        base = {
            "symbol": symbol,
            "name": symbol,
            "sector": None,
            "price": 50.0,
            "beta": 0.5,
            "currency": "USD",
            "country": "US",
            "quoteType": "ETF",
        }
        base.update(overrides)
        return base

    def test_gldm_positive_in_tech_crash(self):
        """GLDM (gold) should have positive impact in tech_crash (金・安全資産 +6%)."""
        stock = self._make_etf("GLDM", beta=0.1)
        scenario = SCENARIOS["tech_crash"]
        result = compute_stock_scenario_impact(stock, {}, scenario)
        # Should match 金・安全資産 +6%, not fallback to base_shock
        assert result["direct_impact"] > 0

    def test_tlt_negative_in_inflation(self):
        """TLT (bonds) should be negatively impacted in inflation_resurgence (長期債 -10%)."""
        stock = self._make_etf("TLT", beta=0.2)
        scenario = SCENARIOS["inflation_resurgence"]
        result = compute_stock_scenario_impact(stock, {}, scenario)
        # Should match 長期債 -10%
        assert result["direct_impact"] < -0.05

    def test_jepi_matches_cyclical_in_recession(self):
        """JEPI (equity income) should match シクリカル株 in us_recession."""
        stock = self._make_etf("JEPI", beta=0.66)
        scenario = SCENARIOS["us_recession"]
        result = compute_stock_scenario_impact(stock, {}, scenario)
        # Should match シクリカル株 -35%, adjusted by beta
        assert result["direct_impact"] < -0.15

    def test_etfs_not_all_same_impact(self):
        """GLDM, JEPI, TLT should NOT all have the same impact in recession."""
        gldm = self._make_etf("GLDM", beta=0.1)
        jepi = self._make_etf("JEPI", beta=0.66)
        tlt = self._make_etf("TLT", beta=0.2)
        scenario = SCENARIOS["us_recession"]

        r_gldm = compute_stock_scenario_impact(gldm, {}, scenario)
        r_jepi = compute_stock_scenario_impact(jepi, {}, scenario)
        r_tlt = compute_stock_scenario_impact(tlt, {}, scenario)

        # They should NOT all be the same (the original bug)
        impacts = {r_gldm["direct_impact"], r_jepi["direct_impact"], r_tlt["direct_impact"]}
        assert len(impacts) > 1, "ETFs should have different impacts based on asset class"

    def test_gldm_less_negative_than_equity_in_yen_appreciation(self):
        """GLDM (gold) should be less negative than equity ETF in yen_appreciation.

        Both match 全外貨資産 (-13%), but GLDM also matches 金・安全資産 (+5%)
        which partially offsets the forex loss.
        """
        gldm = self._make_etf("GLDM", beta=0.1)
        jepi = self._make_etf("JEPI", beta=0.66)
        scenario = SCENARIOS["yen_appreciation"]
        r_gldm = compute_stock_scenario_impact(gldm, {}, scenario)
        r_jepi = compute_stock_scenario_impact(jepi, {}, scenario)
        # Gold benefit should make GLDM less negative than equity ETF
        assert r_gldm["direct_impact"] > r_jepi["direct_impact"]
