"""Yahoo Finance Tool — データ取得ファサード.

tools/ 層は外部API接続のみを担う。判断ロジック（スコア計算、フィルタリング等）は含めない。
src/data/yahoo_client/ の純粋なデータ取得関数を re-export する。
"""

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.yahoo_client import (  # noqa: E402
    get_stock_info,
    get_multiple_stocks,
    get_stock_detail,
    get_price_history,
    get_stock_news,
    get_macro_indicators,
    screen_stocks,
)

__all__ = [
    "get_stock_info",
    "get_multiple_stocks",
    "get_stock_detail",
    "get_price_history",
    "get_stock_news",
    "get_macro_indicators",
    "screen_stocks",
]
