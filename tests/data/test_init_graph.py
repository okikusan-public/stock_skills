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
    import_research,
    import_notes,
    import_portfolio,
    import_watchlists,
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


# ===================================================================
# import_research tests
# ===================================================================

class TestImportResearch:
    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_stock(self, mock_stock, mock_research, mock_link, tmp_path):
        d = tmp_path / "research"
        _write_json(d / "2025-01-15_stock_7203_T.json", {
            "date": "2025-01-15",
            "research_type": "stock",
            "target": "7203.T",
            "name": "Toyota",
            "summary": "Strong fundamentals",
        })
        count = import_research(str(tmp_path))
        assert count == 1
        mock_stock.assert_called_once_with(symbol="7203.T", name="Toyota")
        mock_research.assert_called_once_with(
            research_date="2025-01-15",
            research_type="stock",
            target="7203.T",
            summary="Strong fundamentals",
        )
        mock_link.assert_called_once_with("stock", "7203.T")

    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_industry(self, mock_stock, mock_research, mock_link, tmp_path):
        d = tmp_path / "research"
        _write_json(d / "2025-01-15_industry_semiconductor.json", {
            "date": "2025-01-15",
            "research_type": "industry",
            "target": "半導体",
            "summary": "Growing demand",
        })
        count = import_research(str(tmp_path))
        assert count == 1
        mock_stock.assert_not_called()  # industry type: no Stock merge
        mock_research.assert_called_once()
        mock_link.assert_called_once_with("industry", "半導体")

    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_market(self, mock_stock, mock_research, mock_link, tmp_path):
        d = tmp_path / "research"
        _write_json(d / "2025-01-15_market_nikkei.json", {
            "date": "2025-01-15",
            "research_type": "market",
            "target": "日経平均",
            "summary": "Bullish trend",
        })
        count = import_research(str(tmp_path))
        assert count == 1
        mock_stock.assert_not_called()  # market type: no Stock merge

    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_business(self, mock_stock, mock_research, mock_link, tmp_path):
        d = tmp_path / "research"
        _write_json(d / "2025-01-15_business_7751_T.json", {
            "date": "2025-01-15",
            "research_type": "business",
            "target": "7751.T",
            "summary": "Diversified revenue",
        })
        count = import_research(str(tmp_path))
        assert count == 1
        mock_stock.assert_called_once_with(symbol="7751.T", name="")
        mock_research.assert_called_once()

    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_no_target_skipped(self, mock_stock, mock_research, mock_link, tmp_path):
        d = tmp_path / "research"
        _write_json(d / "2025-01-15_bad.json", {
            "date": "2025-01-15",
            "research_type": "stock",
        })
        count = import_research(str(tmp_path))
        assert count == 0
        mock_research.assert_not_called()

    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_supersedes_chains(self, mock_stock, mock_research, mock_link, tmp_path):
        """Multiple research files for same target should create one SUPERSEDES chain."""
        d = tmp_path / "research"
        _write_json(d / "2025-01-15_stock_7203_T.json", {
            "date": "2025-01-15",
            "research_type": "stock",
            "target": "7203.T",
            "summary": "First",
        })
        _write_json(d / "2025-02-15_stock_7203_T.json", {
            "date": "2025-02-15",
            "research_type": "stock",
            "target": "7203.T",
            "summary": "Second",
        })
        count = import_research(str(tmp_path))
        assert count == 2
        assert mock_research.call_count == 2
        # link_research_supersedes called once for (stock, 7203.T)
        mock_link.assert_called_once_with("stock", "7203.T")

    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_empty_dir(self, mock_stock, mock_research, mock_link, tmp_path):
        count = import_research(str(tmp_path))
        assert count == 0

    @patch("scripts.init_graph.link_research_supersedes")
    @patch("scripts.init_graph.merge_research")
    @patch("scripts.init_graph.merge_stock")
    def test_import_research_corrupted_file(self, mock_stock, mock_research, mock_link, tmp_path):
        d = tmp_path / "research"
        d.mkdir(parents=True)
        (d / "bad.json").write_text("not json")
        count = import_research(str(tmp_path))
        assert count == 0


# ===================================================================
# import_portfolio tests
# ===================================================================

