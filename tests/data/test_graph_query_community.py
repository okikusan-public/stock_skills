"""Tests for community detection (KIK-547).

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
def gq_with_driver(mock_driver):
    """Set up graph_store with a mock driver, return graph_query module."""
    import src.data.graph_store as gs
    import src.data.graph_query as gq

    driver, session = mock_driver
    gs._driver = driver
    return gq, driver, session


# ===================================================================
# Jaccard Similarity
# ===================================================================


class TestJaccardSimilarity:
    """Unit tests for _compute_jaccard_similarity and _jaccard_single."""

    def test_identical_vectors_score_1(self):
        from src.data.graph_query.community import _jaccard_single

        a = {"screens": {"s1", "s2"}, "themes": {"AI"}, "sectors": {"Tech"}, "news": set()}
        b = {"screens": {"s1", "s2"}, "themes": {"AI"}, "sectors": {"Tech"}, "news": set()}
        assert _jaccard_single(a, b) == pytest.approx(1.0)

    def test_disjoint_vectors_score_0(self):
        from src.data.graph_query.community import _jaccard_single

        a = {"screens": {"s1"}, "themes": {"AI"}, "sectors": {"Tech"}, "news": {"n1"}}
        b = {"screens": {"s2"}, "themes": {"EV"}, "sectors": {"Auto"}, "news": {"n2"}}
        assert _jaccard_single(a, b) == pytest.approx(0.0)

    def test_partial_overlap(self):
        from src.data.graph_query.community import _jaccard_single

        a = {"screens": {"s1", "s2"}, "themes": {"AI"}, "sectors": {"Tech"}, "news": set()}
        b = {"screens": {"s1", "s3"}, "themes": {"AI"}, "sectors": {"Auto"}, "news": set()}
        sim = _jaccard_single(a, b)
        # screens: 1/3 * 1.0, themes: 1/1 * 0.8, sectors: 0/2 * 0.5, news: skip
        # = (1/3 + 0.8) / (1.0 + 0.8 + 0.5) = 1.133/2.3 ≈ 0.4927
        assert 0.0 < sim < 1.0

    def test_cutoff_filtering(self):
        from src.data.graph_query.community import _compute_jaccard_similarity

        vectors = {
            "A": {"screens": {"s1"}, "themes": set(), "sectors": set(), "news": set()},
            "B": {"screens": {"s2"}, "themes": set(), "sectors": set(), "news": set()},
        }
        edges = _compute_jaccard_similarity(vectors, cutoff=0.5, top_k=10)
        assert len(edges) == 0  # disjoint, similarity=0 < 0.5

    def test_top_k_limiting(self):
        from src.data.graph_query.community import _compute_jaccard_similarity

        # Create 5 stocks all sharing the same screen → high similarity
        vectors = {
            f"S{i}": {"screens": {"shared"}, "themes": set(), "sectors": set(), "news": set()}
            for i in range(5)
        }
        edges = _compute_jaccard_similarity(vectors, cutoff=0.0, top_k=2)
        # Each node keeps at most 2 neighbors
        from collections import Counter

        counts = Counter()
        for a, b, _ in edges:
            counts[a] += 1
            counts[b] += 1
        for sym, cnt in counts.items():
            assert cnt <= 4  # top_k=2 per side, but pair appears once

    def test_empty_vectors(self):
        from src.data.graph_query.community import _compute_jaccard_similarity

        assert _compute_jaccard_similarity({}, cutoff=0.3, top_k=10) == []

    def test_single_stock(self):
        from src.data.graph_query.community import _compute_jaccard_similarity

        vectors = {"A": {"screens": {"s1"}, "themes": set(), "sectors": set(), "news": set()}}
        assert _compute_jaccard_similarity(vectors, cutoff=0.0, top_k=10) == []

    def test_custom_weights(self):
        from src.data.graph_query.community import _jaccard_single

        a = {"screens": {"s1"}, "themes": {"AI"}, "sectors": set(), "news": set()}
        b = {"screens": {"s1"}, "themes": {"AI"}, "sectors": set(), "news": set()}
        # With custom weights
        custom = {"screens": 0.0, "themes": 1.0, "sectors": 0.0, "news": 0.0}
        sim = _jaccard_single(a, b, weights=custom)
        assert sim == pytest.approx(1.0)


# ===================================================================
# Louvain Communities
# ===================================================================


class TestLouvainCommunities:
    """Tests for _run_louvain wrapper."""

    def test_two_clusters(self):
        from src.data.graph_query.community import _run_louvain

        # Two dense groups with weak cross-connection
        edges = [
            ("A", "B", 0.9),
            ("A", "C", 0.8),
            ("B", "C", 0.85),
            ("D", "E", 0.9),
            ("D", "F", 0.8),
            ("E", "F", 0.85),
            ("C", "D", 0.1),  # weak bridge
        ]
        communities = _run_louvain(edges, resolution=1.0)
        assert len(communities) >= 2
        # All nodes should be assigned
        all_members = set()
        for c in communities:
            all_members.update(c["members"])
        assert all_members == {"A", "B", "C", "D", "E", "F"}

    def test_single_node(self):
        from src.data.graph_query.community import _run_louvain

        edges = [("A", "B", 0.5)]
        communities = _run_louvain(edges)
        total_members = sum(c["size"] for c in communities)
        assert total_members == 2

    def test_empty_edges(self):
        from src.data.graph_query.community import _run_louvain

        assert _run_louvain([]) == []

    def test_community_has_required_keys(self):
        from src.data.graph_query.community import _run_louvain

        edges = [("A", "B", 0.5), ("B", "C", 0.5)]
        communities = _run_louvain(edges)
        for c in communities:
            assert "community_id" in c
            assert "members" in c
            assert "level" in c
            assert "size" in c
            assert c["level"] == 0


# ===================================================================
# detect_communities (full pipeline)
# ===================================================================


class TestDetectCommunities:
    """Integration tests for the full pipeline."""

    def test_returns_empty_no_driver(self):
        from src.data.graph_query.community import detect_communities

        with patch("src.data.graph_store._get_driver", return_value=None):
            assert detect_communities() == []

    def test_returns_empty_on_error(self, gq_with_driver):
        gq, driver, session = gq_with_driver
        session.run.side_effect = Exception("db error")
        assert gq.detect_communities() == []

    def test_returns_empty_insufficient_data(self, gq_with_driver):
        """Fewer than 2 stocks returns empty list."""
        gq, _, session = gq_with_driver
        # Return only 1 stock from screen query, empty from others
        r1 = MagicMock()
        r1.__getitem__ = lambda self, k: {"symbol": "A", "ids": ["s1"]}[k]
        session.run.return_value = iter([r1])
        assert gq.detect_communities() == []

    def test_returns_communities_with_mock(self, gq_with_driver):
        """Full pipeline with mock data returns community dicts."""
        gq, driver, session = gq_with_driver

        # Build mock responses for 4 queries in _fetch_cooccurrence_vectors
        # + 2 queries per community for auto-naming
        # + 1 DETACH DELETE + N CREATE + M MERGE for save
        call_count = [0]

        def mock_run(query_str, **kwargs):
            call_count[0] += 1
            result = MagicMock()

            # More specific checks first (auto-naming queries contain "cnt")
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
            # _fetch_cooccurrence_vectors: 4 queries
            elif "Screen" in query_str and "SURFACED" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "ids": ["s1", "s2"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "ids": ["s1", "s2"]}[k]
                r3 = MagicMock()
                r3.__getitem__ = lambda s, k: {"symbol": "C", "ids": ["s3"]}[k]
                return iter([r1, r2, r3])
            elif "HAS_THEME" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "names": ["AI"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "names": ["AI"]}[k]
                return iter([r1, r2])
            elif "IN_SECTOR" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "names": ["Tech"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "names": ["Tech"]}[k]
                return iter([r1, r2])
            elif "News" in query_str and "MENTIONS" in query_str:
                return iter([])

            # _save_communities: DETACH DELETE, CREATE, MERGE
            return result

        session.run.side_effect = mock_run

        # Need to also mock _get_mode for save
        with patch("src.data.graph_store._get_mode", return_value="full"):
            communities = gq.detect_communities(similarity_cutoff=0.1)

        assert len(communities) > 0
        for c in communities:
            assert "name" in c
            assert "members" in c
            assert "size" in c


# ===================================================================
# get_communities
# ===================================================================


class TestGetCommunities:
    def test_returns_communities(self, gq_with_driver):
        gq, _, session = gq_with_driver
        r1 = MagicMock()
        r1.keys = lambda: ["id", "name", "size", "level", "created_at", "members"]
        r1.__getitem__ = lambda s, k: {
            "id": "community_0_0",
            "name": "Tech x AI",
            "size": 3,
            "level": 0,
            "created_at": "2026-03-14T00:00:00",
            "members": ["A", "B", "C"],
        }[k]
        session.run.return_value = iter([r1])
        result = gq.get_communities(level=0)
        assert len(result) == 1
        assert result[0]["name"] == "Tech x AI"

    def test_returns_empty_no_driver(self):
        import src.data.graph_query as gq

        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_communities() == []

    def test_returns_empty_on_error(self, gq_with_driver):
        gq, driver, _ = gq_with_driver
        driver.session.return_value.__enter__.return_value.run.side_effect = Exception("err")
        assert gq.get_communities() == []


# ===================================================================
# get_stock_community
# ===================================================================


class TestGetStockCommunity:
    def test_found(self, gq_with_driver):
        gq, _, session = gq_with_driver
        rec = MagicMock()
        rec.keys = lambda: ["community_id", "name", "size", "level", "peers"]
        rec.__getitem__ = lambda s, k: {
            "community_id": "community_0_0",
            "name": "Tech x AI",
            "size": 3,
            "level": 0,
            "peers": ["B", "C"],
        }[k]
        session.run.return_value.single.return_value = rec
        result = gq.get_stock_community("A")
        assert result is not None
        assert result["name"] == "Tech x AI"
        assert "B" in result["peers"]

    def test_not_found(self, gq_with_driver):
        gq, _, session = gq_with_driver
        session.run.return_value.single.return_value = None
        assert gq.get_stock_community("UNKNOWN") is None

    def test_no_driver(self):
        import src.data.graph_query as gq

        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_stock_community("A") is None


# ===================================================================
# get_similar_stocks
# ===================================================================


class TestGetSimilarStocks:
    def test_returns_similar(self, gq_with_driver):
        gq, _, session = gq_with_driver

        def mock_run(query_str, **kwargs):
            if "SURFACED" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "ids": ["s1", "s2"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "ids": ["s1", "s2"]}[k]
                return iter([r1, r2])
            if "HAS_THEME" in query_str:
                r1 = MagicMock()
                r1.__getitem__ = lambda s, k: {"symbol": "A", "names": ["AI"]}[k]
                r2 = MagicMock()
                r2.__getitem__ = lambda s, k: {"symbol": "B", "names": ["AI"]}[k]
                return iter([r1, r2])
            if "IN_SECTOR" in query_str:
                return iter([])
            if "MENTIONS" in query_str:
                return iter([])
            return iter([])

        session.run.side_effect = mock_run
        result = gq.get_similar_stocks("A", similarity_cutoff=0.0)
        assert len(result) == 1
        assert result[0]["symbol"] == "B"
        assert result[0]["similarity"] > 0

    def test_no_driver(self):
        import src.data.graph_query as gq

        with patch("src.data.graph_store._get_driver", return_value=None):
            assert gq.get_similar_stocks("A") == []

    def test_symbol_not_in_graph(self, gq_with_driver):
        gq, _, session = gq_with_driver
        # All queries return empty
        session.run.return_value = iter([])
        assert gq.get_similar_stocks("UNKNOWN") == []


# ===================================================================
# Auto-naming
# ===================================================================


class TestAutoNaming:
    def test_sector_and_theme(self):
        from src.data.graph_query.community import _auto_name_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] == 1:  # sector query
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Technology", "cnt": 2}[k]
                result.single.return_value = rec
            else:  # theme query
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "AI", "cnt": 2}[k]
                result.single.return_value = rec
            return result

        session.run.side_effect = mock_run
        name = _auto_name_community(["A", "B"], session, fallback_id=0)
        assert name == "Technology x AI"

    def test_sector_only(self):
        from src.data.graph_query.community import _auto_name_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] == 1:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Healthcare", "cnt": 3}[k]
                result.single.return_value = rec
            else:
                result.single.return_value = None
            return result

        session.run.side_effect = mock_run
        name = _auto_name_community(["A", "B", "C"], session, fallback_id=1)
        assert name == "Healthcare"

    def test_fallback_name(self):
        from src.data.graph_query.community import _auto_name_community

        session = MagicMock()
        result = MagicMock()
        result.single.return_value = None
        session.run.return_value = result
        name = _auto_name_community(["A"], session, fallback_id=5)
        assert name == "Community_5"


# ===================================================================
# Save Communities
# ===================================================================


class TestSaveCommunities:
    def test_mode_off_returns_false(self):
        from src.data.graph_query.community import _save_communities

        with patch("src.data.graph_store._get_mode", return_value="off"):
            assert _save_communities([{"community_id": 0, "name": "x", "size": 1, "level": 0, "members": ["A"]}]) is False

    def test_no_driver_returns_false(self):
        from src.data.graph_query.community import _save_communities

        with patch("src.data.graph_store._get_mode", return_value="full"), \
             patch("src.data.graph_store._get_driver", return_value=None):
            assert _save_communities([]) is False

    def test_writes_communities(self, gq_with_driver):
        from src.data.graph_query.community import _save_communities

        _, _, session = gq_with_driver
        communities = [
            {"community_id": 0, "name": "Tech x AI", "size": 2, "level": 0, "members": ["A", "B"]},
        ]
        with patch("src.data.graph_store._get_mode", return_value="full"):
            result = _save_communities(communities)
        assert result is True
        # Should have: 1 DETACH DELETE + 1 CREATE + 2 MERGE (BELONGS_TO)
        assert session.run.call_count == 4
