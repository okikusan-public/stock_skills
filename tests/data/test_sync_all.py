"""Tests for sync_all() one-shot sync function (KIK-712)."""

from unittest.mock import patch, MagicMock

import pytest


class TestSyncAll:
    """Test tools/graphrag.py sync_all()."""

    def test_neo4j_unavailable_returns_skipped(self):
        """When Neo4j is not available, sync_all returns skipped."""
        from tools.graphrag import sync_all
        with patch("src.data.graph_store._common.is_available", return_value=False):
            result = sync_all()
        assert result["skipped"]
        assert not result["synced"]

    def test_sync_all_returns_dict_structure(self):
        """sync_all always returns a dict with synced/failed/skipped keys."""
        from tools.graphrag import sync_all
        with patch("src.data.graph_store._common.is_available", return_value=False):
            result = sync_all()
        assert "synced" in result
        assert "failed" in result
        assert "skipped" in result
        assert isinstance(result["synced"], list)
        assert isinstance(result["failed"], list)
        assert isinstance(result["skipped"], list)

    def test_portfolio_sync_called(self):
        """When Neo4j available, portfolio sync is attempted."""
        from tools.graphrag import sync_all
        with patch("src.data.graph_store._common.is_available", return_value=True), \
             patch("src.data.portfolio_io.load_portfolio", return_value=[{"symbol": "MSFT"}]), \
             patch("src.data.graph_store.portfolio.sync_portfolio") as mock_sync:
            result = sync_all()
        mock_sync.assert_called_once()
        assert any("portfolio" in s for s in result["synced"])

    def test_portfolio_error_continues(self):
        """Portfolio sync failure doesn't stop note sync."""
        from tools.graphrag import sync_all
        with patch("src.data.graph_store._common.is_available", return_value=True), \
             patch("src.data.portfolio_io.load_portfolio", side_effect=Exception("CSV broken")):
            result = sync_all()
        assert any("portfolio" in s for s in result["failed"])

    def test_notes_sync_calls_merge_note(self, tmp_path):
        """Notes JSON files are synced via merge_note."""
        import json
        from tools.graphrag import sync_all

        notes_dir = tmp_path / "data" / "notes"
        notes_dir.mkdir(parents=True)
        note = {"id": "n1", "date": "2026-04-24", "type": "thesis",
                "content": "Test", "symbol": "MSFT"}
        (notes_dir / "n1.json").write_text(json.dumps(note))

        import tools.graphrag as tg
        orig_root = tg._project_root
        try:
            tg._project_root = str(tmp_path)
            with patch("src.data.graph_store._common.is_available", return_value=True), \
                 patch("src.data.portfolio_io.load_portfolio", return_value=[]), \
                 patch("src.data.graph_store.note.merge_note") as mock_merge:
                result = sync_all()
            mock_merge.assert_called_once()
            assert any("notes" in s for s in result["synced"])
        finally:
            tg._project_root = orig_root

    def test_sync_status_yaml_written(self, tmp_path):
        """sync_status.yaml is written after sync."""
        import tools.graphrag as tg
        orig_root = tg._project_root
        try:
            tg._project_root = str(tmp_path)
            (tmp_path / "data").mkdir(parents=True, exist_ok=True)
            with patch("src.data.graph_store._common.is_available", return_value=True), \
                 patch("src.data.portfolio_io.load_portfolio", return_value=[]):
                from tools.graphrag import sync_all
                sync_all()
            status_path = tmp_path / "data" / "sync_status.yaml"
            assert status_path.exists()
        finally:
            tg._project_root = orig_root
