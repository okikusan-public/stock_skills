"""Tests for src.data.graph_store module (KIK-397).

Neo4j driver is mocked -- no real database connection needed.
"""

import pytest
from unittest.mock import MagicMock, patch, call


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(autouse=True)
def reset_driver():
    """Reset global _driver before each test."""
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


@pytest.fixture
def mock_driver():
    """Provide a mock Neo4j driver with session context manager."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


@pytest.fixture
def gs_with_driver(mock_driver):
    """Set up graph_store with a mock driver already injected."""
    import src.data.graph_store as gs
    driver, session = mock_driver
    gs._driver = driver
    return gs, driver, session


# ===================================================================
# Connection tests
# ===================================================================

class TestConnection:
    def test_is_available_no_driver(self):
        """is_available returns False when driver is None."""
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.is_available() is False

    def test_is_available_success(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.verify_connectivity.return_value = None
        assert gs.is_available() is True

    def test_is_available_connection_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.verify_connectivity.side_effect = Exception("Connection refused")
        assert gs.is_available() is False

    def test_close_resets_driver(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        gs.close()
        assert gs._driver is None
        driver.close.assert_called_once()

    def test_close_noop_when_none(self):
        import src.data.graph_store as gs
        gs._driver = None
        gs.close()  # Should not raise


# ===================================================================
# Schema tests
# ===================================================================

class TestSchema:
    def test_init_schema_success(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.init_schema() is True
        # 8 constraints + 5 indexes = 13 statements
        assert session.run.call_count == 13

    def test_init_schema_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.init_schema() is False

    def test_init_schema_error(self, gs_with_driver):
        gs, driver, session = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("DB error")
        assert gs.init_schema() is False


# ===================================================================
# merge_stock tests
# ===================================================================

class TestMergeStock:
    def test_merge_stock_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_stock("7203.T", "Toyota", "Automotive") is True
        assert session.run.call_count == 2  # MERGE stock + MERGE sector

    def test_merge_stock_no_sector(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_stock("7203.T") is True
        assert session.run.call_count == 1  # Only MERGE stock, no sector

    def test_merge_stock_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_stock("7203.T") is False

    def test_merge_stock_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gs.merge_stock("7203.T") is False


# ===================================================================
# merge_screen tests
# ===================================================================

class TestMergeScreen:
    def test_merge_screen_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        symbols = ["7203.T", "AAPL"]
        assert gs.merge_screen("2025-01-15", "value", "japan", 2, symbols) is True
        # 1 MERGE screen + 2 SURFACED relationships
        assert session.run.call_count == 3

    def test_merge_screen_empty_symbols(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_screen("2025-01-15", "alpha", "us", 0, []) is True
        assert session.run.call_count == 1

    def test_merge_screen_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_screen("2025-01-15", "value", "japan", 0, []) is False


# ===================================================================
# merge_report tests
# ===================================================================

class TestMergeReport:
    def test_merge_report_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_report("2025-01-15", "7203.T", 72.5, "割安") is True
        assert session.run.call_count == 2  # MERGE report + ANALYZED rel

    def test_merge_report_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_report("2025-01-15", "7203.T", 72.5, "割安") is False


# ===================================================================
# merge_trade tests
# ===================================================================

class TestMergeTrade:
    def test_merge_trade_buy(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_trade("2025-01-15", "buy", "7203.T", 100, 2850, "JPY", "test") is True
        assert session.run.call_count == 2
        # Verify BOUGHT relationship type in the Cypher
        cypher = session.run.call_args_list[1][0][0]
        assert "BOUGHT" in cypher

    def test_merge_trade_sell(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_trade("2025-01-15", "sell", "AAPL", 5, 175.0, "USD") is True
        cypher = session.run.call_args_list[1][0][0]
        assert "SOLD" in cypher

    def test_merge_trade_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_trade("2025-01-15", "buy", "7203.T", 100, 2850, "JPY") is False


# ===================================================================
# merge_health tests
# ===================================================================

class TestMergeHealth:
    def test_merge_health_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        summary = {"total": 5, "healthy": 3, "exit": 1}
        symbols = ["7203.T", "AAPL", "D05.SI"]
        assert gs.merge_health("2025-01-15", summary, symbols) is True
        assert session.run.call_count == 4  # 1 MERGE + 3 CHECKED

    def test_merge_health_empty_summary(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_health("2025-01-15", {}, []) is True
        assert session.run.call_count == 1


# ===================================================================
# merge_note tests
# ===================================================================

class TestMergeNote:
    def test_merge_note_with_symbol(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_note(
            "note_2025-01-15_7203.T_abc123",
            "2025-01-15", "thesis", "Strong buy",
            symbol="7203.T", source="manual",
        ) is True
        assert session.run.call_count == 2  # MERGE note + ABOUT rel

    def test_merge_note_without_symbol(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_note(
            "note_2025-01-15_general_abc123",
            "2025-01-15", "observation", "Market is volatile",
        ) is True
        assert session.run.call_count == 1  # Only MERGE note, no ABOUT


# ===================================================================
# tag_theme tests
# ===================================================================

class TestTagTheme:
    def test_tag_theme_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.tag_theme("7203.T", "EV") is True
        assert session.run.call_count == 1

    def test_tag_theme_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.tag_theme("7203.T", "EV") is False


# ===================================================================
# get_stock_history tests
# ===================================================================

class TestGetStockHistory:
    def test_get_stock_history_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            result = gs.get_stock_history("7203.T")
            assert result == {
                "screens": [], "reports": [], "trades": [],
                "health_checks": [], "notes": [], "themes": [],
            }

    def test_get_stock_history_success(self, gs_with_driver):
        gs, _, session = gs_with_driver
        # Mock session.run to return empty results for each query
        session.run.return_value = iter([])
        result = gs.get_stock_history("7203.T")
        assert "screens" in result
        assert "reports" in result
        assert "trades" in result
        assert "health_checks" in result
        assert "notes" in result
        assert "themes" in result
        # 6 queries: screens, reports, trades, health_checks, notes, themes
        assert session.run.call_count == 6

    def test_get_stock_history_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        result = gs.get_stock_history("7203.T")
        assert result["screens"] == []
        assert result["themes"] == []


# ===================================================================
# ID generation tests
# ===================================================================

class TestIdGeneration:
    def test_screen_id_format(self, gs_with_driver):
        gs, _, session = gs_with_driver
        gs.merge_screen("2025-01-15", "value", "japan", 5, [])
        cypher_call = session.run.call_args_list[0]
        kwargs = cypher_call[1]
        assert kwargs["id"] == "screen_2025-01-15_japan_value"

    def test_report_id_format(self, gs_with_driver):
        gs, _, session = gs_with_driver
        gs.merge_report("2025-01-15", "7203.T", 72.5, "割安")
        kwargs = session.run.call_args_list[0][1]
        assert kwargs["id"] == "report_2025-01-15_7203.T"

    def test_trade_id_format(self, gs_with_driver):
        gs, _, session = gs_with_driver
        gs.merge_trade("2025-01-15", "buy", "7203.T", 100, 2850, "JPY")
        kwargs = session.run.call_args_list[0][1]
        assert kwargs["id"] == "trade_2025-01-15_buy_7203.T"

    def test_health_id_format(self, gs_with_driver):
        gs, _, session = gs_with_driver
        gs.merge_health("2025-01-15", {}, [])
        kwargs = session.run.call_args_list[0][1]
        assert kwargs["id"] == "health_2025-01-15"
