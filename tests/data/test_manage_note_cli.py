"""Tests for the investment-note CLI (manage_note.py) (KIK-408).

Uses subprocess for arg validation tests + direct import for function tests.
"""

import importlib.util
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = str(
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "investment-note"
    / "scripts"
    / "manage_note.py"
)


def _load_module():
    """Load manage_note.py as a module."""
    spec = importlib.util.spec_from_file_location("manage_note", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """Run the CLI script and return the result."""
    import os
    return subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )


# ===================================================================
# Argument validation tests (subprocess)
# ===================================================================

class TestManageNoteCLIArgs:
    def test_save_requires_symbol(self):
        result = _run(["save", "--content", "test"])
        assert result.returncode != 0

    def test_save_requires_content(self):
        result = _run(["save", "--symbol", "7203.T"])
        assert result.returncode != 0

    def test_no_command_shows_error(self):
        result = _run([])
        assert result.returncode != 0

    def test_delete_requires_id(self):
        result = _run(["delete"])
        assert result.returncode != 0

    def test_list_runs_without_error(self):
        """list コマンドがエラーなく実行できること."""
        result = _run(["list"])
        assert result.returncode == 0


# ===================================================================
# Function tests (direct import with mocks)
# ===================================================================

class TestManageNoteFunctions:
    def test_cmd_save(self, capsys):
        """cmd_save が save_note を呼び出すこと."""
        mod = _load_module()

        mock_return = {
            "id": "note_7203_T_thesis_20260217_001",
            "symbol": "7203.T",
            "type": "thesis",
            "content": "EV growth",
            "date": "2026-02-17",
            "source": "manual",
        }
        with patch.object(mod, "save_note", return_value=mock_return) as mock_save:
            args = types.SimpleNamespace(
                symbol="7203.T", type="thesis", content="EV growth", source="manual"
            )
            mod.cmd_save(args)

        mock_save.assert_called_once_with(
            symbol="7203.T", note_type="thesis", content="EV growth", source="manual"
        )
        captured = capsys.readouterr()
        assert "保存しました" in captured.out

    def test_cmd_list_empty(self, capsys):
        """cmd_list がメモなしの場合に適切なメッセージを表示すること."""
        mod = _load_module()

        with patch.object(mod, "load_notes", return_value=[]):
            args = types.SimpleNamespace(symbol=None, type=None)
            mod.cmd_list(args)

        captured = capsys.readouterr()
        assert "メモはありません" in captured.out

    def test_cmd_list_with_notes(self, capsys):
        """cmd_list がメモ一覧をMarkdownテーブルで表示すること."""
        mod = _load_module()

        mock_notes = [
            {"date": "2026-02-17", "symbol": "7203.T", "type": "thesis", "content": "EV growth potential"},
            {"date": "2026-02-16", "symbol": "AAPL", "type": "concern", "content": "Valuation stretched"},
        ]
        with patch.object(mod, "load_notes", return_value=mock_notes):
            args = types.SimpleNamespace(symbol=None, type=None)
            mod.cmd_list(args)

        captured = capsys.readouterr()
        assert "投資メモ一覧" in captured.out
        assert "2 件" in captured.out
        assert "7203.T" in captured.out
        assert "AAPL" in captured.out

    def test_cmd_delete_success(self, capsys):
        """cmd_delete がメモ削除成功時にメッセージを表示すること."""
        mod = _load_module()

        with patch.object(mod, "delete_note", return_value=True):
            args = types.SimpleNamespace(id="note_7203_T_thesis_20260217_001")
            mod.cmd_delete(args)

        captured = capsys.readouterr()
        assert "削除しました" in captured.out

    def test_cmd_delete_not_found(self, capsys):
        """cmd_delete がメモ未発見時にメッセージを表示すること."""
        mod = _load_module()

        with patch.object(mod, "delete_note", return_value=False):
            args = types.SimpleNamespace(id="nonexistent")
            mod.cmd_delete(args)

        captured = capsys.readouterr()
        assert "見つかりません" in captured.out

    def test_cmd_list_with_symbol_filter(self, capsys):
        """cmd_list が銘柄フィルタ付きで正しくラベル表示すること."""
        mod = _load_module()

        mock_notes = [
            {"date": "2026-02-17", "symbol": "7203.T", "type": "thesis", "content": "EV growth"},
        ]
        with patch.object(mod, "load_notes", return_value=mock_notes):
            args = types.SimpleNamespace(symbol="7203.T", type=None)
            mod.cmd_list(args)

        captured = capsys.readouterr()
        assert "7203.T" in captured.out
        assert "1 件" in captured.out

    def test_cmd_list_long_content_truncated(self, capsys):
        """cmd_list が長いコンテンツを50文字で切り詰めること."""
        mod = _load_module()

        mock_notes = [
            {"date": "2026-02-17", "symbol": "7203.T", "type": "thesis",
             "content": "A" * 80},
        ]
        with patch.object(mod, "load_notes", return_value=mock_notes):
            args = types.SimpleNamespace(symbol=None, type=None)
            mod.cmd_list(args)

        captured = capsys.readouterr()
        assert "..." in captured.out
