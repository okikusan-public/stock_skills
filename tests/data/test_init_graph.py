"""Tests for scripts/init_graph.py import functions (KIK-397).

Uses tmp_path for test history/notes data, graph_store functions are mocked.
"""

import json
from pathlib import Path
from unittest.mock import patch, call

import pytest

from scripts.init_graph import (
    import_screens,
    import_reports,
    import_trades,
    import_health,
    import_notes,
)


# ===================================================================
# Helpers
# ===================================================================

def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===================================================================
# import_screens tests
# ===================================================================

class TestImportScreens:
    @patch("scripts.init_graph.merge_screen")
    @patch("scripts.init_graph.merge_stock")
    def test_import_screens_basic(self, mock_stock, mock_screen, tmp_path):
        d = tmp_path / "screen"
        _write_json(d / "2025-01-15_japan_value.json", {
            "date": "2025-01-15",
            "preset": "value",
            "region": "japan",
            "results": [
                {"symbol": "7203.T", "name": "Toyota", "sector": "Automotive"},
                {"symbol": "9984.T", "name": "SoftBank", "sector": "Tech"},
            ],
        })
        count = import_screens(str(tmp_path))
        assert count == 1
        assert mock_stock.call_count == 2
        mock_screen.assert_called_once()

    @patch("scripts.init_graph.merge_screen")
    @patch("scripts.init_graph.merge_stock")
    def test_import_screens_empty_dir(self, mock_stock, mock_screen, tmp_path):
        count = import_screens(str(tmp_path))
        assert count == 0

    @patch("scripts.init_graph.merge_screen")
    @patch("scripts.init_graph.merge_stock")
    def test_import_screens_corrupted_file(self, mock_stock, mock_screen, tmp_path):
        d = tmp_path / "screen"
        d.mkdir(parents=True)
        (d / "bad.json").write_text("not json")
        count = import_screens(str(tmp_path))
        assert count == 0


# ===================================================================
# import_reports tests
# ===================================================================

class TestImportReports:
    @patch("scripts.init_graph.merge_report")
    @patch("scripts.init_graph.merge_stock")
    def test_import_reports_basic(self, mock_stock, mock_report, tmp_path):
        d = tmp_path / "report"
        _write_json(d / "2025-01-15_7203_T.json", {
            "date": "2025-01-15",
            "symbol": "7203.T",
            "name": "Toyota",
            "sector": "Automotive",
            "value_score": 72.5,
            "verdict": "割安",
        })
        count = import_reports(str(tmp_path))
        assert count == 1
        mock_stock.assert_called_once_with(symbol="7203.T", name="Toyota", sector="Automotive")
        mock_report.assert_called_once()

    @patch("scripts.init_graph.merge_report")
    @patch("scripts.init_graph.merge_stock")
    def test_import_reports_no_symbol(self, mock_stock, mock_report, tmp_path):
        d = tmp_path / "report"
        _write_json(d / "2025-01-15_empty.json", {"date": "2025-01-15"})
        count = import_reports(str(tmp_path))
        assert count == 0


# ===================================================================
# import_trades tests
# ===================================================================

class TestImportTrades:
    @patch("scripts.init_graph.merge_trade")
    @patch("scripts.init_graph.merge_stock")
    def test_import_trades_basic(self, mock_stock, mock_trade, tmp_path):
        d = tmp_path / "trade"
        _write_json(d / "2025-01-15_buy_7203_T.json", {
            "date": "2025-01-15",
            "symbol": "7203.T",
            "trade_type": "buy",
            "shares": 100,
            "price": 2850,
            "currency": "JPY",
            "memo": "test buy",
        })
        count = import_trades(str(tmp_path))
        assert count == 1
        mock_stock.assert_called_once_with(symbol="7203.T")
        mock_trade.assert_called_once_with(
            trade_date="2025-01-15",
            trade_type="buy",
            symbol="7203.T",
            shares=100,
            price=2850,
            currency="JPY",
            memo="test buy",
        )

    @patch("scripts.init_graph.merge_trade")
    @patch("scripts.init_graph.merge_stock")
    def test_import_trades_no_symbol(self, mock_stock, mock_trade, tmp_path):
        d = tmp_path / "trade"
        _write_json(d / "2025-01-15_buy_empty.json", {"date": "2025-01-15"})
        count = import_trades(str(tmp_path))
        assert count == 0


# ===================================================================
# import_health tests
# ===================================================================

class TestImportHealth:
    @patch("scripts.init_graph.merge_health")
    def test_import_health_basic(self, mock_health, tmp_path):
        d = tmp_path / "health"
        _write_json(d / "2025-01-15_health.json", {
            "date": "2025-01-15",
            "summary": {"total": 5, "healthy": 3, "exit": 1},
            "positions": [
                {"symbol": "7203.T"},
                {"symbol": "AAPL"},
            ],
        })
        count = import_health(str(tmp_path))
        assert count == 1
        mock_health.assert_called_once_with(
            "2025-01-15",
            {"total": 5, "healthy": 3, "exit": 1},
            ["7203.T", "AAPL"],
        )

    @patch("scripts.init_graph.merge_health")
    def test_import_health_empty_positions(self, mock_health, tmp_path):
        d = tmp_path / "health"
        _write_json(d / "2025-01-15_health.json", {
            "date": "2025-01-15",
            "summary": {},
            "positions": [],
        })
        count = import_health(str(tmp_path))
        assert count == 1


# ===================================================================
# import_notes tests
# ===================================================================

class TestImportNotes:
    @patch("scripts.init_graph.merge_note")
    def test_import_notes_list_format(self, mock_note, tmp_path):
        _write_json(tmp_path / "2025-01-15_7203_T_thesis.json", [
            {
                "id": "note_2025-01-15_7203.T_abc1",
                "date": "2025-01-15",
                "type": "thesis",
                "content": "Strong buy",
                "symbol": "7203.T",
                "source": "manual",
            },
            {
                "id": "note_2025-01-15_7203.T_abc2",
                "date": "2025-01-15",
                "type": "thesis",
                "content": "Updated thesis",
                "symbol": "7203.T",
                "source": "manual",
            },
        ])
        count = import_notes(str(tmp_path))
        assert count == 2
        assert mock_note.call_count == 2

    @patch("scripts.init_graph.merge_note")
    def test_import_notes_single_object(self, mock_note, tmp_path):
        _write_json(tmp_path / "2025-01-15_note.json", {
            "id": "note_2025-01-15_general_abc1",
            "date": "2025-01-15",
            "type": "observation",
            "content": "Market volatile",
            "source": "manual",
        })
        count = import_notes(str(tmp_path))
        assert count == 1

    @patch("scripts.init_graph.merge_note")
    def test_import_notes_no_id_skipped(self, mock_note, tmp_path):
        _write_json(tmp_path / "bad_note.json", [
            {"date": "2025-01-15", "content": "No ID"},
        ])
        count = import_notes(str(tmp_path))
        assert count == 0

    @patch("scripts.init_graph.merge_note")
    def test_import_notes_empty_dir(self, mock_note, tmp_path):
        count = import_notes(str(tmp_path))
        assert count == 0

    @patch("scripts.init_graph.merge_note")
    def test_import_notes_nonexistent_dir(self, mock_note, tmp_path):
        count = import_notes(str(tmp_path / "nonexistent"))
        assert count == 0
