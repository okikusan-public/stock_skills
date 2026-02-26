"""Compact knowledge context extraction for Grok API prompt injection (KIK-488).

Extracts a token-budget-limited summary from Neo4j knowledge graph
for injection into Grok API prompts. Designed to be 200-300 tokens max.

Graceful degradation: returns "" when Neo4j is unavailable.
"""

from __future__ import annotations


def _truncate_context(text: str, max_tokens: int = 300) -> str:
    """Truncate context to approximate token budget.

    Uses a rough heuristic: ~3 chars/token for mixed JP/EN text.
    Truncates at line boundaries to avoid mid-sentence cuts.
    """
    if not text:
        return ""
    max_chars = max_tokens * 3
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    result: list[str] = []
    total = 0
    for line in lines:
        if total + len(line) > max_chars:
            break
        result.append(line)
        total += len(line) + 1  # +1 for newline
    return "\n".join(result)


def get_stock_context(symbol: str) -> str:
    """Extract compact context for a specific stock symbol.

    Priority order:
    - High: holding status, prior report numbers, thesis, concern
    - Medium: screening appearances, research history, health check
    - Low: themes

    Returns compact context string (200-300 tokens) or "" if unavailable.
    """
    try:
        from src.data import graph_store

        if not graph_store.is_available():
            return ""

        history = graph_store.get_stock_history(symbol)
        if not history:
            return ""

        is_held = graph_store.is_held(symbol)

        lines: list[str] = ["[INVESTOR CONTEXT]"]

        # 1. Holding status (High)
        if is_held:
            buys = [t for t in history.get("trades", []) if t.get("type") == "buy"]
            if buys:
                t = buys[0]
                lines.append(
                    f"- Status: Currently held "
                    f"(bought {t.get('date', '?')}, "
                    f"{t.get('shares', '?')} shares @ {t.get('price', '?')})"
                )
            else:
                lines.append("- Status: Currently held")
        else:
            sells = [t for t in history.get("trades", []) if t.get("type") == "sell"]
            if sells:
                lines.append(
                    f"- Status: Previously held, sold {sells[0].get('date', '?')}"
                )

        # 2. Prior report (High)
        reports = history.get("reports", [])
        if reports:
            r = reports[0]
            parts: list[str] = []
            if r.get("score"):
                parts.append(f"Score {r['score']}")
            if r.get("verdict"):
                parts.append(f'verdict "{r["verdict"]}"')
            if parts:
                lines.append(
                    f"- Prior report ({r.get('date', '?')}): {', '.join(parts)}"
                )

        # 3. Thesis / Concern notes (High) — max 2 notes total
        note_count = 0
        for n in history.get("notes", []):
            if note_count >= 2:
                break
            ntype = n.get("type", "")
            content = (n.get("content", "") or "")[:80]
            if not content:
                continue
            if ntype == "thesis":
                lines.append(f'- Thesis: "{content}"')
                note_count += 1
            elif ntype == "concern":
                lines.append(f'- Concern: "{content}"')
                note_count += 1

        # 4. Screening appearances (Medium)
        screens = history.get("screens", [])
        if screens:
            presets = list(
                dict.fromkeys(s.get("preset", "") for s in screens if s.get("preset"))
            )[:3]
            lines.append(
                f"- Screening: Appeared {len(screens)} times"
                + (f" ({', '.join(presets)})" if presets else "")
            )

        # 5. Research history (Medium)
        researches = history.get("researches", [])
        if researches:
            r = researches[0]
            summary = (r.get("summary", "") or "")[:60]
            if summary:
                lines.append(f"- Last research ({r.get('date', '?')}): {summary}")

        # 6. Health check (Medium)
        hcs = history.get("health_checks", [])
        if hcs:
            lines.append(f"- Last health check: {hcs[0].get('date', '?')}")

        # 7. Themes (Low)
        themes = history.get("themes", [])
        if themes:
            lines.append(f"- Themes: {', '.join(themes[:3])}")

        if len(lines) <= 1:
            return ""

        lines.append(
            "Focus your research on changes since the above context. "
            "Flag any information that contradicts or supports "
            "the investor's thesis/concerns."
        )

        return _truncate_context("\n".join(lines))
    except Exception:
        return ""


