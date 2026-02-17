"""Tests for the pre-commit hook logic (KIK-407).

Creates a temporary git repo and tests the hook script behavior.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = str(
    Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "pre-commit"
)


def _init_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with the hook installed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), capture_output=True,
    )

    # Install the hook
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_dest = hooks_dir / "pre-commit"

    import shutil
    shutil.copy2(HOOK_SCRIPT, str(hook_dest))
    hook_dest.chmod(0o755)

    # Create initial commit so we have HEAD
    readme = repo / "README.md"
    readme.write_text("init")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo), capture_output=True,
    )

    return repo


class TestPreCommitHook:
    def test_src_change_without_doc_blocks_commit(self, tmp_path):
        """src/ 変更のみの場合、コミットがブロックされること."""
        repo = _init_repo(tmp_path)

        # Create src/core/foo.py
        (repo / "src" / "core").mkdir(parents=True)
        (repo / "src" / "core" / "foo.py").write_text("x = 1")
        subprocess.run(["git", "add", "src/core/foo.py"], cwd=str(repo), capture_output=True)

        result = subprocess.run(
            ["git", "commit", "-m", "test"],
            cwd=str(repo), capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "ドキュメントが更新されていません" in result.stderr or "ドキュメントが更新されていません" in result.stdout

    def test_src_change_with_doc_allows_commit(self, tmp_path):
        """src/ 変更 + ドキュメント更新の場合、コミットが成功すること."""
        repo = _init_repo(tmp_path)

        (repo / "src" / "data").mkdir(parents=True)
        (repo / "src" / "data" / "bar.py").write_text("y = 2")
        (repo / "CLAUDE.md").write_text("updated")
        subprocess.run(["git", "add", "src/data/bar.py", "CLAUDE.md"], cwd=str(repo), capture_output=True)

        result = subprocess.run(
            ["git", "commit", "-m", "test with docs"],
            cwd=str(repo), capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_doc_only_change_allows_commit(self, tmp_path):
        """ドキュメントのみの変更は問題なくコミットできること."""
        repo = _init_repo(tmp_path)

        (repo / "CLAUDE.md").write_text("doc update")
        subprocess.run(["git", "add", "CLAUDE.md"], cwd=str(repo), capture_output=True)

        result = subprocess.run(
            ["git", "commit", "-m", "doc only"],
            cwd=str(repo), capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_non_src_python_allows_commit(self, tmp_path):
        """src/ 外の Python ファイル変更はブロックされないこと."""
        repo = _init_repo(tmp_path)

        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts" / "run.py").write_text("print('hi')")
        subprocess.run(["git", "add", "scripts/run.py"], cwd=str(repo), capture_output=True)

        result = subprocess.run(
            ["git", "commit", "-m", "scripts only"],
            cwd=str(repo), capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_no_verify_bypasses_hook(self, tmp_path):
        """--no-verify でフックをバイパスできること."""
        repo = _init_repo(tmp_path)

        (repo / "src" / "core").mkdir(parents=True)
        (repo / "src" / "core" / "baz.py").write_text("z = 3")
        subprocess.run(["git", "add", "src/core/baz.py"], cwd=str(repo), capture_output=True)

        result = subprocess.run(
            ["git", "commit", "--no-verify", "-m", "bypass"],
            cwd=str(repo), capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_rules_dir_counts_as_doc(self, tmp_path):
        """rules/ ディレクトリの変更がドキュメント更新としてカウントされること."""
        repo = _init_repo(tmp_path)

        (repo / "src" / "core").mkdir(parents=True)
        (repo / "src" / "core" / "mod.py").write_text("a = 1")
        (repo / "rules").mkdir(parents=True)
        (repo / "rules" / "new.md").write_text("rule")
        subprocess.run(
            ["git", "add", "src/core/mod.py", "rules/new.md"],
            cwd=str(repo), capture_output=True,
        )

        result = subprocess.run(
            ["git", "commit", "-m", "src + rules"],
            cwd=str(repo), capture_output=True, text=True,
        )
        assert result.returncode == 0
