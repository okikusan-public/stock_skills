"""Portfolio/Trade/HealthCheck/Forecast graph queries.

Extracted from graph_query.py during KIK-508 submodule split.
"""

from typing import Optional

from src.data.graph_query import _common


# ---------------------------------------------------------------------------
# 13. Current portfolio holdings (KIK-414)
# ---------------------------------------------------------------------------

def get_current_holdings() -> list[dict]:
    """Get stocks currently held in portfolio via HOLDS relationship.

    Returns list of {symbol, shares, cost_price, cost_currency, purchase_date}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Portfolio {name: 'default'})-[r:HOLDS]->(s:Stock) "
                "RETURN s.symbol AS symbol, r.shares AS shares, "
                "r.cost_price AS cost_price, r.cost_currency AS cost_currency, "
                "r.purchase_date AS purchase_date "
                "ORDER BY s.symbol"
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Holdings notes — 1-hop traversal (KIK-563)
# ---------------------------------------------------------------------------

def get_holdings_notes(
    note_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Get important notes for portfolio holdings via 1-hop traversal.

    Traverses: Portfolio→HOLDS→Stock←ABOUT←Note

    Parameters
    ----------
    note_types : list[str], optional
        Filter by note types. Default: observation, concern, target.
    limit : int
        Maximum number of notes to return (default 10).

    Returns
    -------
    list[dict]
        Each dict: {symbol, type, content, date}
        Empty list if Neo4j unavailable.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    if note_types is None:
        note_types = ["observation", "concern", "target"]
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock) "
                "MATCH (n:Note)-[:ABOUT]->(s) "
                "WHERE n.type IN $types "
                "RETURN s.symbol AS symbol, n.type AS type, "
                "n.content AS content, n.date AS date "
                "ORDER BY n.date DESC LIMIT $limit",
                types=note_types,
                limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 14. Stress test history (KIK-428)
# ---------------------------------------------------------------------------

def get_stress_test_history(symbol: str | None = None, limit: int = 5) -> list[dict]:
    """Get StressTest nodes, optionally filtered by symbol.

    Returns list of {date, scenario, portfolio_impact, var_95, var_99, symbol_count}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            if symbol:
                result = session.run(
                    "MATCH (st:StressTest)-[:STRESSED]->(s:Stock {symbol: $symbol}) "
                    "RETURN st.date AS date, st.scenario AS scenario, "
                    "st.portfolio_impact AS portfolio_impact, "
                    "st.var_95 AS var_95, st.var_99 AS var_99, "
                    "st.symbol_count AS symbol_count "
                    "ORDER BY st.date DESC LIMIT $limit",
                    symbol=symbol, limit=limit,
                )
            else:
                result = session.run(
                    "MATCH (st:StressTest) "
                    "RETURN st.date AS date, st.scenario AS scenario, "
                    "st.portfolio_impact AS portfolio_impact, "
                    "st.var_95 AS var_95, st.var_99 AS var_99, "
                    "st.symbol_count AS symbol_count "
                    "ORDER BY st.date DESC LIMIT $limit",
                    limit=limit,
                )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 15. Forecast history (KIK-428)
# ---------------------------------------------------------------------------

def get_forecast_history(symbol: str | None = None, limit: int = 5) -> list[dict]:
    """Get Forecast nodes, optionally filtered by symbol.

    Returns list of {date, optimistic, base, pessimistic, total_value_jpy, symbol_count}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            if symbol:
                result = session.run(
                    "MATCH (f:Forecast)-[:FORECASTED]->(s:Stock {symbol: $symbol}) "
                    "RETURN f.date AS date, f.optimistic AS optimistic, "
                    "f.base AS base, f.pessimistic AS pessimistic, "
                    "f.total_value_jpy AS total_value_jpy, "
                    "f.symbol_count AS symbol_count "
                    "ORDER BY f.date DESC LIMIT $limit",
                    symbol=symbol, limit=limit,
                )
            else:
                result = session.run(
                    "MATCH (f:Forecast) "
                    "RETURN f.date AS date, f.optimistic AS optimistic, "
                    "f.base AS base, f.pessimistic AS pessimistic, "
                    "f.total_value_jpy AS total_value_jpy, "
                    "f.symbol_count AS symbol_count "
                    "ORDER BY f.date DESC LIMIT $limit",
                    limit=limit,
                )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# KIK-434: Portfolio holdings for AI graph linking
# ---------------------------------------------------------------------------

def get_portfolio_holdings_for_linking(limit: int = 8) -> list[dict]:
    """Return portfolio holdings enriched with their latest Report for AI linking.

    Returns list of dicts: {id, type, symbol, sector, score, verdict, summary}
    Empty list when Neo4j is unavailable or no holdings found.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock) "
                "OPTIONAL MATCH (r:Report)-[:ANALYZED]->(s) "
                "WITH s, r ORDER BY r.date DESC "
                "WITH s, collect(r)[0] AS rep "
                "RETURN "
                "  coalesce(rep.id, 'stock_' + s.symbol) AS id, "
                "  'Report' AS type, "
                "  s.symbol AS symbol, "
                "  coalesce(s.sector, '') AS sector, "
                "  coalesce(rep.score, 0) AS score, "
                "  coalesce(rep.verdict, '') AS verdict, "
                "  ('保有: ' + s.symbol + ' score=' + toString(coalesce(rep.score, 0))) AS summary "
                "LIMIT $limit",
                limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 16. Vector similarity search (KIK-420)
# ---------------------------------------------------------------------------

_VECTOR_LABELS = [
    "Screen", "Report", "Trade", "Research",
    "HealthCheck", "MarketContext", "Note", "Watchlist",
    "StressTest", "Forecast",
]


def vector_search(
    query_embedding: list[float],
    top_k: int = 5,
    node_labels: list[str] | None = None,
) -> list[dict]:
    """Cross-type vector similarity search across Neo4j nodes.

    Queries each node type's vector index and merges results by score.

    Parameters
    ----------
    query_embedding : list[float]
        384-dim embedding vector from TEI.
    top_k : int
        Max results to return (default 5).
    node_labels : list[str] | None
        Node labels to search. None means all 7 embeddable types.

    Returns
    -------
    list[dict]
        [{label, summary, score, date, id, symbol?}] sorted by score desc.
        Empty list if Neo4j unavailable.
    """
    driver = _common._get_driver()
    if driver is None:
        return []

    labels = node_labels or _VECTOR_LABELS
    results: list[dict] = []

    for label in labels:
        index_name = f"{label.lower()}_embedding"
        try:
            with driver.session() as session:
                records = session.run(
                    "CALL db.index.vector.queryNodes($index, $k, $emb) "
                    "YIELD node, score "
                    "RETURN node.semantic_summary AS summary, "
                    "node.date AS date, node.id AS id, "
                    "node.symbol AS symbol, score",
                    index=index_name, k=top_k, emb=query_embedding,
                )
                for r in records:
                    results.append({
                        "label": label,
                        "summary": r["summary"],
                        "date": r["date"],
                        "id": r["id"],
                        "symbol": r.get("symbol"),
                        "score": r["score"],
                    })
        except Exception:
            continue  # index not yet created or label has no embeddings

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
