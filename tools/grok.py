"""Grok API Tool — Grok (xAI) 検索ファサード.

tools/ 層は API 呼び出しのみを担う。判断ロジックは含めない。
src/data/grok_client/ の純粋な検索関数を re-export する。
XAI_API_KEY 未設定時は graceful degradation（各関数が空値を返す）。
"""

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from src.data.grok_client import (  # noqa: E402
        # 可用性チェック
        is_available,
        get_error_status,
        # 銘柄検索
        search_stock_deep,
        search_x_sentiment,
        # マーケット検索
        search_market,
        search_trending_stocks,
        get_trending_themes,
        # 業界検索
        search_industry,
        # ビジネスモデル検索
        search_business,
        # テキスト合成
        synthesize_text,
    )
    HAS_GROK = True
except ImportError:
    HAS_GROK = False

__all__ = [
    # 可用性
    "is_available",
    "get_error_status",
    # 銘柄
    "search_stock_deep",
    "search_x_sentiment",
    # マーケット
    "search_market",
    "search_trending_stocks",
    "get_trending_themes",
    # 業界
    "search_industry",
    # ビジネスモデル
    "search_business",
    # テキスト合成
    "synthesize_text",
    # フラグ
    "HAS_GROK",
]
