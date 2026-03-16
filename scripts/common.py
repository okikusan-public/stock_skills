"""Common utilities for skill scripts -- path setup and graceful imports."""

import signal
import sys
from pathlib import Path
from typing import Optional

_CONTEXT_TIMEOUT = 10  # seconds — max wait for context/suggestions


# ---------------------------------------------------------------------------
# Human-readable error messages (KIK-443)
# ---------------------------------------------------------------------------

_ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "neo4j_unavailable": {
        "title": "Neo4jに接続できません",
        "cause": "Dockerコンテナが起動していない可能性があります",
        "fix": "docker compose up -d を実行してください",
        "fallback": "Neo4jなしで続行します（コンテキストなし）",
    },
    "grok_not_configured": {
        "title": "Grok APIキーが設定されていません",
        "cause": "XAI_API_KEY 環境変数が未設定です",
        "fix": "export XAI_API_KEY=your_key を設定してください",
        "fallback": "yfinanceデータのみで実行します",
    },
    "grok_auth_error": {
        "title": "Grok API認証エラー",
        "cause": "APIキーが無効または期限切れの可能性があります",
        "fix": "xai.com でAPIキーを確認・再発行してください",
        "fallback": "yfinanceデータのみで実行します",
    },
    "grok_rate_limited": {
        "title": "Grok APIのレート制限に達しました",
        "cause": "短時間に多くのリクエストが送信されました",
        "fix": "しばらく待ってから再試行してください（通常1〜2分）",
        "fallback": "yfinanceデータのみで実行します",
    },
    "yahoo_timeout": {
        "title": "Yahoo Financeへの接続がタイムアウトしました",
        "cause": "ネットワーク接続が不安定、またはYahoo Financeが一時的に応答していません",
        "fix": "ネットワーク接続を確認し、再試行してください",
        "fallback": "該当銘柄のデータを取得できませんでした",
    },
    "portfolio_not_found": {
        "title": "ポートフォリオデータが見つかりません",
        "cause": "portfolio.csv がまだ作成されていません",
        "fix": "まず buy コマンドで銘柄を追加してください（例: run_portfolio.py buy --symbol 7203.T --shares 100 --price 2800）",
        "fallback": None,
    },
}


def format_user_error(error_type: str, context: str = "") -> str:
    """Format a human-readable error message for the given error type.

    Args:
        error_type: One of neo4j_unavailable, grok_not_configured,
                    grok_auth_error, grok_rate_limited,
                    yahoo_timeout, portfolio_not_found.
        context: Optional extra context (e.g. symbol name).

    Returns:
        Formatted multi-line string suitable for printing to the user.
    """
    msg = _ERROR_MESSAGES.get(error_type)
    if msg is None:
        return f"⚠️  エラーが発生しました: {error_type}" + (f" ({context})" if context else "")

    lines = [f"⚠️  {msg['title']}"]
    if context:
        lines.append(f"    対象: {context}")
    lines.append(f"    原因: {msg['cause']}")
    lines.append(f"    対処: {msg['fix']}")
    if msg.get("fallback"):
        lines.append(f"    → {msg['fallback']}")
    return "\n".join(lines)


def setup_project_path(script_file: str, depth: int = 4) -> str:
    """Add project root to sys.path.

    Args:
        script_file: __file__ of the calling script
        depth: directory levels from script to project root
               4 for .claude/skills/*/scripts/*.py
               2 for scripts/*.py

    Returns:
        Project root path as string.
    """
    root = str(Path(script_file).resolve().parents[depth - 1])
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def try_import(module_path: str, *names: str):
    """Import names from a module with graceful degradation.

    Args:
        module_path: Dotted module path (e.g. "src.data.history_store")
        *names: Names to import from the module

    Returns:
        tuple: (success: bool, imports: dict)
               imports maps each name to the imported object or None.

    Example:
        ok, imports = try_import("src.data.history_store", "save_screening")
        save_screening = imports["save_screening"]
        if ok:
            save_screening(...)
    """
    result = {n: None for n in names}
    try:
        mod = __import__(module_path, fromlist=list(names))
        for name in names:
            result[name] = getattr(mod, name)
        return True, result
    except (ImportError, AttributeError):
        return False, result


# ---------------------------------------------------------------------------
# Module availability flags (KIK-448)
#
# Centralised checks for optional modules used by 2+ skill scripts.
# Each flag answers "can this module be imported?" — nothing more.
# Individual scripts still import the specific functions they need,
# guarded by these flags.
# ---------------------------------------------------------------------------

try:
    import src.data.history_store as _history_store_mod  # noqa: F401
    HAS_HISTORY_STORE = True
except ImportError:
    HAS_HISTORY_STORE = False

try:
    import src.data.graph_query as _graph_query_mod  # noqa: F401
    HAS_GRAPH_QUERY = True
except ImportError:
    HAS_GRAPH_QUERY = False

try:
    import src.data.graph_store as _graph_store_mod  # noqa: F401
    HAS_GRAPH_STORE = True
except ImportError:
    HAS_GRAPH_STORE = False

try:
    import src.data.linear_client as _linear_client_mod  # noqa: F401
    HAS_LINEAR_CLIENT = True
