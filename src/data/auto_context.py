"""Auto graph context injection for user prompts (KIK-411/420/427).

Detects ticker symbols in user input, queries Neo4j for past knowledge,
and recommends the optimal skill based on graph state.
KIK-420: Hybrid search — vector similarity + symbol-based retrieval.
KIK-427: Freshness labels (FRESH/RECENT/STALE) with env-configurable thresholds.
Returns None when no context available or Neo4j unavailable (graceful degradation).
"""

import os
import re
from datetime import date, datetime, timedelta
from typing import Optional

from src.data import graph_store, graph_query


# ---------------------------------------------------------------------------
# Symbol detection (reuse graph_nl_query pattern)
# ---------------------------------------------------------------------------

_SYMBOL_PATTERN = re.compile(
    r"(\d{4}\.[A-Z]+|[A-Z][A-Z0-9]{0,4}(?:\.[A-Z]{1,2})?)"
)


def _extract_symbol(text: str) -> Optional[str]:
    """Extract a ticker symbol from text (e.g. 7203.T, AAPL, D05.SI)."""
    m = _SYMBOL_PATTERN.search(text)
    return m.group(1) if m else None


def _lookup_symbol_by_name(text: str) -> Optional[str]:
    """Reverse-lookup symbol from company name via Neo4j Stock.name field."""
    driver = graph_store._get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (s:Stock) WHERE toLower(s.name) CONTAINS toLower($name) "
                "RETURN s.symbol AS symbol LIMIT 1",
                name=text.strip(),
            )
            record = result.single()
            return record["symbol"] if record else None
    except Exception:
        return None


def _resolve_symbol(user_input: str) -> Optional[str]:
    """Extract or resolve a ticker symbol from user input."""
    symbol = _extract_symbol(user_input)
    if symbol:
        return symbol
    return _lookup_symbol_by_name(user_input)


# ---------------------------------------------------------------------------
# Market / portfolio context (non-symbol queries)
# ---------------------------------------------------------------------------

_MARKET_KEYWORDS = re.compile(r"(相場|市況|マーケット|market)", re.IGNORECASE)
_PF_KEYWORDS = re.compile(r"(PF|ポートフォリオ|portfolio)", re.IGNORECASE)


def _is_market_query(text: str) -> bool:
    return bool(_MARKET_KEYWORDS.search(text))


def _is_portfolio_query(text: str) -> bool:
    return bool(_PF_KEYWORDS.search(text))


# ---------------------------------------------------------------------------
# Graph state analysis helpers
# ---------------------------------------------------------------------------

def _today_str() -> str:
    return date.today().isoformat()


def _days_since(date_str: str) -> int:
    """Return days between date_str and today. Returns 9999 on parse error."""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 9999


# ---------------------------------------------------------------------------
# Freshness detection (KIK-427)
# ---------------------------------------------------------------------------

def _fresh_hours() -> int:
    """Return CONTEXT_FRESH_HOURS threshold (default 24)."""
    try:
        return int(os.environ.get("CONTEXT_FRESH_HOURS", "24"))
    except (ValueError, TypeError):
        return 24


def _recent_hours() -> int:
    """Return CONTEXT_RECENT_HOURS threshold (default 168 = 7 days)."""
    try:
        return int(os.environ.get("CONTEXT_RECENT_HOURS", "168"))
    except (ValueError, TypeError):
        return 168


def _hours_since(date_str: str) -> float:
    """Return hours between date_str and now. Returns 999999 on parse error."""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (datetime.now() - d).total_seconds() / 3600
    except (ValueError, TypeError):
        return 999999


def freshness_label(date_str: str) -> str:
    """Return freshness label for a date string.

    Returns one of: FRESH, RECENT, STALE, NONE.
    """
    if not date_str:
        return "NONE"
    h = _hours_since(date_str)
    if h <= _fresh_hours():
        return "FRESH"
    if h <= _recent_hours():
        return "RECENT"
    return "STALE"


def freshness_action(label: str) -> str:
    """Return recommended action for a freshness label."""
    return {
        "FRESH": "コンテキスト利用",
        "RECENT": "差分モード推奨",
        "STALE": "フル再取得推奨",
        "NONE": "新規取得",
    }.get(label, "新規取得")


