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

# --- 一括同期 (KIK-712) ---


def sync_all() -> dict:
    """data/ → GraphRAG の一括同期.

    SKILL.md の「syncして」に対応する便利関数。
    Neo4j 未接続時は早期リターン。個別ファイルのエラーは続行。

    Returns
    -------
    dict
        {"synced": [...], "failed": [...], "skipped": [...]}
    """
    import json
    import glob
    from datetime import datetime

    result = {"synced": [], "failed": [], "skipped": []}

    # Neo4j 接続チェック
    try:
        from src.data.graph_store._common import is_available
        if not is_available():
            return {"synced": [], "failed": [], "skipped": ["Neo4j未接続"]}
    except ImportError:
        return {"synced": [], "failed": [], "skipped": ["graph_store未インストール"]}

    # 1. Portfolio sync
    try:
        from src.data.portfolio_io import load_portfolio, DEFAULT_CSV_PATH
        from src.data.graph_store.portfolio import sync_portfolio
        holdings = load_portfolio(DEFAULT_CSV_PATH)
        if holdings:
            sync_portfolio(holdings)
            result["synced"].append(f"portfolio({len(holdings)}銘柄)")
    except Exception as e:
        result["failed"].append(f"portfolio: {e}")

    # 2. Notes sync (data/notes/*.json)
    try:
        from src.data.graph_store.note import merge_note as _merge_note
        notes_dir = Path(_project_root) / "data" / "notes"
        if notes_dir.exists():
            note_files = sorted(notes_dir.glob("*.json"))
            synced_count = 0
            for nf in note_files:
                try:
                    with open(nf, "r", encoding="utf-8") as f:
                        note = json.load(f)
                    _merge_note(
                        note_id=note.get("id", nf.stem),
                        note_date=note.get("date", ""),
                        note_type=note.get("type", "observation"),
                        content=note.get("content", ""),
                        symbol=note.get("symbol"),
                        source=note.get("source", "claude"),
                        category=note.get("category", ""),
                    )
                    synced_count += 1
                except Exception:
                    result["failed"].append(f"note: {nf.name}")
            if synced_count:
                result["synced"].append(f"notes({synced_count}件)")
    except Exception as e:
        result["failed"].append(f"notes: {e}")

    # 3. Update sync_status.yaml
    try:
        status_path = Path(_project_root) / "data" / "sync_status.yaml"
        import yaml
        status = {"last_sync": datetime.now().isoformat()}
        with open(status_path, "w", encoding="utf-8") as f:
            yaml.dump(status, f)
        result["synced"].append("sync_status更新")
    except Exception:
        pass  # non-critical

    return result


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
    # 同期
    "sync_all",
    # フラグ
    "HAS_GRAPH_QUERY",
    "HAS_GRAPH_STORE",
    "HAS_CONTEXT",
]