except ImportError:
    HAS_LINEAR_CLIENT = False


# ---------------------------------------------------------------------------
# Context retrieval & proactive suggestions (KIK-465)
#
# Embedded into each skill script's start/end for reliable execution.
# Graceful degradation: returns None / no output on any failure.
# ---------------------------------------------------------------------------

def _timeout_handler(signum, frame):
    raise TimeoutError("Context/suggestion timeout")


def print_context(user_input: str) -> Optional[str]:
    """Get and print graph context at script start.

    Returns the action label (FRESH/RECENT/STALE/NONE) or None on failure.
    Timeout: 10 seconds max. Graceful degradation on any error.
    """
    if not user_input:
        return None
    try:
        from src.data.auto_context import get_context

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_CONTEXT_TIMEOUT)
        try:
            result = get_context(user_input)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        if result and result.get("context_markdown"):
            print(result["context_markdown"])
            print()
            return result.get("action_label")
        return None
    except Exception:
        return None


def print_removal_contexts(symbols: list[str]) -> None:
    """Print graph context for removal candidate symbols (KIK-470).

    Called before what-if simulation to show screening history,
    investment notes, and research for stocks about to be sold.
    Timeout: 10 seconds total. Graceful degradation on any error.
    """
    if not symbols:
        return
    try:
        from src.data.auto_context import get_context

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_CONTEXT_TIMEOUT)
        try:
            contexts = []
            for sym in symbols:
                result = get_context(sym)
                if result and result.get("context_markdown"):
                    contexts.append(result["context_markdown"])
            if contexts:
                print("---")
                print("## 売却候補のコンテキスト (KIK-470)\n")
                print("\n\n".join(contexts))
                print()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except Exception:
        pass  # graceful degradation


def print_suggestions(
    symbol: str = "",
    sector: str = "",
    context_summary: str = "",
    health_data: dict | None = None,
) -> None:
    """Print proactive suggestions at script end.

    Args:
        symbol: Current symbol in focus.
        sector: Current sector in focus.
        context_summary: Execution result summary for context-aware suggestions.
        health_data: Health check result dict (optional, for action item extraction).
    """
    suggestions: list[dict] = []
    try:
        from src.core.proactive_engine import format_suggestions, get_suggestions

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_CONTEXT_TIMEOUT)
        try:
            suggestions = get_suggestions(
                context=context_summary,
                symbol=symbol,
                sector=sector,
            )
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        output = format_suggestions(suggestions)
        if output:
            print(output)
    except Exception:
        pass

    # Action item processing (KIK-472)
    _process_action_items(suggestions, health_data, context_summary)

    # Community incremental update (KIK-549)
    _maybe_refresh_communities()


def _process_action_items(
    suggestions: list[dict],
    health_data: dict | None = None,
    context_summary: str = "",
) -> None:
    """Process action items from suggestions and health data (KIK-472).

    Calls action_item_bridge.process_action_items() and displays results.
    Graceful degradation: no output on any failure.
    """
    try:
        from src.core.action_item_bridge import process_action_items

        results = process_action_items(
            suggestions=suggestions,
            health_data=health_data,
        )
        if not results:
            return

        lines = ["\n---", "📌 **アクションアイテム** (自動検出)\n"]
        for r in results:
            title = r.get("title", "")
            symbol = r.get("symbol", "")
            linear = r.get("linear_issue")
            neo4j = r.get("neo4j_saved", False)

            status_parts = []
            if neo4j:
                status_parts.append("Neo4j保存済")
            if linear:
                ident = linear.get("identifier", "")
                url = linear.get("url", "")
                if ident and url:
                    status_parts.append(f"Linear: [{ident}]({url})")
                elif ident:
                    status_parts.append(f"Linear: {ident}")

            status = " / ".join(status_parts) if status_parts else "検出済"
            lines.append(f"- {title} ({status})")

        print("\n".join(lines))
    except Exception:
        pass  # graceful degradation


def _maybe_refresh_communities() -> None:
    """Check for unclustered stocks and trigger incremental update (KIK-549).

    If new Stock nodes exist that are not in any Community, assign them
    to their best-matching community. If unclustered count exceeds threshold,
    trigger a full re-detection.
    Graceful degradation: no output on any failure.
    """
    try:
        if not HAS_GRAPH_QUERY:
            return
        from src.data.graph_query.community import (
            get_communities,
            update_stock_community,
        )
        from src.data.graph_query._common import _get_driver

        driver = _get_driver()
        if driver is None:
            return

        # Find stocks not in any community
        with driver.session() as session:
            result = session.run(
                "MATCH (s:Stock) "
                "WHERE NOT (s)-[:BELONGS_TO]->(:Community) "
                "RETURN s.symbol AS symbol LIMIT 20"
            )
            unclustered = [r["symbol"] for r in result]

        if not unclustered:
            return

        # If too many unclustered, trigger full re-detection
        if len(unclustered) >= 10:
            from src.data.graph_query.community import detect_communities
            detect_communities()
            return

        # Incremental: assign each to best community
        for sym in unclustered:
            update_stock_community(sym)
    except Exception:
        pass  # graceful degradation
