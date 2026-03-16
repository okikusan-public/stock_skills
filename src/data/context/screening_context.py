"""GraphRAG context aggregator for screening output (KIK-452).

Aggregates multi-hop graph context from screening results:
  - Sector-level research summaries and catalysts (Stock→Sector→Research→Catalyst)
  - Symbol-level notes (Stock→Note)
  - Symbol-level themes (Stock→Theme, via graph_query.get_themes_for_symbols_batch)

Uses existing graph_query helpers. Graceful degradation when Neo4j unavailable.
"""


def get_screening_graph_context(
    symbols: list[str],
    sectors: list[str],
    days: int = 7,
) -> dict:
    """Aggregate knowledge graph context for a set of screened symbols.

    Parameters
    ----------
    symbols : list[str]
        Ticker symbols from the screening results.
    sectors : list[str]
        Unique sector names from the screening results.
    days : int
        Freshness window in days. Data older than this is skipped (STALE).
        Default 7 days = RECENT threshold.

    Returns
    -------
    dict with keys:
        sector_research : {sector: {summaries, catalysts_pos, catalysts_neg}}
        symbol_notes    : {symbol: [{type, content, date}]}
        symbol_themes   : {symbol: [theme_name]}
        has_data        : bool  -- True if any context was found
    """
    _empty = {
        "sector_research": {},
        "symbol_notes": {},
        "symbol_themes": {},
        "has_data": False,
    }

    try:
        from src.data.graph_query import (
            get_industry_research_for_sector,
            get_sector_catalysts,
            get_notes_for_symbols_batch,
            get_themes_for_symbols_batch,
        )
    except ImportError:
        return _empty

    result: dict = {
        "sector_research": {},
        "symbol_notes": {},
        "symbol_themes": {},
        "has_data": False,
    }

    # --- Sector-level research and catalysts ---
    for sector in sectors:
        if not sector:
            continue
        try:
            research = get_industry_research_for_sector(sector, days=days)
            catalysts = get_sector_catalysts(sector, days=days)

            summaries = [
                r.get("summary", "") for r in research if r.get("summary")
            ]
            cats_pos = catalysts.get("positive", []) if isinstance(catalysts, dict) else []
            cats_neg = catalysts.get("negative", []) if isinstance(catalysts, dict) else []

            if summaries or cats_pos or cats_neg:
                result["sector_research"][sector] = {
                    "summaries": summaries,
                    "catalysts_pos": cats_pos,
                    "catalysts_neg": cats_neg,
                }
                result["has_data"] = True
        except Exception:
            continue

    # --- Symbol-level notes (concern + thesis) ---
    if symbols:
        try:
            notes = get_notes_for_symbols_batch(
                symbols, note_types=["concern", "thesis"]
            )
            if notes:
                result["symbol_notes"] = notes
                result["has_data"] = True
        except Exception:
            pass

    # --- Symbol-level themes ---
    if symbols:
        try:
            themes = get_themes_for_symbols_batch(symbols)
            if themes:
                result["symbol_themes"] = themes
                result["has_data"] = True
        except Exception:
            pass

    # --- Symbol-level communities (KIK-549) ---
    if symbols:
        try:
            from src.data.graph_query.community import get_stock_community

            symbol_communities: dict = {}
            for sym in symbols:
                comm = get_stock_community(sym)
                if comm:
                    symbol_communities[sym] = {
                        "name": comm["name"],
                        "peers": comm.get("peers", [])[:3],
                    }
            if symbol_communities:
                result["symbol_communities"] = symbol_communities
                result["has_data"] = True
        except Exception:
            pass

    return result
