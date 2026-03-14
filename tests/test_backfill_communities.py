"""Tests for scripts/backfill_communities.py (KIK-548).

Neo4j driver is mocked -- no real database connection needed.
"""

import pytest
from unittest.mock import MagicMock, patch, call

pytestmark = pytest.mark.no_auto_mock


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
def setup_driver(mock_driver):
    """Set up graph_store with a mock driver."""
    import src.data.graph_store as gs

    driver, session = mock_driver
    gs._driver = driver
    return driver, session


# ===================================================================
# backfill()
# ===================================================================


class TestBackfill:
    def test_returns_empty_no_driver(self):
        from scripts.backfill_communities import backfill

        with patch("scripts.backfill_communities._get_driver", return_value=None):
            result = backfill()
        assert result == {}

    def test_insufficient_data(self, setup_driver):
        """Fewer than 2 stocks returns stats with zero communities."""
        from scripts.backfill_communities import backfill

        _, session = setup_driver
        # Return 1 stock from screen query, empty from others
        r1 = MagicMock()
        r1.__getitem__ = lambda s, k: {"symbol": "A", "ids": ["s1"]}[k]
        session.run.return_value = iter([r1])

        result = backfill()
        assert result["stock_count"] == 1
        assert result["community_count"] == 0
        assert result["isolated_count"] == 1

    def test_no_similarity_edges(self, setup_driver):
        """All stocks are disjoint → no communities."""
        from scripts.backfill_communities import backfill

        _, session = setup_driver

        def mock_run(query_str, **kwargs):
            if "SURFACED" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "ids": ["s1"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "ids": ["s2"]}[k]
                return iter([r1, r2])
            return iter([])

        session.run.side_effect = mock_run

        result = backfill(similarity_cutoff=0.5)
        assert result["stock_count"] == 2
        assert result["community_count"] == 0
        assert result["isolated_count"] == 2

    def test_successful_backfill(self, setup_driver):
        """Full pipeline returns valid stats."""
        from scripts.backfill_communities import backfill

        _, session = setup_driver

        def mock_run(query_str, **kwargs):
            result = MagicMock()
            # Auto-naming queries (more specific, check first)
            if "IN_SECTOR" in query_str and "cnt" in query_str:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Technology", "cnt": 2}[k]
                result.single.return_value = rec
                return result
            elif "HAS_THEME" in query_str and "cnt" in query_str:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "AI", "cnt": 2}[k]
                result.single.return_value = rec
                return result
            # Co-occurrence queries
            elif "SURFACED" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "ids": ["s1", "s2"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "ids": ["s1", "s2"]}[k]
                return iter([r1, r2])
            elif "HAS_THEME" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "names": ["AI"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "names": ["AI"]}[k]
                return iter([r1, r2])
            elif "IN_SECTOR" in query_str:
                return iter([])
            elif "MENTIONS" in query_str:
                return iter([])
            # Save queries
            return result

        session.run.side_effect = mock_run

        with patch("src.data.graph_store._get_mode", return_value="full"):
            result = backfill(similarity_cutoff=0.1)

        assert result["stock_count"] == 2
        assert result["community_count"] >= 1
        assert result["max_size"] >= 1
        assert result["isolated_count"] == 0

    def test_dry_run_does_not_save(self, setup_driver):
        """Dry run computes stats but does not save."""
        from scripts.backfill_communities import backfill

        _, session = setup_driver

        def mock_run(query_str, **kwargs):
            result = MagicMock()
            if "IN_SECTOR" in query_str and "cnt" in query_str:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Technology", "cnt": 2}[k]
                result.single.return_value = rec
                return result
            elif "HAS_THEME" in query_str and "cnt" in query_str:
                result.single.return_value = None
                return result
            elif "SURFACED" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "ids": ["s1"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "ids": ["s1"]}[k]
                return iter([r1, r2])
            elif "HAS_THEME" in query_str:
                return iter([])
            elif "IN_SECTOR" in query_str:
                return iter([])
            elif "MENTIONS" in query_str:
                return iter([])
            return result

        session.run.side_effect = mock_run

        result = backfill(similarity_cutoff=0.1, dry_run=True)
        assert result["stock_count"] == 2
        # No DETACH DELETE or CREATE should have been called
        calls = [str(c) for c in session.run.call_args_list]
        assert not any("DETACH DELETE" in c for c in calls)

    def test_idempotent(self, setup_driver):
        """Running backfill twice should produce same results."""
        from scripts.backfill_communities import backfill

        _, session = setup_driver

        def mock_run(query_str, **kwargs):
            result = MagicMock()
            if "IN_SECTOR" in query_str and "cnt" in query_str:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Tech", "cnt": 2}[k]
                result.single.return_value = rec
                return result
            elif "HAS_THEME" in query_str and "cnt" in query_str:
                result.single.return_value = None
                return result
            elif "SURFACED" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "X", "ids": ["s1"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "Y", "ids": ["s1"]}[k]
                return iter([r1, r2])
            elif "HAS_THEME" in query_str:
                return iter([])
            elif "IN_SECTOR" in query_str:
                return iter([])
            elif "MENTIONS" in query_str:
                return iter([])
            return result

        session.run.side_effect = mock_run

        with patch("src.data.graph_store._get_mode", return_value="full"):
            result1 = backfill(similarity_cutoff=0.1)
            result2 = backfill(similarity_cutoff=0.1)

        assert result1["stock_count"] == result2["stock_count"]
        assert result1["community_count"] == result2["community_count"]