def _write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    import csv as _csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


class TestImportPortfolio:
    @patch("scripts.init_graph.merge_stock")
    def test_import_portfolio_basic(self, mock_stock, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        _write_csv(csv_path, [
            {"symbol": "7203.T", "shares": "100", "price": "2850", "memo": "Toyota"},
            {"symbol": "AAPL", "shares": "10", "price": "178", "memo": "Apple"},
        ])
        count = import_portfolio(str(csv_path))
        assert count == 2
        assert mock_stock.call_count == 2
        mock_stock.assert_any_call(symbol="7203.T", name="Toyota")
        mock_stock.assert_any_call(symbol="AAPL", name="Apple")

    @patch("scripts.init_graph.merge_stock")
    def test_import_portfolio_skip_cash(self, mock_stock, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        _write_csv(csv_path, [
            {"symbol": "7203.T", "shares": "100", "price": "2850", "memo": "Toyota"},
            {"symbol": "JPY.CASH", "shares": "1", "price": "500000", "memo": "Cash"},
        ])
        count = import_portfolio(str(csv_path))
        assert count == 1
        mock_stock.assert_called_once_with(symbol="7203.T", name="Toyota")

    @patch("scripts.init_graph.merge_stock")
    def test_import_portfolio_nonexistent(self, mock_stock, tmp_path):
        count = import_portfolio(str(tmp_path / "missing.csv"))
        assert count == 0
        mock_stock.assert_not_called()

    @patch("scripts.init_graph.merge_stock")
    def test_import_portfolio_empty_symbol(self, mock_stock, tmp_path):
        csv_path = tmp_path / "portfolio.csv"
        _write_csv(csv_path, [
            {"symbol": "", "shares": "100", "price": "0", "memo": "Empty"},
        ])
        count = import_portfolio(str(csv_path))
        assert count == 0


# ===================================================================
# import_watchlists tests
# ===================================================================

class TestImportWatchlists:
    @patch("scripts.init_graph.merge_watchlist")
    @patch("scripts.init_graph.merge_stock")
    def test_import_watchlists_basic(self, mock_stock, mock_wl, tmp_path):
        _write_json(tmp_path / "favorites.json", ["7203.T", "AAPL", "D05.SI"])
        count = import_watchlists(str(tmp_path))
        assert count == 1
        assert mock_stock.call_count == 3
        mock_wl.assert_called_once_with("favorites", ["7203.T", "AAPL", "D05.SI"])

    @patch("scripts.init_graph.merge_watchlist")
    @patch("scripts.init_graph.merge_stock")
    def test_import_watchlists_multiple_files(self, mock_stock, mock_wl, tmp_path):
        _write_json(tmp_path / "japan.json", ["7203.T", "9984.T"])
        _write_json(tmp_path / "us.json", ["AAPL", "MSFT"])
        count = import_watchlists(str(tmp_path))
        assert count == 2
        assert mock_wl.call_count == 2

    @patch("scripts.init_graph.merge_watchlist")
    @patch("scripts.init_graph.merge_stock")
    def test_import_watchlists_empty_list(self, mock_stock, mock_wl, tmp_path):
        _write_json(tmp_path / "empty.json", [])
        count = import_watchlists(str(tmp_path))
        assert count == 0
        mock_wl.assert_not_called()

    @patch("scripts.init_graph.merge_watchlist")
    @patch("scripts.init_graph.merge_stock")
    def test_import_watchlists_not_a_list(self, mock_stock, mock_wl, tmp_path):
        _write_json(tmp_path / "bad.json", {"key": "value"})
        count = import_watchlists(str(tmp_path))
        assert count == 0

    @patch("scripts.init_graph.merge_watchlist")
    @patch("scripts.init_graph.merge_stock")
    def test_import_watchlists_nonexistent_dir(self, mock_stock, mock_wl, tmp_path):
        count = import_watchlists(str(tmp_path / "missing"))
        assert count == 0

    @patch("scripts.init_graph.merge_watchlist")
    @patch("scripts.init_graph.merge_stock")
    def test_import_watchlists_corrupted_file(self, mock_stock, mock_wl, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "bad.json").write_text("not json")
        count = import_watchlists(str(tmp_path))
        assert count == 0
