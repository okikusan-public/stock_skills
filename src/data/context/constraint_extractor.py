"""Constraint extraction from investment lessons for plan-check flow (KIK-596).

Extracts action type from user query, loads relevant lessons,
and structures them as constraints for the multi-agent planning system.

Usage:
    from src.data.context.constraint_extractor import extract_constraints
    result = extract_constraints("7751.Tを売って代わりを探して")
    # => {"action_type": "swap_proposal", "symbols": ["7751.T"], "constraints": [...]}
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Action type classification
# ---------------------------------------------------------------------------

_ACTION_PATTERNS: dict[str, list[str]] = {
    "swap_proposal": [
        "入替", "入れ替え", "乗り換え", "スワップ", "代わり", "代替",
        "リプレイス", "swap", "replace",
    ],
    "new_buy": [
        "買いたい", "購入したい", "エントリー", "追加したい", "検討中",
        "買おうか", "買い増し",
    ],
    "sell": [
        "売りたい", "売却", "損切り", "利確", "手放", "ポジション解消",
        "利益確定",
    ],
    "rebalance": [
        "リバランス", "配分調整", "バランス改善", "偏り直し",
    ],
    "adjust": [
        "調整", "アドバイス", "処方箋", "直して", "改善して",
        "対策", "どうしたらいい", "どうすべき",
    ],
}

# Additional search keywords per action type to boost lesson matching
_ACTION_BOOST_KEYWORDS: dict[str, list[str]] = {
    "swap_proposal": [
        "入替", "通貨配分", "地域分散", "単元株", "what-if",
        "セクター", "穴埋め",
    ],
    "new_buy": [
        "エントリー", "カタリスト", "バリュエーション", "確信",
        "conviction", "タイミング",
    ],
    "sell": [
        "損切り", "閾値", "カタリスト", "テーゼ", "EXIT",
    ],
    "rebalance": [
        "配分", "HHI", "集中", "分散", "偏り",
    ],
    "adjust": [
        "ヘルスチェック", "警告", "EXIT", "改善", "弱点",
    ],
}


def classify_action_type(user_query: str) -> str:
    """Classify user query into an action type.

    Returns one of: swap_proposal, new_buy, sell, rebalance, adjust.
    Falls back to "adjust" if no pattern matches.
    """
    query_lower = user_query.lower()
    scores: dict[str, int] = {k: 0 for k in _ACTION_PATTERNS}

    for action_type, keywords in _ACTION_PATTERNS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                scores[action_type] += 1

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] == 0:
        return "adjust"
    return best


# ---------------------------------------------------------------------------
# Constraint extraction
# ---------------------------------------------------------------------------


def extract_constraints(
    user_query: str,
    max_constraints: int = 5,
) -> dict:
    """Extract constraints from investment lessons for the given user query.

    Returns a dict with:
        action_type: str
        symbols: list[str]
        constraints: list[dict]  -- each has id, trigger, expected_action,
                                    source, community, relevance_score
        lesson_count: int
        matched_count: int
    """
    action_type = classify_action_type(user_query)
    symbols = _extract_symbols(user_query)

    # Load all lessons
    lessons = _load_lessons()
    lesson_count = len(lessons)

    # Build enriched query with action-type boost keywords
    enriched_query = _build_enriched_query(user_query, action_type)

    # Score and select relevant lessons
    relevant = _select_lessons(lessons, enriched_query, max_constraints)

    # Convert to constraint format
    constraints = [
        _lesson_to_constraint(les, score)
        for score, les in relevant
    ]

    # Auto-inject lot size constraints for detected symbols
    lot_constraints = _build_lot_size_constraints(symbols)
    constraints = lot_constraints + constraints

    return {
        "action_type": action_type,
        "symbols": symbols,
        "constraints": constraints,
        "lesson_count": lesson_count,
        "matched_count": len(constraints),
    }


def format_constraints_markdown(result: dict) -> str:
    """Format constraint extraction result as markdown."""
    lines = [
        f"## 制約条件 ({result['action_type']})",
        "",
    ]
    if result["symbols"]:
        lines.append(f"対象シンボル: {', '.join(result['symbols'])}")
        lines.append("")

    if not result["constraints"]:
        lines.append("該当するlessonはありません。")
        return "\n".join(lines)

    for i, c in enumerate(result["constraints"], 1):
        lines.append(
            f"### 制約{i}: {c['source']} ({c['community']}, "
            f"関連度{c['relevance_score']:.2f})"
        )
        lines.append(f"- **trigger**: {c['trigger']}")
        lines.append(f"- **expected_action**: {c['expected_action']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_lot_size_constraints(symbols: list[str]) -> list[dict]:
    """Auto-generate lot size constraints for detected symbols.

    Injects structural knowledge about trading unit requirements
    so the system never proposes impossible trades (e.g., 50 shares of JP stock).
    """
    try:
        from src.data.ticker_utils import get_lot_size, infer_currency
    except ImportError:
        return []

    constraints = []
    for sym in symbols:
        lot = get_lot_size(sym)
        if lot <= 1:
            continue  # US/UK stocks: 1 share, no constraint needed
        currency = infer_currency(sym)
        constraints.append({
            "id": f"system_lot_size_{sym}",
            "trigger": f"{sym}の売買提案時",
            "expected_action": (
                f"{sym}は{lot}株単位でしか売買できない。"
                f"一部売却（{lot}株未満）は不可能。"
                f"購入時は{lot}株×株価({currency})が予算内か確認すること"
            ),
            "source": f"【システム制約】{sym}の売買単位={lot}株",
            "community": "システム制約",
            "relevance_score": 1.0,  # Always highest priority
        })
    return constraints


def _extract_symbols(user_query: str) -> list[str]:
    """Extract ticker symbols from user query."""
    try:
        from src.data.ticker_utils import extract_all_symbols
        return extract_all_symbols(user_query)
    except ImportError:
        return []


def _load_lessons() -> list[dict]:
    """Load all lesson-type notes."""
    try:
        from src.data.note_manager import load_notes
        return load_notes(note_type="lesson")
    except ImportError:
        return []


def _build_enriched_query(user_query: str, action_type: str) -> str:
    """Enrich user query with action-type specific keywords for better matching."""
    boost = _ACTION_BOOST_KEYWORDS.get(action_type, [])
    return f"{user_query} {' '.join(boost)}"


def _select_lessons(
    lessons: list[dict],
    enriched_query: str,
    max_results: int,
) -> list[tuple[float, dict]]:
    """Score and select relevant lessons using existing scoring logic.

    Returns list of (score, lesson) tuples sorted by relevance.
    """
    try:
        from src.data.lesson_conflict import keyword_similarity
    except ImportError:
        return [(0.0, les) for les in lessons[:max_results]]

    query_lower = enriched_query.lower()
    scored: list[tuple[float, dict]] = []

    for les in lessons:
        trigger = _get_trigger(les)
        expected = _get_action(les)
        symbol = (les.get("symbol") or "").strip()
        content = (les.get("content") or "")[:80].strip()
        les_text = f"{trigger} {expected} {symbol} {content}".strip()

        # Base keyword similarity (public API from lesson_conflict)
        score = keyword_similarity(query_lower, les_text.lower())

        # Bonus: symbol appears in query
        if symbol and symbol.lower() in query_lower:
            score += 0.3

        # Bonus: trigger substring match
        if trigger:
            trigger_lower = trigger.lower()
            for word in trigger_lower.split():
                if len(word) >= 2 and word in query_lower:
                    score += 0.2
                    break
            # CJK character overlap (only for low-score rescue when
            # keyword/word match didn't fire, to catch partial CJK matches)
            if score < 0.1:
                common = sum(
                    1 for c in set(trigger_lower)
                    if c in query_lower and c not in " \t\n"
                )
                total = len(set(trigger_lower) | set(query_lower))
                if total > 0:
                    score += (common / total) * 0.3

        if score > 0:
            scored.append((score, les))

    scored.sort(key=lambda x: (x[0], x[1].get("date", "")), reverse=True)
    return scored[:max_results]


def _get_trigger(lesson: dict) -> str:
    """Extract trigger from lesson, with content fallback."""
    try:
        from src.data.lesson_conflict import extract_trigger
        return extract_trigger(lesson)
    except ImportError:
        return (lesson.get("trigger") or "").strip()


def _get_action(lesson: dict) -> str:
    """Extract expected_action from lesson, with content fallback."""
    try:
        from src.data.lesson_conflict import extract_action
        return extract_action(lesson)
    except ImportError:
        return (lesson.get("expected_action") or "").strip()


def _classify_community(lesson: dict) -> str:
    """Classify lesson into a community category."""
    try:
        from src.data.lesson_community import classify_lesson
        content = lesson.get("content", "")
        trigger = _get_trigger(lesson)
        return classify_lesson(content, trigger)
    except ImportError:
        return "その他"


def _lesson_to_constraint(lesson: dict, relevance_score: float) -> dict:
    """Convert a lesson to a constraint dict."""
    trigger = _get_trigger(lesson)
    expected_action = _get_action(lesson)
    content = (lesson.get("content") or "").strip()
    # Extract first line or first 60 chars as source label
    first_line = content.split("\n")[0][:60] if content else ""
    source = first_line or lesson.get("id", "unknown")

    return {
        "id": lesson.get("id", ""),
        "trigger": trigger,
        "expected_action": expected_action,
        "source": source,
        "community": _classify_community(lesson),
        "relevance_score": round(relevance_score, 2),
    }
