"""Tests for src.data.note_manager module (KIK-397, KIK-429).

Uses tmp_path for JSON file operations, Neo4j is mocked.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data.note_manager import (
    save_note,
    load_notes,
    delete_note,
    _VALID_TYPES,
    _VALID_CATEGORIES,
)


# ===================================================================
# save_note tests
# ===================================================================

class TestSaveNote:
    def test_save_note_creates_file(self, tmp_path):
        with patch("src.data.graph_store.merge_note"):
            note = save_note("7203.T", "thesis", "Strong buy candidate", base_dir=str(tmp_path))

        assert note["symbol"] == "7203.T"
        assert note["type"] == "thesis"
        assert note["content"] == "Strong buy candidate"
        assert note["id"].startswith("note_")
        assert "7203.T" in note["id"]

        # Verify JSON file was created
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        with open(files[0], encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["content"] == "Strong buy candidate"

    def test_save_note_appends_same_date_symbol_type(self, tmp_path):
        with patch("src.data.graph_store.merge_note"):
            save_note("7203.T", "thesis", "First note", base_dir=str(tmp_path))
            save_note("7203.T", "thesis", "Second note", base_dir=str(tmp_path))

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1  # Same file, appended
        with open(files[0], encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[0]["content"] == "First note"
        assert data[1]["content"] == "Second note"

    def test_save_note_different_types_separate_files(self, tmp_path):
        with patch("src.data.graph_store.merge_note"):
            save_note("7203.T", "thesis", "Thesis", base_dir=str(tmp_path))
            save_note("7203.T", "concern", "Concern", base_dir=str(tmp_path))

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 2

    def test_save_note_invalid_type(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid note type"):
            save_note("7203.T", "invalid_type", "content", base_dir=str(tmp_path))

    def test_save_note_valid_types(self):
        assert _VALID_TYPES == {"thesis", "observation", "concern", "review", "target", "lesson", "journal"}

    def test_save_note_lesson_type(self, tmp_path):
        """lesson タイプのノートが保存できること (KIK-408)."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note("7203.T", "lesson", "Never chase momentum blindly", base_dir=str(tmp_path))
        assert note["type"] == "lesson"
        assert note["content"] == "Never chase momentum blindly"

    def test_save_note_source_field(self, tmp_path):
        with patch("src.data.graph_store.merge_note"):
            note = save_note("7203.T", "observation", "Note", source="health-check", base_dir=str(tmp_path))
        assert note["source"] == "health-check"

    def test_save_note_neo4j_failure_still_saves_json(self, tmp_path):
        """Neo4j failure should not prevent JSON write."""
        with patch("src.data.graph_store.merge_note", side_effect=Exception("Neo4j down")):
            note = save_note("7203.T", "thesis", "content", base_dir=str(tmp_path))

        assert note["content"] == "content"
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_save_note_creates_directory(self, tmp_path):
        nested = tmp_path / "sub" / "notes"
        with patch("src.data.graph_store.merge_note"):
            save_note("AAPL", "thesis", "test", base_dir=str(nested))
        assert nested.exists()

    def test_save_note_dot_in_symbol(self, tmp_path):
        """Dots in symbol should be replaced with underscore in filename."""
        with patch("src.data.graph_store.merge_note"):
            save_note("D05.SI", "thesis", "test", base_dir=str(tmp_path))
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "D05_SI" in files[0].name

    # KIK-429: category support
    def test_save_note_without_symbol(self, tmp_path):
        """symbol なしでカテゴリ指定で保存できること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(note_type="review", content="PF analysis", category="portfolio", base_dir=str(tmp_path))
        assert note["symbol"] == ""
        assert note["category"] == "portfolio"
        assert "portfolio" in note["id"]
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "portfolio" in files[0].name

    def test_save_note_with_symbol_category_is_stock(self, tmp_path):
        """symbol 指定時は category が自動で stock になること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note("7203.T", "thesis", "test", base_dir=str(tmp_path))
        assert note["category"] == "stock"

    def test_save_note_category_defaults_to_general(self, tmp_path):
        """symbol も category も未指定なら general になること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(note_type="observation", content="test", base_dir=str(tmp_path))
        assert note["category"] == "general"

    def test_save_note_market_category(self, tmp_path):
        """market カテゴリで保存できること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(note_type="observation", content="Market memo", category="market", base_dir=str(tmp_path))
        assert note["category"] == "market"
        assert note["symbol"] == ""
        assert "market" in note["id"]

    def test_save_note_invalid_category(self, tmp_path):
        """無効なカテゴリでエラーになること."""
        with pytest.raises(ValueError, match="Invalid category"):
            save_note(note_type="observation", content="test", category="invalid", base_dir=str(tmp_path))

    def test_valid_categories(self):
        assert _VALID_CATEGORIES == {"stock", "portfolio", "market", "general"}

    def test_save_note_symbol_with_invalid_category_ignored(self, tmp_path):
        """symbol 指定時は無効 category が無視されて stock になること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note("7203.T", "thesis", "test", category="invalid", base_dir=str(tmp_path))
        assert note["category"] == "stock"


# ===================================================================
# KIK-473: journal note type tests
# ===================================================================

class TestSaveNoteJournal:
    def test_journal_type_in_valid_types(self):
        """journal が _VALID_TYPES に含まれること."""
        assert "journal" in _VALID_TYPES

    def test_journal_without_symbol_or_category(self, tmp_path):
        """journal タイプは symbol/category なしで保存できること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(note_type="journal", content="Today was quiet", base_dir=str(tmp_path))
        assert note["type"] == "journal"
        assert note["category"] == "general"
        assert note["symbol"] == ""

    def test_journal_auto_detects_symbols(self, tmp_path):
        """journal の content からティッカーシンボルを自動検出すること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(
                note_type="journal",
                content="NVDAが急騰。7203.Tは下落した",
                base_dir=str(tmp_path),
            )
        detected = note.get("detected_symbols", [])
        assert set(detected) == {"NVDA", "7203.T"}

    def test_journal_no_symbols_detected(self, tmp_path):
        """シンボルなしの journal では detected_symbols がないこと."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(
                note_type="journal",
                content="今日はトレードしない",
                base_dir=str(tmp_path),
            )
        assert "detected_symbols" not in note

    def test_journal_with_explicit_symbol(self, tmp_path):
        """journal でも symbol 指定時は category が stock になること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(
                symbol="AAPL",
                note_type="journal",
                content="AAPL earnings coming up",
                base_dir=str(tmp_path),
            )
        assert note["category"] == "stock"
        assert note["symbol"] == "AAPL"
        # With explicit symbol, no auto-detection
        assert "detected_symbols" not in note

    def test_journal_with_category(self, tmp_path):
        """journal でも category 指定を尊重すること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(
                note_type="journal",
                content="Market reflections",
                category="market",
                base_dir=str(tmp_path),
            )
        assert note["category"] == "market"

    def test_journal_detected_symbols_max_3(self, tmp_path):
        """detected_symbols は最大3件に制限されること."""
        with patch("src.data.graph_store.merge_note"):
            note = save_note(
                note_type="journal",
                content="NVDA AAPL MSFT GOOGL TSLA all up today",
                base_dir=str(tmp_path),
            )
        detected = note.get("detected_symbols", [])
        assert len(detected) <= 3