def _has_bought_not_sold(history: dict) -> bool:
    """Check if there are BOUGHT trades but no matching SOLD trades."""
    trades = history.get("trades", [])
    bought = [t for t in trades if t.get("type") == "buy"]
    sold = [t for t in trades if t.get("type") == "sell"]
    return len(bought) > 0 and len(sold) < len(bought)


def _is_bookmarked(history: dict) -> bool:
    """Check if the symbol appears in any watchlist (via graph_query)."""
    # Watchlist info is not in get_stock_history; check via screens/notes pattern
    # For now, we rely on graph_store having BOOKMARKED relationship
    # This is checked separately in get_context()
    return False  # Placeholder - checked via separate query


def _screening_count(history: dict) -> int:
    """Count how many Screen nodes reference this stock."""
    return len(history.get("screens", []))


def _has_recent_research(history: dict, days: int = 7) -> bool:
    """Check if there's a Research within the given days."""
    for r in history.get("researches", []):
        if _days_since(r.get("date", "")) <= days:
            return True
    return False


def _has_exit_alert(history: dict) -> bool:
    """Check if latest health check had EXIT alert (via notes/health_checks)."""
    # Health checks don't store alert detail in graph; approximate via recent
    # health check existence + notes with concern type
    health_checks = history.get("health_checks", [])
    if not health_checks:
        return False
    # Check for recent concern/lesson notes as proxy for EXIT
    notes = history.get("notes", [])
    for n in notes:
        if n.get("type") == "lesson" and _days_since(n.get("date", "")) <= 30:
            return True
    return False


def _thesis_needs_review(history: dict, days: int = 90) -> bool:
    """Check if a thesis note exists and is older than the given days."""
    notes = history.get("notes", [])
    for n in notes:
        if n.get("type") == "thesis" and _days_since(n.get("date", "")) >= days:
            return True
    return False


def _has_concern_notes(history: dict) -> bool:
    """Check if there are concern-type notes."""
    notes = history.get("notes", [])
    return any(n.get("type") == "concern" for n in notes)


# ---------------------------------------------------------------------------
# Skill recommendation
# ---------------------------------------------------------------------------

