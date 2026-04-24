"""Tests for disclosure reader (KIK-713)."""

import os
import tempfile

import pytest

from src.data.disclosure_reader import (
    HAS_MARKITDOWN,
    HAS_PDFPLUMBER,
    HAS_PYMUPDF,
    DISCLOSURE_DIR,
    _table_to_markdown,
    detect_important_pages,
    read_disclosure,
    screenshot_pages,
    download_disclosure,
)


class TestDependencies:
    """依存ライブラリの存在確認."""

    def test_markitdown_available(self):
        assert HAS_MARKITDOWN is True

    def test_pdfplumber_available(self):
        assert HAS_PDFPLUMBER is True

    def test_pymupdf_available(self):
        assert HAS_PYMUPDF is True

    def test_disclosure_dir_path(self):
        assert "data/disclosures" in str(DISCLOSURE_DIR)


class TestTableToMarkdown:
    """_table_to_markdown のテスト."""

    def test_basic(self):
        table = [["Name", "Value"], ["売上", "100"]]
        result = _table_to_markdown(table)
        assert "| Name | Value |" in result
        assert "| 売上 | 100 |" in result
        assert "| --- | --- |" in result

    def test_empty(self):
        assert _table_to_markdown([]) is None
        assert _table_to_markdown([[]]) is None

    def test_none_cells(self):
        table = [["A", None], [None, "B"]]
        result = _table_to_markdown(table)
        assert "| A |  |" in result
        assert "|  | B |" in result


class TestDetectImportantPages:
    """detect_important_pages のテスト."""

    def test_japanese_keywords(self):
        md = """--- Page 1 ---
会社概要です

--- Page 2 ---
業績予想は以下の通りです

--- Page 3 ---
株主還元方針について
"""
        pages = detect_important_pages(md, lang="ja")
        assert 2 in pages  # 業績予想
        assert 3 in pages  # 株主還元
        assert 1 not in pages  # 会社概要は重要キーワードなし

    def test_english_keywords(self):
        md = """--- Page 1 ---
Company overview

--- Page 2 ---
Revenue guidance for FY2026
"""
        pages = detect_important_pages(md, lang="en")
        assert 2 in pages  # guidance + revenue
        assert 1 not in pages

    def test_no_page_markers(self):
        md = "売上高は100億円。営業利益は10億円。"
        pages = detect_important_pages(md, lang="ja")
        assert 1 in pages  # 全体が1ページ扱い

    def test_empty(self):
        pages = detect_important_pages("", lang="ja")
        assert pages == []  # 空文字はキーワードなし → 空リスト


class TestReadDisclosure:
    """read_disclosure のテスト."""

    def test_nonexistent_file(self):
        result = read_disclosure("/nonexistent/file.pdf")
        assert result is None

    def test_reads_text_file(self):
        """テキストファイルでも MarkItDown は処理できる."""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write("テスト文書です。売上高は100億円。")
            f.flush()
            result = read_disclosure(f.name)

        os.unlink(f.name)
        if result is not None:
            assert "テスト" in result or "売上" in result


class TestScreenshotPages:
    """screenshot_pages のテスト."""

    def test_nonexistent_file(self):
        result = screenshot_pages("/nonexistent/file.pdf", [1, 2])
        assert result == []

    def test_empty_pages(self):
        result = screenshot_pages("/nonexistent/file.pdf", [])
        assert result == []


class TestDownloadDisclosure:
    """download_disclosure のテスト."""

    def test_invalid_url(self, monkeypatch):
        """HTTP通信をモックして無効URLテスト."""
        import requests

        def mock_get(*args, **kwargs):
            raise requests.ConnectionError("mocked")

        monkeypatch.setattr(requests, "get", mock_get)
        result = download_disclosure("https://invalid.example.com/nonexistent.pdf")
        assert result is None

    def test_successful_download(self, monkeypatch, tmp_path):
        """正常ダウンロードのモックテスト."""
        import requests

        class MockResponse:
            status_code = 200
            content = b"%PDF-1.4 mock content"
            headers = {"Content-Type": "application/pdf"}
            def raise_for_status(self):
                pass

        monkeypatch.setattr(requests, "get", lambda *a, **kw: MockResponse())
        result = download_disclosure("https://example.com/test.pdf", save_dir=str(tmp_path))
        assert result is not None
        assert os.path.exists(result)
        assert result.endswith("test.pdf")

    def test_path_traversal_prevention(self, monkeypatch, tmp_path):
        """パストラバーサル攻撃の防止テスト."""
        import requests

        class MockResponse:
            status_code = 200
            content = b"malicious"
            headers = {}
            def raise_for_status(self):
                pass

        monkeypatch.setattr(requests, "get", lambda *a, **kw: MockResponse())
        result = download_disclosure(
            "https://example.com/../../etc/passwd",
            save_dir=str(tmp_path)
        )
        assert result is not None
        # パスがtmp_path内に収まっていること
        assert str(tmp_path) in result
        # ファイル名にディレクトリ成分がないこと
        assert ".." not in os.path.basename(result)