# ===================================================================
# load_notes tests
# ===================================================================

class TestLoadNotes:
    def _save_notes(self, tmp_path):
        """Save test notes and return them."""
        with patch("src.data.graph_store.merge_note"):
            n1 = save_note("7203.T", "thesis", "Toyota thesis", base_dir=str(tmp_path))
            n2 = save_note("AAPL", "concern", "Apple concern", base_dir=str(tmp_path))
            n3 = save_note("7203.T", "concern", "Toyota concern", base_dir=str(tmp_path))
        return n1, n2, n3

    def test_load_all_notes(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 3

    def test_load_notes_filter_by_symbol(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(symbol="7203.T", base_dir=str(tmp_path))
        assert len(notes) == 2
        assert all(n["symbol"] == "7203.T" for n in notes)

    def test_load_notes_filter_by_type(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(note_type="concern", base_dir=str(tmp_path))
        assert len(notes) == 2
        assert all(n["type"] == "concern" for n in notes)

    def test_load_notes_filter_both(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(symbol="7203.T", note_type="thesis", base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "Toyota thesis"

    def test_load_notes_empty_dir(self, tmp_path):
        notes = load_notes(base_dir=str(tmp_path))
        assert notes == []

    def test_load_notes_nonexistent_dir(self, tmp_path):
        notes = load_notes(base_dir=str(tmp_path / "nonexistent"))
        assert notes == []

    def test_load_notes_sorted_by_date_desc(self, tmp_path):
        self._save_notes(tmp_path)
        notes = load_notes(base_dir=str(tmp_path))
        dates = [n["date"] for n in notes]
        assert dates == sorted(dates, reverse=True)

    def test_load_notes_corrupted_file(self, tmp_path):
        """Corrupted JSON files should be skipped."""
        (tmp_path / "bad.json").write_text("not valid json")
        with patch("src.data.graph_store.merge_note"):
            save_note("7203.T", "thesis", "Good note", base_dir=str(tmp_path))
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "Good note"

    # KIK-429: category filter
    def test_load_notes_filter_by_category(self, tmp_path):
        """category フィルタで絞り込みできること."""
        with patch("src.data.graph_store.merge_note"):
            save_note("7203.T", "thesis", "Stock note", base_dir=str(tmp_path))
            save_note(note_type="review", content="PF note", category="portfolio", base_dir=str(tmp_path))
            save_note(note_type="observation", content="Market note", category="market", base_dir=str(tmp_path))

        stock_notes = load_notes(category="stock", base_dir=str(tmp_path))
        assert len(stock_notes) == 1
        assert stock_notes[0]["symbol"] == "7203.T"

        pf_notes = load_notes(category="portfolio", base_dir=str(tmp_path))
        assert len(pf_notes) == 1
        assert pf_notes[0]["content"] == "PF note"

        market_notes = load_notes(category="market", base_dir=str(tmp_path))
        assert len(market_notes) == 1
        assert market_notes[0]["content"] == "Market note"

    def test_load_notes_all_includes_categorized(self, tmp_path):
        """全件取得でカテゴリ付きメモも含まれること."""
        with patch("src.data.graph_store.merge_note"):
            save_note("AAPL", "thesis", "Stock", base_dir=str(tmp_path))
            save_note(note_type="review", content="PF", category="portfolio", base_dir=str(tmp_path))
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 2

    def test_load_notes_category_and_type_combined(self, tmp_path):
        """category + type の複合フィルタが正しく動くこと."""
        with patch("src.data.graph_store.merge_note"):
            save_note(note_type="review", content="PF review", category="portfolio", base_dir=str(tmp_path))
            save_note(note_type="observation", content="PF obs", category="portfolio", base_dir=str(tmp_path))
            save_note(note_type="review", content="Market review", category="market", base_dir=str(tmp_path))
        notes = load_notes(category="portfolio", note_type="review", base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "PF review"


# ===================================================================
# delete_note tests
# ===================================================================

class TestDeleteNote:
    def test_delete_note_found(self, tmp_path):
        with patch("src.data.graph_store.merge_note"):
            note = save_note("7203.T", "thesis", "To delete", base_dir=str(tmp_path))
        assert delete_note(note["id"], base_dir=str(tmp_path)) is True
        # File should be removed (was the only note)
        assert list(tmp_path.glob("*.json")) == []

    def test_delete_note_keeps_others(self, tmp_path):
        with patch("src.data.graph_store.merge_note"):
            n1 = save_note("7203.T", "thesis", "Keep me", base_dir=str(tmp_path))
            n2 = save_note("7203.T", "thesis", "Delete me", base_dir=str(tmp_path))
        assert delete_note(n2["id"], base_dir=str(tmp_path)) is True
        notes = load_notes(base_dir=str(tmp_path))
        assert len(notes) == 1
        assert notes[0]["content"] == "Keep me"

    def test_delete_note_not_found(self, tmp_path):
        with patch("src.data.graph_store.merge_note"):
            save_note("7203.T", "thesis", "Note", base_dir=str(tmp_path))
        assert delete_note("nonexistent_id", base_dir=str(tmp_path)) is False

    def test_delete_note_empty_dir(self, tmp_path):
        assert delete_note("any_id", base_dir=str(tmp_path)) is False

    def test_delete_note_nonexistent_dir(self, tmp_path):
        assert delete_note("any_id", base_dir=str(tmp_path / "nonexistent")) is False