def _recommend_skill(history: dict, is_bookmarked: bool,
                     is_held: bool = False) -> tuple[str, str, str]:
    """Determine recommended skill based on graph state.

    Returns (skill, reason, relationship).
    """
    # Priority order: higher = checked first
    # KIK-414: HOLDS relationship is authoritative for current holdings
    if is_held or _has_bought_not_sold(history):
        if _thesis_needs_review(history, 90):
            return ("health", "テーゼ3ヶ月経過 → レビュー促し", "保有(要レビュー)")
        return ("health", "保有銘柄 → ヘルスチェック優先", "保有")

    if _has_exit_alert(history):
        return ("screen_alternative", "EXIT判定 → 代替候補検索", "EXIT判定")

    if is_bookmarked:
        return ("report", "ウォッチ中 → レポート + 前回差分", "ウォッチ中")

    if _screening_count(history) >= 3:
        return ("report", "3回以上スクリーニング出現 → 注目銘柄", "注目")

    if _has_recent_research(history, 7):
        return ("report_diff", "直近リサーチあり → 差分モード", "リサーチ済")

    if _has_concern_notes(history):
        return ("report", "懸念メモあり → 再検証", "懸念あり")

    if history.get("screens") or history.get("reports") or history.get("trades"):
        return ("report", "過去データあり → レポート", "既知")

    return ("report", "未知の銘柄 → ゼロから調査", "未知")


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def _format_context(symbol: str, history: dict, skill: str, reason: str,
                    relationship: str) -> str:
    """Format graph context as markdown with freshness labels (KIK-427)."""
    lines = [f"## 過去の経緯: {symbol} ({relationship})"]

    # Track freshness by data type for summary
    freshness_map: dict[str, str] = {}  # data_type -> label

    # Screens
    for s in history.get("screens", [])[:3]:
        d = s.get("date", "?")
        fl = freshness_label(d)
        lines.append(f"- [{fl}] {d} {s.get('preset', '')} "
                     f"スクリーニング ({s.get('region', '')})")
        freshness_map.setdefault("スクリーニング", fl)

    # Reports
    for r in history.get("reports", [])[:2]:
        d = r.get("date", "?")
        fl = freshness_label(d)
        verdict = r.get("verdict", "")
        score = r.get("score", "")
        lines.append(f"- [{fl}] {d} レポート: スコア {score}, {verdict}")
        freshness_map.setdefault("レポート", fl)

    # Trades
    for t in history.get("trades", [])[:3]:
        d = t.get("date", "?")
        fl = freshness_label(d)
        action = "購入" if t.get("type") == "buy" else "売却"
        lines.append(f"- [{fl}] {d} {action}: "
                     f"{t.get('shares', '')}株 @ {t.get('price', '')}")
        freshness_map.setdefault("取引", fl)

    # Health checks
    for h in history.get("health_checks", [])[:1]:
        d = h.get("date", "?")
        fl = freshness_label(d)
        lines.append(f"- [{fl}] {d} ヘルスチェック実施")
        freshness_map.setdefault("ヘルスチェック", fl)

    # Notes
    for n in history.get("notes", [])[:3]:
        content = (n.get("content", "") or "")[:50]
        lines.append(f"- メモ({n.get('type', '')}): {content}")

    # Themes
    themes = history.get("themes", [])
    if themes:
        lines.append(f"- テーマ: {', '.join(themes[:5])}")

    # Researches
    for r in history.get("researches", [])[:2]:
        d = r.get("date", "?")
        fl = freshness_label(d)
        summary = (r.get("summary", "") or "")[:50]
        lines.append(f"- [{fl}] {d} リサーチ({r.get('research_type', '')}): "
                     f"{summary}")
        freshness_map.setdefault("リサーチ", fl)

    if len(lines) == 1:
        lines.append("- (過去データなし)")

    # Freshness summary (KIK-427)
    if freshness_map:
        lines.append("")
        lines.append("### 鮮度サマリー")
        for dtype, fl in freshness_map.items():
            lines.append(f"- {dtype}: [{fl}] → {freshness_action(fl)}")

    lines.append(f"\n**推奨**: {skill} ({reason})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Market context formatting
# ---------------------------------------------------------------------------

def _format_market_context(mc: dict) -> str:
    """Format market context as markdown with freshness label (KIK-427)."""
    d = mc.get("date", "?")
    fl = freshness_label(d)
    lines = [f"## 直近の市況コンテキスト [{fl}]"]
    lines.append(f"- 取得日: {d} → {freshness_action(fl)}")
    for idx in mc.get("indices", [])[:5]:
        if isinstance(idx, dict):
            name = idx.get("name", idx.get("symbol", "?"))
            price = idx.get("price", idx.get("close", "?"))
            lines.append(f"- {name}: {price}")
    lines.append("\n**推奨**: market-research (市況照会)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bookmarked check (separate query since get_stock_history doesn't include it)
# ---------------------------------------------------------------------------

def _check_bookmarked(symbol: str) -> bool:
    """Check if symbol is in any watchlist via Neo4j."""
    driver = graph_store._get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (w:Watchlist)-[:BOOKMARKED]->(s:Stock {symbol: $symbol}) "
                "RETURN count(w) AS cnt",
                symbol=symbol,
            )
            record = result.single()
            return record["cnt"] > 0 if record else False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Vector search helpers (KIK-420)
# ---------------------------------------------------------------------------

def _vector_search(user_input: str) -> list[dict]:
    """Embed user input via TEI and run vector similarity search on Neo4j.

    Returns list of {label, summary, score, date, id, symbol?}.
    Empty list when TEI or Neo4j unavailable (graceful degradation).
    """
    try:
        from src.data.embedding_client import get_embedding, is_available
        if not is_available():
            return []
        emb = get_embedding(user_input)
        if emb is None:
            return []
        return graph_query.vector_search(emb, top_k=5)
    except Exception:
        return []


def _format_vector_results(results: list[dict]) -> str:
    """Format vector search results as markdown with freshness labels (KIK-427)."""
    lines = ["## 関連する過去の記録"]
    for r in results[:5]:
        score_pct = f"{r['score'] * 100:.0f}%"
        summary = r.get("summary") or "(要約なし)"
        fl = freshness_label(r.get("date", ""))
        lines.append(f"- [{r['label']}][{fl}] {summary} (類似度{score_pct})")
    return "\n".join(lines)


def _infer_skill_from_vectors(results: list[dict]) -> str:
    """Infer a recommended skill from vector search result labels."""
    if not results:
        return "report"
    label_counts: dict[str, int] = {}
    for r in results[:5]:
        label = r.get("label", "")
        label_counts[label] = label_counts.get(label, 0) + 1
    if not label_counts:
        return "report"
    top_label = max(label_counts, key=label_counts.get)  # type: ignore[arg-type]
    mapping = {
        "Screen": "screen-stocks",
        "Report": "report",
        "Trade": "health",
        "Research": "market-research",
        "HealthCheck": "health",
        "MarketContext": "market-research",
        "Note": "report",
    }
    return mapping.get(top_label, "report")


def _merge_context(
    symbol_context: Optional[dict],
    vector_results: list[dict],
) -> Optional[dict]:
    """Merge symbol-based context with vector search results."""
    if not symbol_context and not vector_results:
        return None

    if symbol_context and not vector_results:
        return symbol_context

    if not symbol_context and vector_results:
        return {
            "symbol": "",
            "context_markdown": _format_vector_results(vector_results),
            "recommended_skill": _infer_skill_from_vectors(vector_results),
            "recommendation_reason": "ベクトル類似検索",
            "relationship": "関連",
        }

    # Both available: append vector results to symbol context
    merged = dict(symbol_context)  # type: ignore[arg-type]
    merged["context_markdown"] += "\n\n" + _format_vector_results(vector_results)
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_context(user_input: str) -> Optional[dict]:
    """Auto-detect symbol in user input and retrieve graph context.

    KIK-420: Hybrid search — always attempts vector search when TEI + Neo4j
    are available, plus traditional symbol-based search when a symbol is detected.

    Returns:
        {
            "symbol": str,
            "context_markdown": str,
            "recommended_skill": str,
            "recommendation_reason": str,
            "relationship": str,
        }
        or None if no context available.
    """
    # KIK-420: Always attempt vector search (TEI unavailable → empty list)
    vector_results = _vector_search(user_input)

    # Market context query (no symbol needed)
    if _is_market_query(user_input):
        mc = graph_query.get_recent_market_context()
        if mc:
            market_ctx = {
                "symbol": "",
                "context_markdown": _format_market_context(mc),
                "recommended_skill": "market-research",
                "recommendation_reason": "市況照会",
                "relationship": "市況",
            }
            return _merge_context(market_ctx, vector_results) or market_ctx
        return _merge_context(None, vector_results)

    # Portfolio query (no specific symbol)
    if _is_portfolio_query(user_input):
        mc = graph_query.get_recent_market_context()
        ctx_lines = ["## ポートフォリオコンテキスト"]
        if mc:
            ctx_lines.append(f"- 直近市況: {mc.get('date', '?')}")
        ctx_lines.append("\n**推奨**: health (ポートフォリオ診断)")
        pf_ctx = {
            "symbol": "",
            "context_markdown": "\n".join(ctx_lines),
            "recommended_skill": "health",
            "recommendation_reason": "ポートフォリオ照会",
            "relationship": "PF",
        }
        return _merge_context(pf_ctx, vector_results) or pf_ctx

    # Symbol-based query
    symbol = _resolve_symbol(user_input)
    symbol_context = None

    if symbol and graph_store.is_available():
        history = graph_store.get_stock_history(symbol)
        is_bookmarked = _check_bookmarked(symbol)
        # KIK-414: HOLDS relationship for authoritative held-stock detection
        held = graph_store.is_held(symbol)
        skill, reason, relationship = _recommend_skill(history, is_bookmarked,
                                                       is_held=held)
        context_md = _format_context(symbol, history, skill, reason, relationship)
        symbol_context = {
            "symbol": symbol,
            "context_markdown": context_md,
            "recommended_skill": skill,
            "recommendation_reason": reason,
            "relationship": relationship,
        }

    # KIK-420: Merge symbol context + vector results
    return _merge_context(symbol_context, vector_results)