def get_industry_context(industry_or_theme: str) -> str:
    """Extract compact context for industry/theme research.

    Includes held stocks in matching sectors and prior industry research.
    Returns compact context string or "" if unavailable.
    """
    try:
        from src.data import graph_store

        if not graph_store.is_available():
            return ""

        lines: list[str] = ["[INVESTOR CONTEXT]"]

        # 1. Held stocks in this sector/theme
        driver = graph_store._get_driver()
        if driver:
            with driver.session() as session:
                result = session.run(
                    "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock) "
                    "WHERE toLower(s.sector) CONTAINS toLower($theme) "
                    "OR toLower(s.name) CONTAINS toLower($theme) "
                    "RETURN s.symbol AS symbol LIMIT 5",
                    theme=industry_or_theme,
                )
                held_symbols = [r["symbol"] for r in result if r.get("symbol")]
                if held_symbols:
                    lines.append(
                        f"- Investor holds stocks in this sector: "
                        f"{', '.join(held_symbols)}"
                    )

        # 2. Prior industry research
        try:
            from src.data.graph_query import get_research_chain

            chain = get_research_chain("industry", industry_or_theme, limit=1)
            if chain:
                r = chain[0]
                summary = (r.get("summary", "") or "")[:80]
                if summary:
                    lines.append(
                        f"- Prior research ({r.get('date', '?')}): {summary}"
                    )
        except (ImportError, Exception):
            pass

        if len(lines) <= 1:
            return ""

        lines.append(
            "Focus on developments since the investor's last research. "
            "Highlight impacts on their held stocks if applicable."
        )

        return _truncate_context("\n".join(lines))
    except Exception:
        return ""


def get_market_context() -> str:
    """Extract compact context for market research.

    Includes held sectors and recent market context.
    Returns compact context string or "" if unavailable.
    """
    try:
        from src.data import graph_store

        if not graph_store.is_available():
            return ""

        lines: list[str] = ["[INVESTOR CONTEXT]"]

        # 1. Held sectors
        driver = graph_store._get_driver()
        if driver:
            with driver.session() as session:
                result = session.run(
                    "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock) "
                    "WHERE s.sector IS NOT NULL AND s.sector <> '' "
                    "RETURN s.sector AS sector, count(*) AS cnt "
                    "ORDER BY cnt DESC LIMIT 5"
                )
                sectors = [
                    f"{r['sector']}({r['cnt']})" for r in result
                    if r.get("sector")
                ]
                if sectors:
                    lines.append(
                        f"- Investor's portfolio sectors: {', '.join(sectors)}"
                    )

        # 2. Recent market context date
        try:
            from src.data.graph_query import get_recent_market_context

            mc = get_recent_market_context()
            if mc and mc.get("date"):
                lines.append(f"- Last market context recorded: {mc['date']}")
        except (ImportError, Exception):
            pass

        if len(lines) <= 1:
            return ""

        lines.append(
            "Focus on how current market conditions affect "
            "the investor's portfolio sectors listed above."
        )

        return _truncate_context("\n".join(lines))
    except Exception:
        return ""


def get_business_context(symbol: str) -> str:
    """Extract compact context for business model analysis.

    Reuses stock context but focuses on sector, themes, and prior research.
    Returns compact context string or "" if unavailable.
    """
    try:
        from src.data import graph_store

        if not graph_store.is_available():
            return ""

        history = graph_store.get_stock_history(symbol)
        if not history:
            return ""

        is_held = graph_store.is_held(symbol)

        lines: list[str] = ["[INVESTOR CONTEXT]"]

        if is_held:
            lines.append("- Status: Currently held by investor")

        # Prior research summary (business-focused)
        researches = history.get("researches", [])
        for r in researches[:2]:
            summary = (r.get("summary", "") or "")[:80]
            rtype = r.get("research_type", "")
            if summary:
                lines.append(
                    f"- Prior {rtype} research ({r.get('date', '?')}): {summary}"
                )

        # Themes
        themes = history.get("themes", [])
        if themes:
            lines.append(f"- Themes: {', '.join(themes[:3])}")

        # Thesis
        for n in history.get("notes", []):
            if n.get("type") == "thesis":
                content = (n.get("content", "") or "")[:80]
                if content:
                    lines.append(f'- Investment thesis: "{content}"')
                    break

        if len(lines) <= 1:
            return ""

        lines.append(
            "Focus on how the business model supports or contradicts "
            "the investor's thesis above."
        )

        return _truncate_context("\n".join(lines))
    except Exception:
        return ""
