"""Auto graph context injection for user prompts (KIK-411/420/427).

Detects ticker symbols in user input, queries Neo4j for past knowledge,
and recommends the optimal skill based on graph state.
KIK-420: Hybrid search — vector similarity + symbol-based retrieval.
KIK-427: Freshness labels (FRESH/RECENT/STALE) with env-configurable thresholds.
KIK-577: Split into sub-modules (freshness, skill_recommender, vector_search,
         context_formatter). This file is now a thin orchestrator.
Returns None when no context available or Neo4j unavailable (graceful degradation).
"""

import re
from typing import Optional

from src.data.ticker_utils import extract_symbol
from src.data import graph_store, graph_query
from src.data import note_manager

# ---------------------------------------------------------------------------
# Sub-module imports (KIK-577)
# ---------------------------------------------------------------------------
from src.data.context.freshness import (  # noqa: F401
    _fresh_hours,
    _recent_hours,
    _days_since,
    _hours_since,
    freshness_label,
    freshness_action,
    _action_directive,
    _best_freshness,
)
from src.data.context.skill_recommender import (  # noqa: F401
    _has_bought_not_sold,
    _screening_count,
    _has_recent_research,
    _has_exit_alert,
    _thesis_needs_review,
    _has_concern_notes,
    _recommend_skill,
)
from src.data.context.skill_recommender import (
    _check_bookmarked as _check_bookmarked_impl,
)
from src.data.context.vector_search import (
    _vector_search as _vector_search_impl,
)
from src.data.context.vector_search import (  # noqa: F401
    _format_vector_results,
    _infer_skill_from_vectors,
    _merge_context,
)
from src.data.context.context_formatter import (  # noqa: F401
    _format_context,
    _format_market_context,
)


def _check_bookmarked(symbol: str) -> bool:
    """Check if symbol is in any watchlist via Neo4j.

    Wraps skill_recommender._check_bookmarked with this module's graph_store
    reference so that ``@patch("src.data.context.auto_context.graph_store")`` works.
    """
    return _check_bookmarked_impl(symbol, _graph_store=graph_store)


def _vector_search(user_input: str) -> list[dict]:
    """Embed user input via TEI and run vector similarity search on Neo4j.

    Wraps vector_search._vector_search with this module's graph_query
    reference so that ``@patch("src.data.context.auto_context.graph_query")`` works.
    """
    return _vector_search_impl(user_input, _graph_query=graph_query)

# Backward-compatible alias (tests import _extract_symbol from this module)
_extract_symbol = extract_symbol


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
# Placeholder (kept for backward compatibility)
# ---------------------------------------------------------------------------

def _is_bookmarked(history: dict) -> bool:
    """Check if the symbol appears in any watchlist (via graph_query)."""
    return False  # Placeholder - checked via separate query


# ---------------------------------------------------------------------------
# Investment lesson context (KIK-534)
# ---------------------------------------------------------------------------

def _append_lessons(
    result: dict | None,
    symbol: Optional[str] = None,
    user_input: str = "",
) -> dict | None:
    """Append investment lesson section to context result (KIK-534/554/569).

    KIK-569: Selects lessons relevant to user_input, and includes
    community-based lessons for related stocks.
    """
    if result is None:
        return None
    try:
        lessons = _load_lessons(symbol=symbol)

        # KIK-569: Community-based related lessons
        community_lessons = _load_community_lessons(symbol) if symbol else []

        # KIK-571: Theme-based lessons from LessonCommunity
        theme_lessons = _load_theme_lessons(user_input)

        # KIK-569: Select relevant lessons based on user input
        all_lessons = lessons + community_lessons + theme_lessons
        # Deduplicate by id
        seen_ids: set = set()
        unique_lessons = []
        for les in all_lessons:
            lid = les.get("id", "")
            if lid and lid in seen_ids:
                continue
            if lid:
                seen_ids.add(lid)
            unique_lessons.append(les)
        all_lessons = unique_lessons

        if user_input and all_lessons:
            all_lessons = _select_relevant_lessons(all_lessons, user_input)

        lesson_md = _format_lesson_section(all_lessons)
        if lesson_md:
            result["context_markdown"] += lesson_md
    except Exception:
        pass  # graceful degradation
    return result


def _load_lessons(symbol: Optional[str] = None) -> list[dict]:
    """Load type=lesson notes from JSON files (graceful degradation).

    Falls back to reading data/notes/ directly when Neo4j is unavailable.
    """
    try:
        return note_manager.load_notes(note_type="lesson", symbol=symbol)
    except Exception:
        return []


def _load_theme_lessons(user_input: str) -> list[dict]:
    """Load lessons from matching LessonCommunity based on user intent (KIK-571)."""
    try:
        from src.data.lesson_community import infer_theme_from_input, get_lessons_by_theme
        theme = infer_theme_from_input(user_input)
        if theme:
            return get_lessons_by_theme(theme, limit=3)
    except Exception:
        pass
    return []


def _load_community_lessons(symbol: str) -> list[dict]:
    """Load lessons from community peer stocks via Neo4j (KIK-569).

    Traverses: Stock->BELONGS_TO->Community<-BELONGS_TO<-Stock<-ABOUT<-Note(lesson)
    """
    try:
        from src.data.graph_query.community import get_community_lessons
        return get_community_lessons(symbol)
    except Exception:
        return []


