"""Portfolio I/O Tool — PF CSV 読み書きファサード.

tools/ 層は保存・取得のみを担う。判断ロジックは含めない。
src/core/portfolio/portfolio_io の純粋なデータ操作関数を re-export する。
"""

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.data.portfolio_io import (  # noqa: E402
    load_portfolio,
    save_portfolio,
    add_position,
    sell_position,
    get_performance_review,
    DEFAULT_CSV_PATH,
)

__all__ = [
    "load_portfolio",
    "save_portfolio",
    "add_position",
    "sell_position",
    "get_performance_review",
    "DEFAULT_CSV_PATH",
]
