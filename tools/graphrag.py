"""GraphRAG Tool — Neo4j ナレッジグラフ ファサード.

tools/ 層は保存・取得のみを担う。判断ロジックは含めない。
src/data/graph_store/ と src/data/graph_query/ の純粋な関数を re-export する。
Neo4j 未接続時は graceful degradation（各関数が空値を返す）。
"""

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# --- 取得系 (graph_query) ---
try:
    from src.data.graph_query import (  # noqa: E402
        get_prior_report,
        get_screening_frequency,
        get_trade_context,
        get_report_trend,
        get_research_chain,
        get_stock_news_history,
        get_sentiment_trend,
        get_catalysts,
        get_current_holdings,
        get_holdings_notes,
        get_stress_test_history,
        get_forecast_history,
        get_recent_market_context,
        get_upcoming_events,
        get_theme_trends,
        get_communities,
        get_stock_community,
        get_community_lessons,
    )
    HAS_GRAPH_QUERY = True
except ImportError:
    HAS_GRAPH_QUERY = False

# --- 保存系 (graph_store) ---
try:
    from src.data.graph_store import (  # noqa: E402
        get_stock_history,
        merge_note,
        merge_trade,
        merge_report,
        merge_screen,
        get_open_action_items,
    )
    HAS_GRAPH_STORE = True
except ImportError:
    HAS_GRAPH_STORE = False

# --- コンテキスト (auto_context) ---
try:
    from src.data.context import get_context  # noqa: E402
    HAS_CONTEXT = True
except ImportError:
    HAS_CONTEXT = False

__all__ = [
    # 取得系
    "get_prior_report",
    "get_screening_frequency",
    "get_trade_context",
    "get_report_trend",
    "get_research_chain",
    "get_stock_news_history",
    "get_sentiment_trend",
    "get_catalysts",
    "get_current_holdings",
    "get_holdings_notes",
    "get_stress_test_history",
    "get_forecast_history",
    "get_recent_market_context",
    "get_upcoming_events",
    "get_theme_trends",
    "get_communities",
    "get_stock_community",
    "get_community_lessons",
    # 保存系
    "get_stock_history",
    "merge_note",
    "merge_trade",
    "merge_report",
    "merge_screen",
    "get_open_action_items",
    # コンテキスト
    "get_context",
    # フラグ
    "HAS_GRAPH_QUERY",
    "HAS_GRAPH_STORE",
    "HAS_CONTEXT",
]