# ===================================================================
# _print_report
# ===================================================================


class TestPrintReport:
    def test_empty_stats(self, capsys):
        from scripts.backfill_communities import _print_report

        _print_report({})
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_report_with_communities(self, capsys):
        from scripts.backfill_communities import _print_report

        stats = {
            "stock_count": 10,
            "community_count": 3,
            "max_size": 5,
            "min_size": 2,
            "avg_size": 3.3,
            "isolated_count": 1,
            "communities": [
                {"community_id": 0, "name": "Tech x AI", "size": 5, "members": ["A", "B", "C", "D", "E"]},
                {"community_id": 1, "name": "Healthcare", "size": 3, "members": ["F", "G", "H"]},
                {"community_id": 2, "name": "Community_2", "size": 2, "members": ["I", "J"]},
            ],
        }
        _print_report(stats)
        captured = capsys.readouterr()
        assert "Stock nodes processed:  10" in captured.out
        assert "Communities generated:  3" in captured.out
        assert "Max cluster size:       5" in captured.out
        assert "Isolated nodes:         1" in captured.out
        assert "Tech x AI" in captured.out
        assert "Healthcare" in captured.out

    def test_report_dry_run_prefix(self, capsys):
        from scripts.backfill_communities import _print_report

        stats = {
            "stock_count": 0,
            "community_count": 0,
            "max_size": 0,
            "min_size": 0,
            "avg_size": 0.0,
            "isolated_count": 0,
            "communities": [],
        }
        _print_report(stats, dry_run=True)
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out

    def test_report_many_members_truncated(self, capsys):
        from scripts.backfill_communities import _print_report

        stats = {
            "stock_count": 8,
            "community_count": 1,
            "max_size": 8,
            "min_size": 8,
            "avg_size": 8.0,
            "isolated_count": 0,
            "communities": [
                {"community_id": 0, "name": "Big", "size": 8,
                 "members": ["A", "B", "C", "D", "E", "F", "G", "H"]},
            ],
        }
        _print_report(stats)
        captured = capsys.readouterr()
        assert "+3 more" in captured.out


# ===================================================================
# Empty graph
# ===================================================================


class TestEmptyGraph:
    def test_empty_graph_no_error(self, setup_driver):
        """Empty Neo4j graph should not error."""
        from scripts.backfill_communities import backfill

        _, session = setup_driver
        session.run.return_value = iter([])

        result = backfill()
        assert result["stock_count"] == 0
        assert result["community_count"] == 0
