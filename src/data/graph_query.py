"""Graph query helpers for enriching skill output (KIK-406/413/420).

All functions return empty/None when Neo4j is unavailable (graceful degradation).
KIK-413 additions: semantic sub-node queries (news, sentiment, catalysts, report trend, events).
KIK-420 additions: vector_search() for semantic similarity across all node types.
"""

import json
from typing import Optional


def _get_driver():
    """Reuse graph_store's driver."""
    from src.data.graph_store import _get_driver as _gs_driver
    return _gs_driver()


# ---------------------------------------------------------------------------
# 1. Prior report lookup
# ---------------------------------------------------------------------------

def get_prior_report(symbol: str) -> Optional[dict]:
    """Get the most recent Report for a symbol.

    Returns dict with keys: date, score, verdict. None if not found.
    """
    driver = _get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Report)-[:ANALYZED]->(s:Stock {symbol: $symbol}) "
                "RETURN r.date AS date, r.score AS score, r.verdict AS verdict "
                "ORDER BY r.date DESC LIMIT 1",
                symbol=symbol,
            )
            record = result.single()
            if record is None:
                return None
            return dict(record)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 2. Screening frequency
# ---------------------------------------------------------------------------

def get_screening_frequency(symbols: list[str]) -> dict[str, int]:
    """Count how many times each symbol appeared in past Screen results.

    Returns {symbol: count} for symbols with count >= 1.
    """
    driver = _get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (sc:Screen)-[:SURFACED]->(s:Stock) "
                "WHERE s.symbol IN $symbols "
                "RETURN s.symbol AS symbol, count(sc) AS cnt",
                symbols=symbols,
            )
            return {r["symbol"]: r["cnt"] for r in result if r["cnt"] >= 1}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 3. Research chain (SUPERSEDES)
# ---------------------------------------------------------------------------

def get_research_chain(
    research_type: str, target: str, limit: int = 5,
) -> list[dict]:
    """Get the SUPERSEDES chain for a research type+target, newest first.

    Returns list of {date, summary}.
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research {research_type: $rtype, target: $target}) "
                "RETURN r.date AS date, r.summary AS summary "
                "ORDER BY r.date DESC LIMIT $limit",
                rtype=research_type, target=target, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 4. Recent market context
# ---------------------------------------------------------------------------

def get_recent_market_context() -> Optional[dict]:
    """Get the most recent MarketContext node.

    Returns dict with keys: date, indices (parsed from JSON).
    None if not found.
    """
    driver = _get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (m:MarketContext) "
                "RETURN m.date AS date, m.indices AS indices "
                "ORDER BY m.date DESC LIMIT 1",
            )
            record = result.single()
            if record is None:
                return None
            indices_raw = record["indices"]
            try:
                indices = json.loads(indices_raw) if indices_raw else []
            except (json.JSONDecodeError, TypeError):
                indices = []
            return {"date": record["date"], "indices": indices}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 5. Trade context (trades + notes for a symbol)
# ---------------------------------------------------------------------------

def get_trade_context(symbol: str) -> dict:
    """Get trade history and notes for a symbol.

    Returns {trades: [{date, type, shares, price}], notes: [{date, type, content}]}.
    """
    empty = {"trades": [], "notes": []}
    driver = _get_driver()
    if driver is None:
        return empty
    try:
        with driver.session() as session:
            trades = session.run(
                "MATCH (t:Trade)-[:BOUGHT|SOLD]->(s:Stock {symbol: $symbol}) "
                "RETURN t.date AS date, t.type AS type, "
                "t.shares AS shares, t.price AS price "
                "ORDER BY t.date DESC",
                symbol=symbol,
            )
            notes = session.run(
                "MATCH (n:Note)-[:ABOUT]->(s:Stock {symbol: $symbol}) "
                "RETURN n.date AS date, n.type AS type, n.content AS content "
                "ORDER BY n.date DESC",
                symbol=symbol,
            )
            return {
                "trades": [dict(r) for r in trades],
                "notes": [dict(r) for r in notes],
            }
    except Exception:
        return empty


# ---------------------------------------------------------------------------
# 6. Recurring picks (frequently screened but not bought)
# ---------------------------------------------------------------------------

def get_recurring_picks(min_count: int = 2) -> list[dict]:
    """Find stocks that appear in multiple screens but have no BOUGHT trade.

    Returns list of {symbol, count, last_date}.
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (sc:Screen)-[:SURFACED]->(s:Stock) "
                "WHERE NOT exists { MATCH (:Trade)-[:BOUGHT]->(s) } "
                "WITH s.symbol AS symbol, count(sc) AS cnt, "
                "max(sc.date) AS last_date "
                "WHERE cnt >= $min_count "
                "RETURN symbol, cnt AS count, last_date "
                "ORDER BY cnt DESC, last_date DESC",
                min_count=min_count,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 7. Stock news history (KIK-413)
# ---------------------------------------------------------------------------

def get_stock_news_history(symbol: str, limit: int = 10) -> list[dict]:
    """Get News nodes linked to a stock via News→MENTIONS→Stock.

    Returns list of {date, title, source}.
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (n:News)-[:MENTIONS]->(s:Stock {symbol: $symbol}) "
                "RETURN n.date AS date, n.title AS title, n.source AS source "
                "ORDER BY n.date DESC LIMIT $limit",
                symbol=symbol, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 8. Sentiment trend (KIK-413)
# ---------------------------------------------------------------------------

def get_sentiment_trend(symbol: str, limit: int = 5) -> list[dict]:
    """Get Sentiment nodes linked via Research→HAS_SENTIMENT for a stock.

    Returns list of {date, source, score, summary}.
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research)-[:RESEARCHED]->(s:Stock {symbol: $symbol}) "
                "MATCH (r)-[:HAS_SENTIMENT]->(sent:Sentiment) "
                "RETURN sent.date AS date, sent.source AS source, "
                "sent.score AS score, sent.summary AS summary "
                "ORDER BY sent.date DESC LIMIT $limit",
                symbol=symbol, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 9. Catalysts (KIK-413)
