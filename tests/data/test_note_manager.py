"""Tests for src.data.note_manager module (KIK-397).

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
        assert _VALID_TYPES == {"thesis", "observation", "concern", "review", "target"}

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