def _select_relevant_lessons(
    lessons: list[dict],
    user_input: str,
    max_results: int = 5,
) -> list[dict]:
    """Select lessons most relevant to user input (KIK-569).

    Uses keyword overlap scoring on trigger + expected_action.
    Falls back to TEI embedding similarity if available.
    """
    if not lessons or not user_input:
        return lessons[:max_results]

    try:
        from src.data.note_manager import _keyword_similarity
    except ImportError:
        return lessons[:max_results]

    input_lower = user_input.lower()

    scored = []
    for les in lessons:
        trigger = (les.get("trigger") or "").strip()
        expected = (les.get("expected_action") or "").strip()
        symbol = (les.get("symbol") or "").strip()
        content = (les.get("content") or "")[:80].strip()
        les_text = f"{trigger} {expected} {symbol} {content}".strip()

        # Keyword similarity (works for space-separated languages)
        score = _keyword_similarity(input_lower, les_text.lower())

        # Bonus: symbol appears in user input
        if symbol and symbol.lower() in input_lower:
            score += 0.3

        # Bonus: substring matching (handles Japanese without spaces)
        if trigger:
            trigger_lower = trigger.lower()
            # Check if any 2+ char substring from trigger appears in input
            for word in trigger_lower.split():
                if len(word) >= 2 and word in input_lower:
                    score += 0.2
                    break
            # Character n-gram overlap for non-space languages
            if score < 0.1:
                common = sum(1 for c in set(trigger_lower) if c in input_lower and c.strip())
                total = len(set(trigger_lower) | set(input_lower))
                if total > 0:
                    score += (common / total) * 0.3

        scored.append((score, les))

    # Sort by relevance, then by date for ties
    scored.sort(key=lambda x: (x[0], x[1].get("date", "")), reverse=True)
    return [les for _, les in scored[:max_results]]


def _format_lesson_section(lessons: list[dict]) -> str:
    """Format investment lessons as a markdown section for context injection.

    KIK-564: Detects potential contradictions between lessons and annotates.
    """
    if not lessons:
        return ""

    # KIK-564/570: Pre-compute conflict pairs using unified engine
    conflict_map = _find_lesson_conflict_pairs(lessons)

    lines = ["", "## 投資lesson"]
    for les in lessons[:5]:
        symbol_part = f"[{les.get('symbol')}] " if les.get("symbol") else ""
        trigger = les.get("trigger", "")
        expected = les.get("expected_action", "")
        content = (les.get("content", "") or "")[:80]

        # KIK-570: Conflict annotation with detail
        conflict_mark = ""
        les_id = les.get("id", "")
        detail = conflict_map.get(les_id, "")
        if detail:
            conflict_mark = f"⚠️矛盾候補({detail}) "

        if trigger and expected:
            lines.append(f"- {conflict_mark}{symbol_part}{trigger} → {expected}")
        elif trigger:
            lines.append(f"- {conflict_mark}{symbol_part}トリガー: {trigger} / {content}")
        elif expected:
            lines.append(f"- {conflict_mark}{symbol_part}次回: {expected} / {content}")
        else:
            lines.append(f"- {conflict_mark}{symbol_part}{content}")
        date_str = les.get("date", "")
        if date_str:
            lines[-1] += f" ({date_str})"

    if conflict_map:
        lines.append("")
        lines.append("⚠️ 矛盾候補のlessonがあります。統合・更新を検討してください。")

    return "\n".join(lines)


def _find_lesson_conflict_pairs(lessons: list[dict]) -> dict[str, str]:
    """Find lesson IDs with contradictions using unified engine (KIK-570).

    Returns {lesson_id: conflict_detail} for annotated display.
    """
    if len(lessons) < 2:
        return {}
    try:
        from src.data.lesson_conflict import find_conflict_pairs
        return find_conflict_pairs(lessons)
    except ImportError:
        return {}


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
    # KIK-420: Always attempt vector search (TEI unavailable -> empty list)
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
            result = _merge_context(market_ctx, vector_results) or market_ctx
        else:
            result = _merge_context(None, vector_results)
        return _append_lessons(result, user_input=user_input)

    # Portfolio query (no specific symbol)
    if _is_portfolio_query(user_input):
        mc = graph_query.get_recent_market_context()
        ctx_lines = ["## ポートフォリオコンテキスト"]
        if mc:
            ctx_lines.append(f"- 直近市況: {mc.get('date', '?')}")

        # KIK-563: 1-hop traversal for holdings notes
        try:
            from src.data.graph_query.portfolio import get_holdings_notes
            notes = get_holdings_notes()
            if notes:
                ctx_lines.append("")
                ctx_lines.append("## 保有銘柄の重要メモ")
                for n in notes:
                    sym = n.get("symbol", "?")
                    ntype = n.get("type", "?")
                    content = (n.get("content", "") or "")[:60]
                    ndate = n.get("date", "")
                    date_part = f" ({ndate})" if ndate else ""
                    ctx_lines.append(f"- [{sym}] {ntype}: {content}{date_part}")
        except Exception:
            pass  # graceful degradation

        ctx_lines.append("\n**推奨**: health (ポートフォリオ診断)")
        pf_ctx = {
            "symbol": "",
            "context_markdown": "\n".join(ctx_lines),
            "recommended_skill": "health",
            "recommendation_reason": "ポートフォリオ照会",
            "relationship": "PF",
        }
        result = _merge_context(pf_ctx, vector_results) or pf_ctx
        return _append_lessons(result, user_input=user_input)

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
    merged = _merge_context(symbol_context, vector_results)

    # KIK-534: Append investment lesson section
    return _append_lessons(merged, symbol=symbol, user_input=user_input)