# ---------------------------------------------------------------------------

def get_catalysts(symbol: str) -> dict:
    """Get Catalyst nodes linked via Research→HAS_CATALYST for a stock.

    Returns {positive: [text], negative: [text]}.
    """
    empty = {"positive": [], "negative": []}
    driver = _get_driver()
    if driver is None:
        return empty
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Research)-[:RESEARCHED]->(s:Stock {symbol: $symbol}) "
                "MATCH (r)-[:HAS_CATALYST]->(c:Catalyst) "
                "RETURN c.type AS type, c.text AS text "
                "ORDER BY r.date DESC",
                symbol=symbol,
            )
            out = {"positive": [], "negative": []}
            for rec in result:
                polarity = rec["type"]
                if polarity in out:
                    out[polarity].append(rec["text"])
            return out
    except Exception:
        return empty


# ---------------------------------------------------------------------------
# 10. Report trend (KIK-413)
# ---------------------------------------------------------------------------

def get_report_trend(symbol: str, limit: int = 10) -> list[dict]:
    """Get Report nodes with extended properties for a stock, newest first.

    Returns list of {date, score, verdict, price, per, pbr}.
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (r:Report)-[:ANALYZED]->(s:Stock {symbol: $symbol}) "
                "RETURN r.date AS date, r.score AS score, r.verdict AS verdict, "
                "r.price AS price, r.per AS per, r.pbr AS pbr "
                "ORDER BY r.date DESC LIMIT $limit",
                symbol=symbol, limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 11. Upcoming events (KIK-413)
# ---------------------------------------------------------------------------


def get_upcoming_events(limit: int = 10) -> list[dict]:
    """Get UpcomingEvent nodes from the most recent MarketContext.

    Returns list of {date, text}.
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (m:MarketContext)-[:HAS_EVENT]->(e:UpcomingEvent) "
                "RETURN e.date AS date, e.text AS text "
                "ORDER BY m.date DESC, e.id LIMIT $limit",
                limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 12. Current portfolio holdings (KIK-414)
# ---------------------------------------------------------------------------


def get_recent_sells_batch(cutoff_date: str) -> dict[str, str]:
    """Get symbols sold on or after cutoff_date (KIK-418).

    Parameters
    ----------
    cutoff_date : str
        ISO date string (e.g. "2025-01-01"). Only sells on or after this date are returned.

    Returns
    -------
    dict[str, str]
        {symbol: sell_date} for recently sold stocks. Empty dict if Neo4j unavailable.
    """
    driver = _get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (t:Trade)-[:SOLD]->(s:Stock) "
                "WHERE t.date >= $cutoff "
                "RETURN s.symbol AS symbol, max(t.date) AS sell_date",
                cutoff=cutoff_date,
            )
            return {r["symbol"]: r["sell_date"] for r in result}
    except Exception:
        return {}


def get_notes_for_symbols_batch(
    symbols: list[str],
    note_types: list[str] | None = None,
) -> dict[str, list[dict]]:
    """Get notes for multiple symbols in one query (KIK-419).

    Parameters
    ----------
    symbols : list[str]
        Ticker symbols to look up.
    note_types : list[str] | None
        Filter to specific note types (e.g. ["concern", "lesson"]).
        None means all types.

    Returns
    -------
    dict[str, list[dict]]
        {symbol: [{type, content, date}]}. Empty dict if Neo4j unavailable.
    """
    driver = _get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            if note_types:
                result = session.run(
                    "MATCH (n:Note)-[:ABOUT]->(s:Stock) "
                    "WHERE s.symbol IN $symbols AND n.type IN $types "
                    "RETURN s.symbol AS symbol, n.type AS type, "
                    "n.content AS content, n.date AS date "
                    "ORDER BY n.date DESC",
                    symbols=symbols, types=note_types,
                )
            else:
                result = session.run(
                    "MATCH (n:Note)-[:ABOUT]->(s:Stock) "
                    "WHERE s.symbol IN $symbols "
                    "RETURN s.symbol AS symbol, n.type AS type, "
                    "n.content AS content, n.date AS date "
                    "ORDER BY n.date DESC",
                    symbols=symbols,
                )
            out: dict[str, list[dict]] = {}
            for r in result:
                sym = r["symbol"]
                if sym not in out:
                    out[sym] = []
                out[sym].append({"type": r["type"], "content": r["content"], "date": r["date"]})
            return out
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 13. Current portfolio holdings (KIK-414)
# ---------------------------------------------------------------------------


def get_current_holdings() -> list[dict]:
    """Get stocks currently held in portfolio via HOLDS relationship.

    Returns list of {symbol, shares, cost_price, cost_currency, purchase_date}.
    """
    driver = _get_driver()
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
# 14. Stress test history (KIK-428)
# ---------------------------------------------------------------------------


def get_stress_test_history(symbol: str | None = None, limit: int = 5) -> list[dict]:
    """Get StressTest nodes, optionally filtered by symbol.

    Returns list of {date, scenario, portfolio_impact, var_95, var_99, symbol_count}.
    """
    driver = _get_driver()
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
    driver = _get_driver()
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
    driver = _get_driver()
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
