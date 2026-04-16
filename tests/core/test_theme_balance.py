"""Tests for src.core.health.theme_balance (KIK-605).

Theme concentration, sector-relative PER warnings, and theme cooling detection.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def positions_3_ai():
    """3 positions in AI theme."""
    return [
        {"symbol": "NVDA", "weight": 0.10, "sector": "Technology", "per": 60.0},
        {"symbol": "MSFT", "weight": 0.08, "sector": "Technology", "per": 35.0},
        {"symbol": "GOOG", "weight": 0.07, "sector": "Communication Services", "per": 25.0},
    ]


@pytest.fixture
def positions_2_ai():
    """2 positions in AI theme (below threshold)."""
    return [
        {"symbol": "NVDA", "weight": 0.10, "sector": "Technology", "per": 60.0},
        {"symbol": "MSFT", "weight": 0.08, "sector": "Technology", "per": 35.0},
    ]


@pytest.fixture
def themes_map_ai():
    """Theme map with AI theme."""
    return {
        "NVDA": ["ai", "semiconductor"],
        "MSFT": ["ai", "cloud"],
        "GOOG": ["ai", "advertising"],
    }


@pytest.fixture
def themes_map_ai_2():
    """Theme map for 2 AI stocks."""
    return {
        "NVDA": ["ai", "semiconductor"],
        "MSFT": ["ai", "cloud"],
    }


@pytest.fixture
def sector_median_per():
    return {
        "Technology": 28.0,
        "Communication Services": 22.0,
        "Financials": 12.0,
    }


# ---------------------------------------------------------------------------
# check_theme_concentration
# ---------------------------------------------------------------------------

class TestCheckThemeConcentration:
    def test_3_stocks_triggers_warning(self, positions_3_ai, themes_map_ai):
        """3 stocks in same theme should trigger a warning."""
        from src.core.health.theme_balance import check_theme_concentration
        warnings = check_theme_concentration(positions_3_ai, themes_map_ai)
        ai_warnings = [w for w in warnings if w["theme"] == "ai"]
        assert len(ai_warnings) == 1
        assert ai_warnings[0]["stock_count"] == 3
        assert ai_warnings[0]["level"] in ("warn", "danger")

    def test_2_stocks_no_warning(self, positions_2_ai, themes_map_ai_2):
        """2 stocks in same theme, weight under 20%, should not trigger."""
        from src.core.health.theme_balance import check_theme_concentration
        warnings = check_theme_concentration(positions_2_ai, themes_map_ai_2)
        ai_warnings = [w for w in warnings if w["theme"] == "ai"]
        assert len(ai_warnings) == 0

    def test_high_weight_triggers_warning(self):
        """Even 2 stocks, if weight > 20%, should trigger."""
        from src.core.health.theme_balance import check_theme_concentration
        positions = [
            {"symbol": "NVDA", "weight": 0.15},
            {"symbol": "MSFT", "weight": 0.10},
        ]
        themes = {"NVDA": ["ai"], "MSFT": ["ai"]}
        warnings = check_theme_concentration(positions, themes)
        ai_warnings = [w for w in warnings if w["theme"] == "ai"]
        assert len(ai_warnings) == 1
        assert ai_warnings[0]["weight"] > 0.20

    def test_danger_level_both_exceeded(self, positions_3_ai, themes_map_ai):
        """Both count and weight exceeded should produce 'danger' level."""
        from src.core.health.theme_balance import check_theme_concentration
        # Make weights higher to exceed 20%
        positions = [
            {"symbol": "NVDA", "weight": 0.10},
            {"symbol": "MSFT", "weight": 0.08},
            {"symbol": "GOOG", "weight": 0.07},
        ]
        themes = {"NVDA": ["ai"], "MSFT": ["ai"], "GOOG": ["ai"]}
        warnings = check_theme_concentration(positions, themes)
        ai_warnings = [w for w in warnings if w["theme"] == "ai"]
        assert len(ai_warnings) == 1
        # weight = 0.25 > 0.20 and count = 3 >= 3 → danger
        assert ai_warnings[0]["level"] == "danger"

    def test_no_themes_no_warnings(self):
        """Empty themes map should produce no warnings."""
        from src.core.health.theme_balance import check_theme_concentration
        positions = [{"symbol": "NVDA", "weight": 0.30}]
        warnings = check_theme_concentration(positions, {})
        assert warnings == []

    def test_empty_positions(self):
        """Empty positions list should produce no warnings."""
        from src.core.health.theme_balance import check_theme_concentration
        warnings = check_theme_concentration([], {"NVDA": ["ai"]})
        assert warnings == []

    def test_symbols_included_in_warning(self, positions_3_ai, themes_map_ai):
        """Warning should list the involved symbols."""
        from src.core.health.theme_balance import check_theme_concentration
        warnings = check_theme_concentration(positions_3_ai, themes_map_ai)
        ai_warnings = [w for w in warnings if w["theme"] == "ai"]
        assert len(ai_warnings) == 1
        assert set(ai_warnings[0]["symbols"]) == {"NVDA", "MSFT", "GOOG"}

    def test_custom_thresholds(self):
        """Custom thresholds from config should be respected."""
        from src.core.health.theme_balance import check_theme_concentration
        positions = [
            {"symbol": "A", "weight": 0.05},
            {"symbol": "B", "weight": 0.05},
        ]
        themes = {"A": ["x"], "B": ["x"]}
        # Default thresholds: 3 stocks or 20% weight → no warning
        warnings = check_theme_concentration(positions, themes)
        assert len(warnings) == 0

        # Override to 2 stocks max
        with patch("src.core.health.theme_balance.th") as mock_th:
            mock_th.side_effect = lambda section, key, default: {
                ("theme_balance", "max_theme_weight", 0.20): 0.20,
                ("theme_balance", "max_theme_stocks", 3): 2,
            }.get((section, key, default), default)
            warnings = check_theme_concentration(positions, themes)
            x_warn = [w for w in warnings if w["theme"] == "x"]
            assert len(x_warn) == 1

    def test_invalid_weight_treated_as_zero(self):
        """Non-numeric weight should be treated as 0."""
        from src.core.health.theme_balance import check_theme_concentration
        positions = [
            {"symbol": "A", "weight": "invalid"},
            {"symbol": "B", "weight": None},
            {"symbol": "C", "weight": 0.30},
        ]
        themes = {"A": ["x"], "B": ["x"], "C": ["x"]}
        warnings = check_theme_concentration(positions, themes)
        x_warn = [w for w in warnings if w["theme"] == "x"]
        assert len(x_warn) == 1
        # weight should be 0.30 (only C's weight counts)
        assert x_warn[0]["weight"] == 0.30


# ---------------------------------------------------------------------------
# check_sector_relative_per
# ---------------------------------------------------------------------------

class TestCheckSectorRelativePer:
    def test_high_per_triggers_warning(self, sector_median_per):
        """PER 2x+ above sector median should trigger."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "NVDA", "sector": "Technology", "per": 60.0},
        ]
        warnings = check_sector_relative_per(positions, sector_median_per)
        assert len(warnings) == 1
        assert warnings[0]["symbol"] == "NVDA"
        assert warnings[0]["ratio"] >= 2.0

    def test_normal_per_no_warning(self, sector_median_per):
        """PER below 2x sector median should not trigger."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "MSFT", "sector": "Technology", "per": 35.0},
        ]
        warnings = check_sector_relative_per(positions, sector_median_per)
        assert len(warnings) == 0

    def test_exactly_2x_triggers(self, sector_median_per):
        """PER exactly at multiplier boundary should trigger."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "TEST", "sector": "Technology", "per": 56.0},  # 56/28 = 2.0
        ]
        warnings = check_sector_relative_per(positions, sector_median_per)
        assert len(warnings) == 1

    def test_missing_sector_median_skips(self):
        """Missing sector in median map should skip."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "X", "sector": "Unknown", "per": 100.0},
        ]
        warnings = check_sector_relative_per(positions, {"Technology": 28.0})
        assert len(warnings) == 0

    def test_zero_per_skips(self, sector_median_per):
        """PER of 0 or negative should skip."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "X", "sector": "Technology", "per": 0},
            {"symbol": "Y", "sector": "Technology", "per": -5.0},
        ]
        warnings = check_sector_relative_per(positions, sector_median_per)
        assert len(warnings) == 0

    def test_none_per_skips(self, sector_median_per):
        """None PER should skip."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "X", "sector": "Technology", "per": None},
        ]
        warnings = check_sector_relative_per(positions, sector_median_per)
        assert len(warnings) == 0

    def test_zero_sector_median_skips(self):
        """Sector median of 0 should skip (avoid division by zero)."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "X", "sector": "Tech", "per": 50.0},
        ]
        warnings = check_sector_relative_per(positions, {"Tech": 0.0})
        assert len(warnings) == 0

    def test_multiple_positions(self, sector_median_per):
        """Multiple positions: only the high-PER one should warn."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "NVDA", "sector": "Technology", "per": 60.0},
            {"symbol": "MSFT", "sector": "Technology", "per": 35.0},
            {"symbol": "JPM", "sector": "Financials", "per": 10.0},
        ]
        warnings = check_sector_relative_per(positions, sector_median_per)
        assert len(warnings) == 1
        assert warnings[0]["symbol"] == "NVDA"

    def test_warning_includes_ratio(self, sector_median_per):
        """Warning should include the ratio value."""
        from src.core.health.theme_balance import check_sector_relative_per
        positions = [
            {"symbol": "NVDA", "sector": "Technology", "per": 70.0},
        ]
        warnings = check_sector_relative_per(positions, sector_median_per)
        assert warnings[0]["ratio"] == 2.5  # 70/28 = 2.5


# ---------------------------------------------------------------------------
# detect_theme_cooling
# ---------------------------------------------------------------------------

class TestDetectThemeCooling:
    def test_confidence_drop_detected(self):
        """Confidence decrease should produce 'cooling' status."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = [{"theme": "ai", "confidence": 0.9}]
        curr = [{"theme": "ai", "confidence": 0.5}]
        result = detect_theme_cooling(curr, prev)
        assert len(result) == 1
        assert result[0]["status"] == "cooling"
        assert result[0]["prev_confidence"] == 0.9
        assert result[0]["current_confidence"] == 0.5

    def test_theme_gone_detected(self):
        """Theme disappeared from current scan → 'gone' status."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = [{"theme": "ev", "confidence": 0.8}]
        curr = []
        result = detect_theme_cooling(curr, prev)
        assert len(result) == 1
        assert result[0]["status"] == "gone"
        assert result[0]["theme"] == "ev"
        assert result[0]["current_confidence"] == 0.0

    def test_no_change_no_cooling(self):
        """Same confidence → no cooling detected."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = [{"theme": "ai", "confidence": 0.8}]
        curr = [{"theme": "ai", "confidence": 0.8}]
        result = detect_theme_cooling(curr, prev)
        assert len(result) == 0

    def test_confidence_increase_no_cooling(self):
        """Confidence increase → not cooling."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = [{"theme": "ai", "confidence": 0.5}]
        curr = [{"theme": "ai", "confidence": 0.9}]
        result = detect_theme_cooling(curr, prev)
        assert len(result) == 0

    def test_new_theme_not_reported(self):
        """Theme that only appears in current (new) → not reported."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = []
        curr = [{"theme": "defense", "confidence": 0.7}]
        result = detect_theme_cooling(curr, prev)
        assert len(result) == 0

    def test_multiple_themes_mixed(self):
        """Mix of cooling, gone, and stable themes."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = [
            {"theme": "ai", "confidence": 0.9},
            {"theme": "ev", "confidence": 0.8},
            {"theme": "biotech", "confidence": 0.6},
        ]
        curr = [
            {"theme": "ai", "confidence": 0.5},    # cooling
            # ev is gone
            {"theme": "biotech", "confidence": 0.7},  # increased
            {"theme": "defense", "confidence": 0.8},  # new
        ]
        result = detect_theme_cooling(curr, prev)
        themes = {r["theme"] for r in result}
        assert themes == {"ai", "ev"}
        ev = next(r for r in result if r["theme"] == "ev")
        assert ev["status"] == "gone"
        ai = next(r for r in result if r["theme"] == "ai")
        assert ai["status"] == "cooling"

    def test_gone_sorted_before_cooling(self):
        """'gone' themes should appear before 'cooling' themes."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = [
            {"theme": "ai", "confidence": 0.9},
            {"theme": "ev", "confidence": 0.8},
        ]
        curr = [
            {"theme": "ai", "confidence": 0.5},
            # ev gone
        ]
        result = detect_theme_cooling(curr, prev)
        assert result[0]["status"] == "gone"
        assert result[1]["status"] == "cooling"

    def test_case_insensitive_matching(self):
        """Theme names should be matched case-insensitively."""
        from src.core.health.theme_balance import detect_theme_cooling
        prev = [{"theme": "AI", "confidence": 0.9}]
        curr = [{"theme": "ai", "confidence": 0.5}]
        result = detect_theme_cooling(curr, prev)
        assert len(result) == 1
        assert result[0]["theme"] == "ai"

    def test_empty_both(self):
        """Both empty → no results."""
        from src.core.health.theme_balance import detect_theme_cooling
        result = detect_theme_cooling([], [])
        assert result == []


