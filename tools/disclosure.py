"""Disclosure Tool — IR資料読み取りファサード.

tools/ 層は API 呼び出しのみを担う。判断ロジックは含めない。
src/data/disclosure_reader.py の関数を re-export する。
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.disclosure_reader import (  # noqa: E402
    read_disclosure,
    detect_important_pages,
    screenshot_pages,
    download_disclosure,
    HAS_MARKITDOWN,
    HAS_PDFPLUMBER,
    HAS_PYMUPDF,
)

__all__ = [
    "read_disclosure",
    "detect_important_pages",
    "screenshot_pages",
    "download_disclosure",
    "HAS_MARKITDOWN",
    "HAS_PDFPLUMBER",
    "HAS_PYMUPDF",
]
