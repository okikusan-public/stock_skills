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
        # 21 constraints + 14 indexes + 10 vector indexes = 45 (KIK-414/420/428)
        assert session.run.call_count == 45

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
                "researches": [],
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
        assert "researches" in result
        # 7 queries: screens, reports, trades, health_checks, notes, themes, researches
        assert session.run.call_count == 7

    def test_get_stock_history_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        result = gs.get_stock_history("7203.T")
        assert result["screens"] == []
        assert result["themes"] == []
        assert result["researches"] == []


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

    def test_research_id_format(self, gs_with_driver):
        gs, _, session = gs_with_driver
        gs.merge_research("2025-01-15", "stock", "7203.T")
        kwargs = session.run.call_args_list[0][1]
        assert kwargs["id"] == "research_2025-01-15_stock_7203_T"

    def test_research_id_japanese(self, gs_with_driver):
        gs, _, session = gs_with_driver
        gs.merge_research("2025-01-15", "industry", "半導体")
        kwargs = session.run.call_args_list[0][1]
        assert kwargs["id"] == "research_2025-01-15_industry____"


# ===================================================================
# merge_research tests (KIK-398)
# ===================================================================

class TestMergeResearch:
    def test_merge_research_stock(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_research("2025-01-15", "stock", "7203.T", "Toyota analysis") is True
        # 1 MERGE research + 1 RESEARCHED rel (stock type links to Stock)
        assert session.run.call_count == 2

    def test_merge_research_industry(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_research("2025-01-15", "industry", "半導体", "Semiconductor trends") is True
        # 1 MERGE research only (industry type does NOT link to Stock)
        assert session.run.call_count == 1

    def test_merge_research_market(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_research("2025-01-15", "market", "日経平均") is True
        assert session.run.call_count == 1

    def test_merge_research_business(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_research("2025-01-15", "business", "7751.T") is True
        # business type also links to Stock
        assert session.run.call_count == 2

    def test_merge_research_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_research("2025-01-15", "stock", "7203.T") is False

    def test_merge_research_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gs.merge_research("2025-01-15", "stock", "7203.T") is False


# ===================================================================
# merge_watchlist tests (KIK-398)
# ===================================================================

class TestMergeWatchlist:
    def test_merge_watchlist_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        symbols = ["7203.T", "AAPL", "D05.SI"]
        assert gs.merge_watchlist("my-list", symbols) is True
        # 1 MERGE watchlist + 3 BOOKMARKED relationships
        assert session.run.call_count == 4

    def test_merge_watchlist_empty(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_watchlist("empty-list", []) is True
        assert session.run.call_count == 1

    def test_merge_watchlist_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_watchlist("my-list", ["7203.T"]) is False

    def test_merge_watchlist_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gs.merge_watchlist("my-list", ["7203.T"]) is False


# ===================================================================
# link_research_supersedes tests (KIK-398)
# ===================================================================

class TestLinkResearchSupersedes:
    def test_link_supersedes_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.link_research_supersedes("stock", "7203.T") is True
        assert session.run.call_count == 1
        kwargs = session.run.call_args[1]
        assert kwargs["rtype"] == "stock"
        assert kwargs["target"] == "7203.T"

    def test_link_supersedes_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.link_research_supersedes("stock", "7203.T") is False

    def test_link_supersedes_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gs.link_research_supersedes("stock", "7203.T") is False


# ===================================================================
# clear_all tests (KIK-398)
# ===================================================================

class TestClearAll:
    def test_clear_all_success(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.clear_all() is True
        assert session.run.call_count == 1
        cypher = session.run.call_args[0][0]
        assert "DETACH DELETE" in cypher

    def test_clear_all_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.clear_all() is False

    def test_clear_all_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gs.clear_all() is False


# ===================================================================
# _safe_id tests (KIK-398)
# ===================================================================

# ===================================================================
# merge_market_context tests (KIK-399)
# ===================================================================

class TestMergeMarketContext:
    def test_merge_market_context_basic(self, gs_with_driver):
        gs, _, session = gs_with_driver
        indices = [{"name": "S&P500", "price": 5800}, {"name": "日経平均", "price": 40000}]
        assert gs.merge_market_context("2025-02-17", indices) is True
        assert session.run.call_count == 1
        kwargs = session.run.call_args[1]
        assert kwargs["id"] == "market_context_2025-02-17"
        assert kwargs["date"] == "2025-02-17"
        import json
        parsed = json.loads(kwargs["indices"])
        assert len(parsed) == 2
        assert parsed[0]["name"] == "S&P500"

    def test_merge_market_context_empty_indices(self, gs_with_driver):
        gs, _, session = gs_with_driver
        assert gs.merge_market_context("2025-02-17", []) is True
        kwargs = session.run.call_args[1]
        assert kwargs["indices"] == "[]"

    def test_merge_market_context_no_driver(self):
        import src.data.graph_store as gs
        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gs.merge_market_context("2025-02-17", []) is False

    def test_merge_market_context_error(self, gs_with_driver):
        gs, driver, _ = gs_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gs.merge_market_context("2025-02-17", []) is False


class TestSafeId:
    def test_safe_id_symbol(self):
        from src.data.graph_store import _safe_id
        assert _safe_id("7203.T") == "7203_T"

    def test_safe_id_japanese(self):
        from src.data.graph_store import _safe_id
        assert _safe_id("半導体") == "___"

    def test_safe_id_clean(self):
        from src.data.graph_store import _safe_id
        assert _safe_id("AAPL") == "AAPL"