# ---------------------------------------------------------------------------
# Thresholds config loading
# ---------------------------------------------------------------------------

class TestThresholdsConfig:
    def test_theme_balance_defaults_when_missing(self):
        """th() should return defaults when config key is missing."""
        from src.core._thresholds import th
        # Even if config section is missing, defaults should work
        val = th("theme_balance_nonexistent", "max_theme_weight", 0.20)
        assert val == 0.20

    def test_theme_balance_config_loaded(self):
        """Config values should load from thresholds.yaml."""
        from src.core._thresholds import th
        # These should be set in config/thresholds.yaml
        max_weight = th("theme_balance", "max_theme_weight", 0.20)
        max_stocks = th("theme_balance", "max_theme_stocks", 3)
        per_mult = th("theme_balance", "per_warn_multiplier", 2.0)
        fng_thresh = th("theme_balance", "fng_caution_threshold", 80)
        stale_days = th("theme_balance", "theme_stale_days", 90)
        # Verify they match what we put in the YAML
        assert max_weight == 0.20
        assert max_stocks == 3
        assert per_mult == 2.0
        assert fng_thresh == 80
        assert stale_days == 90


# ---------------------------------------------------------------------------
# Proactive engine: theme staleness suggestion
# ---------------------------------------------------------------------------

class TestProactiveThemeStaleness:
    def test_theme_staleness_triggers_suggestion(self):
        """Stale theme in PF should trigger suggestion."""
        from src.core.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()

        stale_date = (date.today() - timedelta(days=100)).isoformat()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {"name": "ai", "updated_at": stale_date}
        mock_result.__iter__ = lambda self: iter([mock_record])
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda self: mock_session
        mock_driver.session.return_value.__exit__ = lambda self, *a: None

        with patch(
            "src.data.graph_query.get_current_holdings",
            return_value=[{"symbol": "NVDA"}],
        ), patch(
            "src.data.graph_query.get_themes_for_symbols_batch",
            return_value={"NVDA": ["ai"]},
        ), patch(
            "src.data.graph_query._common._get_driver",
            return_value=mock_driver,
        ):
            result = engine._check_theme_staleness()
        assert len(result) == 1
        assert "ai" in result[0]["title"]
        assert result[0]["urgency"] == "medium"

    def test_fresh_theme_no_suggestion(self):
        """Fresh theme should not trigger suggestion."""
        from src.core.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()

        fresh_date = (date.today() - timedelta(days=10)).isoformat()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {"name": "ai", "updated_at": fresh_date}
        mock_result.__iter__ = lambda self: iter([mock_record])
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda self: mock_session
        mock_driver.session.return_value.__exit__ = lambda self, *a: None

        with patch(
            "src.data.graph_query.get_current_holdings",
            return_value=[{"symbol": "NVDA"}],
        ), patch(
            "src.data.graph_query.get_themes_for_symbols_batch",
            return_value={"NVDA": ["ai"]},
        ), patch(
            "src.data.graph_query._common._get_driver",
            return_value=mock_driver,
        ):
            result = engine._check_theme_staleness()
        assert len(result) == 0

    def test_no_holdings_no_suggestion(self):
        """No holdings should produce no suggestion."""
        from src.core.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()

        with patch(
            "src.data.graph_query.get_current_holdings",
            return_value=[],
        ):
            result = engine._check_theme_staleness()
        assert result == []

    def test_no_themes_no_suggestion(self):
        """Holdings without themes should produce no suggestion."""
        from src.core.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()

        with patch(
            "src.data.graph_query.get_current_holdings",
            return_value=[{"symbol": "NVDA"}],
        ), patch(
            "src.data.graph_query.get_themes_for_symbols_batch",
            return_value={},
        ):
            result = engine._check_theme_staleness()
        assert result == []

    def test_neo4j_error_graceful_degradation(self):
        """Neo4j error should return empty (graceful degradation)."""
        from src.core.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()

        with patch(
            "src.data.graph_query.get_current_holdings",
            side_effect=Exception("Neo4j down"),
        ):
            result = engine._check_theme_staleness()
        assert result == []

    def test_null_updated_at_triggers_suggestion(self):
        """Theme with null updated_at should trigger suggestion."""
        from src.core.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {"name": "ev", "updated_at": None}
        mock_result.__iter__ = lambda self: iter([mock_record])
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda self: mock_session
        mock_driver.session.return_value.__exit__ = lambda self, *a: None

        with patch(
            "src.data.graph_query.get_current_holdings",
            return_value=[{"symbol": "TSLA"}],
        ), patch(
            "src.data.graph_query.get_themes_for_symbols_batch",
            return_value={"TSLA": ["ev"]},
        ), patch(
            "src.data.graph_query._common._get_driver",
            return_value=mock_driver,
        ):
            result = engine._check_theme_staleness()
        assert len(result) == 1
        assert "ev" in result[0]["title"]


# ---------------------------------------------------------------------------
# Re-export from health __init__
# ---------------------------------------------------------------------------

class TestHealthReExport:
    def test_theme_balance_importable_from_health(self):
        """Functions should be importable from src.core.health."""
        from src.core.health import (
            check_theme_concentration,
            check_sector_relative_per,
            detect_theme_cooling,
        )
        assert callable(check_theme_concentration)
        assert callable(check_sector_relative_per)
        assert callable(detect_theme_cooling)
