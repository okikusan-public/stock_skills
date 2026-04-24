"""Disclosure Reader — IR資料のテキスト抽出+スクショ解析.

2パス方式:
  1st pass: MarkItDown でテキスト抽出 → Markdown化
  2nd pass: 重要ページだけスクショ → Vision で図表読み（補助）

判断ロジックは含めない。抽出のみ。
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import requests

# MarkItDown（1st pass: テキスト抽出）
try:
    from markitdown import MarkItDown
    HAS_MARKITDOWN = True
except ImportError:
    HAS_MARKITDOWN = False

# pdfplumber（テーブル抽出のフォールバック）
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# PyMuPDF（2nd pass: スクショ画像化）
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISCLOSURE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "disclosures"

# 重要ページ検出キーワード
IMPORTANT_KEYWORDS_JA = [
    "業績予想", "ガイダンス", "通期予想", "配当", "株主還元",
    "自社株買い", "KPI", "セグメント", "成長戦略", "中期経営計画",
    "売上高", "営業利益", "経常利益", "純利益", "キャッシュ・フロー",
]

IMPORTANT_KEYWORDS_EN = [
    "guidance", "outlook", "forecast", "dividend", "buyback",
    "segment", "revenue", "operating income", "net income",
    "cash flow", "KPI", "growth strategy",
]


# ---------------------------------------------------------------------------
# 1st pass: テキスト抽出
# ---------------------------------------------------------------------------

def read_disclosure(file_path: str) -> Optional[str]:
    """PDF/DOCX/XLSX/PPTXをMarkdownに変換して返す.

    Parameters
    ----------
    file_path : str
        ローカルファイルパス

    Returns
    -------
    str or None
        Markdownテキスト。変換失敗時は None
    """
    if not os.path.exists(file_path):
        return None

    if HAS_MARKITDOWN:
        try:
            md = MarkItDown()
            result = md.convert(file_path)
            return result.text_content
        except Exception:
            pass

    # MarkItDown が使えない or 失敗した場合、pdfplumber でフォールバック
    if HAS_PDFPLUMBER and file_path.lower().endswith(".pdf"):
        return _read_pdf_pdfplumber(file_path)

    return None


def _read_pdf_pdfplumber(file_path: str) -> Optional[str]:
    """pdfplumber でPDFをテキスト抽出（フォールバック）."""
    try:
        pages_text = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    pages_text.append(f"--- Page {i} ---\n{text}")

                # テーブル抽出
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        # Markdown テーブルに変換
                        md_table = _table_to_markdown(table)
                        if md_table:
                            pages_text.append(md_table)

        return "\n\n".join(pages_text) if pages_text else None
    except Exception:
        return None


def _table_to_markdown(table: list[list]) -> Optional[str]:
    """2D リストを Markdown テーブルに変換."""
    if not table or not table[0]:
        return None

    rows = []
    for i, row in enumerate(table):
        cells = [str(c).strip() if c else "" for c in row]
        rows.append("| " + " | ".join(cells) + " |")
        if i == 0:
            rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# 重要ページ検出
# ---------------------------------------------------------------------------

def detect_important_pages(markdown: str, lang: str = "ja") -> list[int]:
    """Markdown化した内容から重要ページ候補を選ぶ.

    Parameters
    ----------
    markdown : str
        read_disclosure() の出力
    lang : str
        "ja" or "en"

    Returns
    -------
    list[int]
        重要ページ番号のリスト（1-indexed）
    """
    keywords = IMPORTANT_KEYWORDS_JA if lang == "ja" else IMPORTANT_KEYWORDS_EN
    important_pages = set()

    # ページ区切りを検出（MarkItDown / pdfplumber の出力パターン）
    pages = re.split(r"---\s*Page\s+(\d+)\s*---", markdown)

    # ページ番号とコンテンツのペアを作成
    page_contents: list[tuple[int, str]] = []
    if len(pages) > 1:
        # "--- Page N ---" 形式で分割された場合
        for i in range(1, len(pages), 2):
            page_num = int(pages[i])
            content = pages[i + 1] if i + 1 < len(pages) else ""
            page_contents.append((page_num, content))
    else:
        # ページ区切りがない場合、全体を1ページとして扱う
        page_contents.append((1, markdown))

    for page_num, content in page_contents:
        content_lower = content.lower()
        for kw in keywords:
            if kw.lower() in content_lower:
                important_pages.add(page_num)
                break

    return sorted(important_pages)


# ---------------------------------------------------------------------------
# 2nd pass: スクショ画像化
# ---------------------------------------------------------------------------

def screenshot_pages(file_path: str, pages: list[int],
                     output_dir: Optional[str] = None,
                     dpi: int = 200) -> list[str]:
    """指定ページだけスクショ画像化.

    Parameters
    ----------
    file_path : str
        PDFファイルパス
    pages : list[int]
        画像化するページ番号（1-indexed）
    output_dir : str, optional
        画像の保存先。None の場合は一時ディレクトリ
    dpi : int
        画像解像度（デフォルト200）

    Returns
    -------
    list[str]
        生成された画像ファイルパスのリスト

    Note
    ----
    output_dir が None の場合、一時ディレクトリが作成される。
    呼び出し側が不要になったら shutil.rmtree() で削除すること。
    """
    if not HAS_PYMUPDF:
        return []

    if not os.path.exists(file_path):
        return []

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="disclosure_")
    else:
        os.makedirs(output_dir, exist_ok=True)

    image_paths = []
    try:
        doc = fitz.open(file_path)
        for page_num in pages:
            idx = page_num - 1  # 0-indexed
            if 0 <= idx < len(doc):
                page = doc[idx]
                zoom = dpi / 72  # 72 DPI が標準
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                stem = Path(file_path).stem
                img_path = os.path.join(output_dir, f"{stem}_p{page_num}.png")
                pix.save(img_path)
                image_paths.append(img_path)
        doc.close()
    except Exception:
        pass

    return image_paths


# ---------------------------------------------------------------------------
# ダウンロード
# ---------------------------------------------------------------------------

def download_disclosure(url: str, save_dir: Optional[str] = None) -> Optional[str]:
    """URLからIR資料をダウンロードし、ローカルパスを返す.

    Parameters
    ----------
    url : str
        IR資料のURL
    save_dir : str, optional
        保存先ディレクトリ。None の場合は data/disclosures/

    Returns
    -------
    str or None
        ダウンロードしたファイルのローカルパス。失敗時は None
    """
    if save_dir is None:
        save_dir = str(DISCLOSURE_DIR)

    os.makedirs(save_dir, exist_ok=True)

    try:
        response = requests.get(url, timeout=30, allow_redirects=True)
        response.raise_for_status()

        # ファイル名をURLから推定
        filename = url.split("/")[-1]
        if not filename or "." not in filename:
            # Content-Disposition から取得
            cd = response.headers.get("Content-Disposition", "")
            if "filename" in cd:
                filename = cd.split("filename=")[-1].strip('"')
            else:
                filename = "disclosure.pdf"

        # URL デコード + パストラバーサル防止
        from urllib.parse import unquote
        filename = unquote(filename)
        filename = os.path.basename(filename)  # ディレクトリ成分を除去

        if not filename or filename.startswith("."):
            filename = "disclosure.pdf"

        file_path = os.path.join(save_dir, filename)
        with open(file_path, "wb") as f:
            f.write(response.content)

        return file_path

    except Exception:
        return None


# ---------------------------------------------------------------------------
# 公開API
# ---------------------------------------------------------------------------

__all__ = [
    "read_disclosure",
    "detect_important_pages",
    "screenshot_pages",
    "download_disclosure",
    "HAS_MARKITDOWN",
    "HAS_PDFPLUMBER",
    "HAS_PYMUPDF",
    "DISCLOSURE_DIR",
]
