"""Neo4j graph store for investment knowledge graph (KIK-397/398/413).

Provides schema initialization and CRUD operations for the knowledge graph.
All writes use MERGE for idempotent operations.
Graceful degradation: if Neo4j is unavailable, operations are silently skipped.

NEO4J_MODE environment variable controls write depth (KIK-413):
  - "off"     : No Neo4j writes (JSON only)
  - "summary" : Current behavior -- score/verdict/summary only (backward compat)
  - "full"    : Semantic sub-nodes (News, Sentiment, Catalyst, etc.) with relationships
  Default: "full" if Neo4j reachable, "off" otherwise.
"""

import os
import re
import time
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

_driver = None


# ---------------------------------------------------------------------------
# Write mode (KIK-413)
# ---------------------------------------------------------------------------

_mode_cache: tuple[str, float] = ("", 0.0)
_MODE_TTL = 30.0


def _get_mode() -> str:
    """Return Neo4j write mode: 'off', 'summary', or 'full'.

    Env var ``NEO4J_MODE`` overrides auto-detection.
    Default: 'full' if Neo4j is reachable, 'off' otherwise.
    Result is cached for ``_MODE_TTL`` seconds to avoid repeated connectivity checks.
    """
    global _mode_cache
    env_mode = os.environ.get("NEO4J_MODE", "").lower()
    if env_mode in ("off", "summary", "full"):
        return env_mode
    now = time.time()
    if _mode_cache[0] and (now - _mode_cache[1]) < _MODE_TTL:
        return _mode_cache[0]
    mode = "full" if is_available() else "off"
    _mode_cache = (mode, now)
    return mode


def get_mode() -> str:
    """Public accessor for current Neo4j write mode."""
    return _get_mode()


def _get_driver():
    """Lazy-init Neo4j driver. Returns None if neo4j package not installed."""
    global _driver
    if _driver is not None:
        return _driver
    try:
        from neo4j import GraphDatabase
        _driver = GraphDatabase.driver(_NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASSWORD))
        return _driver
    except Exception:
        return None


def is_available() -> bool:
    """Check if Neo4j is reachable."""
    driver = _get_driver()
    if driver is None:
        return False
    try:
        driver.verify_connectivity()
        return True
    except Exception:
        return False


def close():
    """Close the Neo4j driver."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

_SCHEMA_CONSTRAINTS = [
    "CREATE CONSTRAINT stock_symbol IF NOT EXISTS FOR (s:Stock) REQUIRE s.symbol IS UNIQUE",
    "CREATE CONSTRAINT screen_id IF NOT EXISTS FOR (s:Screen) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT report_id IF NOT EXISTS FOR (r:Report) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT trade_id IF NOT EXISTS FOR (t:Trade) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT health_id IF NOT EXISTS FOR (h:HealthCheck) REQUIRE h.id IS UNIQUE",
    "CREATE CONSTRAINT note_id IF NOT EXISTS FOR (n:Note) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT theme_name IF NOT EXISTS FOR (t:Theme) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT sector_name IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT research_id IF NOT EXISTS FOR (r:Research) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT watchlist_name IF NOT EXISTS FOR (w:Watchlist) REQUIRE w.name IS UNIQUE",
    "CREATE CONSTRAINT market_context_id IF NOT EXISTS FOR (m:MarketContext) REQUIRE m.id IS UNIQUE",
    # KIK-413 full-mode nodes
    "CREATE CONSTRAINT news_id IF NOT EXISTS FOR (n:News) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT sentiment_id IF NOT EXISTS FOR (s:Sentiment) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT catalyst_id IF NOT EXISTS FOR (c:Catalyst) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT analyst_view_id IF NOT EXISTS FOR (a:AnalystView) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT indicator_id IF NOT EXISTS FOR (i:Indicator) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT upcoming_event_id IF NOT EXISTS FOR (e:UpcomingEvent) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT sector_rotation_id IF NOT EXISTS FOR (r:SectorRotation) REQUIRE r.id IS UNIQUE",
    # KIK-414 portfolio sync
    "CREATE CONSTRAINT portfolio_name IF NOT EXISTS FOR (p:Portfolio) REQUIRE p.name IS UNIQUE",
    # KIK-428 stress test / forecast auto-save
    "CREATE CONSTRAINT stress_test_id IF NOT EXISTS FOR (st:StressTest) REQUIRE st.id IS UNIQUE",
    "CREATE CONSTRAINT forecast_id IF NOT EXISTS FOR (f:Forecast) REQUIRE f.id IS UNIQUE",
]

_SCHEMA_INDEXES = [
    "CREATE INDEX stock_sector IF NOT EXISTS FOR (s:Stock) ON (s.sector)",
    "CREATE INDEX screen_date IF NOT EXISTS FOR (s:Screen) ON (s.date)",
    "CREATE INDEX report_date IF NOT EXISTS FOR (r:Report) ON (r.date)",
    "CREATE INDEX trade_date IF NOT EXISTS FOR (t:Trade) ON (t.date)",
    "CREATE INDEX note_type IF NOT EXISTS FOR (n:Note) ON (n.type)",
    "CREATE INDEX research_date IF NOT EXISTS FOR (r:Research) ON (r.date)",
    "CREATE INDEX research_type IF NOT EXISTS FOR (r:Research) ON (r.research_type)",
    "CREATE INDEX market_context_date IF NOT EXISTS FOR (m:MarketContext) ON (m.date)",
    # KIK-428 stress test / forecast indexes
    "CREATE INDEX stress_test_date IF NOT EXISTS FOR (st:StressTest) ON (st.date)",
    "CREATE INDEX forecast_date IF NOT EXISTS FOR (f:Forecast) ON (f.date)",
    # KIK-413 full-mode indexes
    "CREATE INDEX news_date IF NOT EXISTS FOR (n:News) ON (n.date)",
    "CREATE INDEX sentiment_source IF NOT EXISTS FOR (s:Sentiment) ON (s.source)",
    "CREATE INDEX catalyst_type IF NOT EXISTS FOR (c:Catalyst) ON (c.type)",
    "CREATE INDEX indicator_date IF NOT EXISTS FOR (i:Indicator) ON (i.date)",
]

# KIK-420: Vector indexes for semantic search
_VECTOR_INDEXES = [
    "CREATE VECTOR INDEX screen_embedding IF NOT EXISTS FOR (s:Screen) ON (s.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX report_embedding IF NOT EXISTS FOR (r:Report) ON (r.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX trade_embedding IF NOT EXISTS FOR (t:Trade) ON (t.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX healthcheck_embedding IF NOT EXISTS FOR (h:HealthCheck) ON (h.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX research_embedding IF NOT EXISTS FOR (r:Research) ON (r.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX marketcontext_embedding IF NOT EXISTS FOR (m:MarketContext) ON (m.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX note_embedding IF NOT EXISTS FOR (n:Note) ON (n.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX watchlist_embedding IF NOT EXISTS FOR (w:Watchlist) ON (w.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    # KIK-428 stress test / forecast vector indexes
    "CREATE VECTOR INDEX stresstest_embedding IF NOT EXISTS FOR (st:StressTest) ON (st.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
    "CREATE VECTOR INDEX forecast_embedding IF NOT EXISTS FOR (f:Forecast) ON (f.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}",
]


def init_schema() -> bool:
    """Create constraints and indexes. Returns True on success."""
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            for stmt in _SCHEMA_CONSTRAINTS + _SCHEMA_INDEXES:
                session.run(stmt)
            # KIK-420: Vector indexes (separate try/except -- older Neo4j may not support)
            for stmt in _VECTOR_INDEXES:
                try:
                    session.run(stmt)
                except Exception:
                    pass  # Skip if vector indexes not supported
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Embedding helper (KIK-420)
# ---------------------------------------------------------------------------

def _set_embedding(session, label: str, node_id: str,
                   semantic_summary: str = "",
                   embedding: list[float] | None = None) -> None:
    """Set semantic_summary and embedding on a node if provided."""
    if not semantic_summary and embedding is None:
        return
    sets = []
    params: dict = {"id": node_id}
    if semantic_summary:
        sets.append("n.semantic_summary = $summary")
        params["summary"] = semantic_summary
    if embedding is not None:
        sets.append("n.embedding = $embedding")
        params["embedding"] = embedding
    if sets:
        query = f"MATCH (n:{label} {{id: $id}}) SET {', '.join(sets)}"
        session.run(query, **params)


# ---------------------------------------------------------------------------
# Stock node
# ---------------------------------------------------------------------------

def merge_stock(symbol: str, name: str = "", sector: str = "", country: str = "") -> bool:
    """Create or update a Stock node."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MERGE (s:Stock {symbol: $symbol}) "
                "SET s.name = $name, s.sector = $sector, s.country = $country",
                symbol=symbol, name=name, sector=sector, country=country,
            )
            if sector:
                session.run(
                    "MERGE (sec:Sector {name: $sector}) "
                    "WITH sec "
                    "MATCH (s:Stock {symbol: $symbol}) "
                    "MERGE (s)-[:IN_SECTOR]->(sec)",
                    sector=sector, symbol=symbol,
                )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Screen node
# ---------------------------------------------------------------------------

def merge_screen(
    screen_date: str, preset: str, region: str, count: int,
    symbols: list[str],
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Screen node and SURFACED relationships to stocks."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    screen_id = f"screen_{screen_date}_{region}_{preset}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (sc:Screen {id: $id}) "
                "SET sc.date = $date, sc.preset = $preset, "
                "sc.region = $region, sc.count = $count",
                id=screen_id, date=screen_date, preset=preset,
                region=region, count=count,
            )
            _set_embedding(session, "Screen", screen_id, semantic_summary, embedding)
            for sym in symbols:
                session.run(
                    "MATCH (sc:Screen {id: $screen_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (sc)-[:SURFACED]->(s)",
                    screen_id=screen_id, symbol=sym,
                )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Report node
# ---------------------------------------------------------------------------

def merge_report(
    report_date: str, symbol: str, score: float, verdict: str,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Report node and ANALYZED relationship."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    report_id = f"report_{report_date}_{symbol}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (r:Report {id: $id}) "
                "SET r.date = $date, r.symbol = $symbol, "
                "r.score = $score, r.verdict = $verdict",
                id=report_id, date=report_date, symbol=symbol,
                score=score, verdict=verdict,
            )
            session.run(
                "MATCH (r:Report {id: $report_id}) "
                "MERGE (s:Stock {symbol: $symbol}) "
                "MERGE (r)-[:ANALYZED]->(s)",
                report_id=report_id, symbol=symbol,
            )
            _set_embedding(session, "Report", report_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Trade node
# ---------------------------------------------------------------------------

def merge_trade(
    trade_date: str, trade_type: str, symbol: str,
    shares: int, price: float, currency: str, memo: str = "",
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Trade node and BOUGHT/SOLD relationship."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    trade_id = f"trade_{trade_date}_{trade_type}_{symbol}"
    rel_type = "BOUGHT" if trade_type == "buy" else "SOLD"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (t:Trade {id: $id}) "
                "SET t.date = $date, t.type = $type, t.symbol = $symbol, "
                "t.shares = $shares, t.price = $price, t.currency = $currency, "
                "t.memo = $memo",
                id=trade_id, date=trade_date, type=trade_type,
                symbol=symbol, shares=shares, price=price,
                currency=currency, memo=memo,
            )
            session.run(
                f"MATCH (t:Trade {{id: $trade_id}}) "
                f"MERGE (s:Stock {{symbol: $symbol}}) "
                f"MERGE (t)-[:{rel_type}]->(s)",
                trade_id=trade_id, symbol=symbol,
            )
            _set_embedding(session, "Trade", trade_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HealthCheck node
# ---------------------------------------------------------------------------

def merge_health(health_date: str, summary: dict, symbols: list[str],
                  semantic_summary: str = "", embedding: list[float] | None = None,
                  ) -> bool:
    """Create a HealthCheck node and CHECKED relationships."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    health_id = f"health_{health_date}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (h:HealthCheck {id: $id}) "
                "SET h.date = $date, h.total = $total, "
                "h.healthy = $healthy, h.exit_count = $exit_count",
                id=health_id, date=health_date,
                total=summary.get("total", 0),
                healthy=summary.get("healthy", 0),
                exit_count=summary.get("exit", 0),
            )
            for sym in symbols:
                session.run(
                    "MATCH (h:HealthCheck {id: $health_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (h)-[:CHECKED]->(s)",
                    health_id=health_id, symbol=sym,
                )
            _set_embedding(session, "HealthCheck", health_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Note node
# ---------------------------------------------------------------------------

def merge_note(
    note_id: str, note_date: str, note_type: str, content: str,
    symbol: Optional[str] = None, source: str = "",
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Note node and ABOUT relationship to a stock."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MERGE (n:Note {id: $id}) "
                "SET n.date = $date, n.type = $type, "
                "n.content = $content, n.source = $source",
                id=note_id, date=note_date, type=note_type,
                content=content, source=source,
            )
            if symbol:
                session.run(
                    "MATCH (n:Note {id: $note_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (n)-[:ABOUT]->(s)",
                    note_id=note_id, symbol=symbol,
                )
            _set_embedding(session, "Note", note_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Theme tagging
# ---------------------------------------------------------------------------

def tag_theme(symbol: str, theme: str) -> bool:
    """Tag a stock with a theme."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MERGE (t:Theme {name: $theme}) "
                "WITH t "
                "MERGE (s:Stock {symbol: $symbol}) "
                "MERGE (s)-[:HAS_THEME]->(t)",
                theme=theme, symbol=symbol,
            )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Research node (KIK-398)
# ---------------------------------------------------------------------------

def _safe_id(text: str) -> str:
    """Make text safe for use in a node ID (replace non-alphanum with _)."""
    return re.sub(r"[^a-zA-Z0-9]", "_", text)


def merge_research(
    research_date: str, research_type: str, target: str,
    summary: str = "",
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Research node and optionally RESEARCHED relationship to Stock.

    For stock/business types, target is treated as a symbol and linked to Stock.
    For industry/market types, no Stock link is created.
    """
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    research_id = f"research_{research_date}_{research_type}_{_safe_id(target)}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (r:Research {id: $id}) "
                "SET r.date = $date, r.research_type = $rtype, "
                "r.target = $target, r.summary = $summary",
                id=research_id, date=research_date, rtype=research_type,
                target=target, summary=summary,
            )
            if research_type in ("stock", "business"):
                session.run(
                    "MATCH (r:Research {id: $research_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (r)-[:RESEARCHED]->(s)",
                    research_id=research_id, symbol=target,
                )
            _set_embedding(session, "Research", research_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Watchlist node (KIK-398)
# ---------------------------------------------------------------------------

def merge_watchlist(name: str, symbols: list[str],
                    semantic_summary: str = "",
                    embedding: list[float] | None = None) -> bool:
    """Create a Watchlist node and BOOKMARKED relationships to stocks."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MERGE (w:Watchlist {name: $name})",
                name=name,
            )
            # Watchlist uses 'name' as key, not 'id'; set embedding directly
            if semantic_summary or embedding is not None:
                _sets = []
                _params: dict = {"name": name}
                if semantic_summary:
                    _sets.append("w.semantic_summary = $summary")
                    _params["summary"] = semantic_summary
                if embedding is not None:
                    _sets.append("w.embedding = $embedding")
                    _params["embedding"] = embedding
                if _sets:
                    session.run(
                        f"MATCH (w:Watchlist {{name: $name}}) SET {', '.join(_sets)}",
                        **_params,
                    )
            for sym in symbols:
                session.run(
                    "MATCH (w:Watchlist {name: $name}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (w)-[:BOOKMARKED]->(s)",
                    name=name, symbol=sym,
                )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Research SUPERSEDES chain (KIK-398)
# ---------------------------------------------------------------------------

def link_research_supersedes(research_type: str, target: str) -> bool:
    """Link Research nodes of same type+target in date order with SUPERSEDES."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run(
                "MATCH (r:Research {research_type: $rtype, target: $target}) "
                "WITH r ORDER BY r.date ASC "
                "WITH collect(r) AS nodes "
                "UNWIND range(0, size(nodes)-2) AS i "
                "WITH nodes[i] AS a, nodes[i+1] AS b "
                "MERGE (a)-[:SUPERSEDES]->(b)",
                rtype=research_type, target=target,
            )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Portfolio sync (KIK-414)
# ---------------------------------------------------------------------------


def sync_portfolio(holdings: list[dict]) -> bool:
    """Sync portfolio CSV holdings to Neo4j HOLDS relationships.

    Creates a Portfolio anchor node and HOLDS relationships to each Stock.
    Removes HOLDS for stocks no longer in the portfolio.
    Cash positions (*.CASH) are excluded.
    """
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    try:
        from src.core.common import is_cash

        with driver.session() as session:
            session.run("MERGE (p:Portfolio {name: 'default'})")

            current_symbols = []
            for h in holdings:
                symbol = h.get("symbol", "")
                if not symbol or is_cash(symbol):
                    continue
                current_symbols.append(symbol)
                session.run(
                    "MERGE (s:Stock {symbol: $symbol})",
                    symbol=symbol,
                )
                session.run(
                    "MATCH (p:Portfolio {name: 'default'}) "
                    "MATCH (s:Stock {symbol: $symbol}) "
                    "MERGE (p)-[r:HOLDS]->(s) "
                    "SET r.shares = $shares, r.cost_price = $cost_price, "
                    "r.cost_currency = $cost_currency, "
                    "r.purchase_date = $purchase_date",
                    symbol=symbol,
                    shares=int(h.get("shares", 0)),
                    cost_price=float(h.get("cost_price", 0)),
                    cost_currency=h.get("cost_currency", "JPY"),
                    purchase_date=h.get("purchase_date", ""),
                )

            if current_symbols:
                session.run(
                    "MATCH (p:Portfolio {name: 'default'})-[r:HOLDS]->(s:Stock) "
                    "WHERE NOT s.symbol IN $symbols "
                    "DELETE r",
                    symbols=current_symbols,
                )
            else:
                session.run(
                    "MATCH (p:Portfolio {name: 'default'})-[r:HOLDS]->() "
                    "DELETE r",
                )
        return True
    except Exception:
        return False


def is_held(symbol: str) -> bool:
    """Check if a symbol is currently held in the portfolio."""
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock {symbol: $symbol}) "
                "RETURN count(*) AS cnt",
                symbol=symbol,
            )
            record = result.single()
            return record["cnt"] > 0 if record else False
    except Exception:
        return False


def get_held_symbols() -> list[str]:
    """Return symbols currently held in portfolio via HOLDS relationship."""
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Portfolio {name: 'default'})-[:HOLDS]->(s:Stock) "
                "RETURN s.symbol AS symbol"
            )
            return [r["symbol"] for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# MarketContext node (KIK-399)
# ---------------------------------------------------------------------------

def merge_market_context(context_date: str, indices: list[dict],
                         semantic_summary: str = "",
                         embedding: list[float] | None = None,
                         ) -> bool:
    """Create/update a MarketContext node with index snapshots.

    indices is stored as a JSON string (Neo4j can't store list-of-maps).
    """
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    import json as _json
    context_id = f"market_context_{context_date}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (m:MarketContext {id: $id}) "
                "SET m.date = $date, m.indices = $indices",
                id=context_id,
                date=context_date,
                indices=_json.dumps(indices, ensure_ascii=False),
            )
            _set_embedding(session, "MarketContext", context_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# StressTest node (KIK-428)
# ---------------------------------------------------------------------------


def merge_stress_test(
    test_date: str, scenario: str, portfolio_impact: float,
    symbols: list[str], var_95: float = 0, var_99: float = 0,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a StressTest node and STRESSED relationships to stocks."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    test_id = f"stress_test_{test_date}_{_safe_id(scenario)}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (st:StressTest {id: $id}) "
                "SET st.date = $date, st.scenario = $scenario, "
                "st.portfolio_impact = $impact, "
                "st.var_95 = $var95, st.var_99 = $var99, "
                "st.symbol_count = $cnt",
                id=test_id, date=test_date, scenario=scenario,
                impact=float(portfolio_impact),
                var95=float(var_95), var99=float(var_99),
                cnt=len(symbols),
            )
            for sym in symbols:
                session.run(
                    "MATCH (st:StressTest {id: $test_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (st)-[:STRESSED]->(s)",
                    test_id=test_id, symbol=sym,
                )
            _set_embedding(session, "StressTest", test_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Forecast node (KIK-428)
# ---------------------------------------------------------------------------


def merge_forecast(
    forecast_date: str, optimistic: float, base: float, pessimistic: float,
    symbols: list[str], total_value_jpy: float = 0,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create a Forecast node and FORECASTED relationships to stocks."""
    if _get_mode() == "off":
        return False
    driver = _get_driver()
    if driver is None:
        return False
    forecast_id = f"forecast_{forecast_date}"
    try:
        with driver.session() as session:
            session.run(
                "MERGE (f:Forecast {id: $id}) "
                "SET f.date = $date, f.optimistic = $opt, "
                "f.base = $base, f.pessimistic = $pess, "
                "f.total_value_jpy = $total, f.symbol_count = $cnt",
                id=forecast_id, date=forecast_date,
                opt=float(optimistic), base=float(base),
                pess=float(pessimistic),
                total=float(total_value_jpy), cnt=len(symbols),
            )
            for sym in symbols:
                session.run(
                    "MATCH (f:Forecast {id: $forecast_id}) "
                    "MERGE (s:Stock {symbol: $symbol}) "
                    "MERGE (f)-[:FORECASTED]->(s)",
                    forecast_id=forecast_id, symbol=sym,
                )
            _set_embedding(session, "Forecast", forecast_id, semantic_summary, embedding)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Clear all (KIK-398 --rebuild)
# ---------------------------------------------------------------------------

def clear_all() -> bool:
    """Delete all nodes and relationships. Used for --rebuild."""
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = 500) -> str:
    """Truncate text to max_len characters."""
    if not isinstance(text, str):
        return str(text)[:max_len] if text else ""
    return text[:max_len]


def merge_report_full(
    report_date: str, symbol: str, score: float, verdict: str,
    price: float = 0, per: float = 0, pbr: float = 0,
    dividend_yield: float = 0, roe: float = 0, market_cap: float = 0,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Extend an existing Report node with full valuation properties (KIK-413).

    Calls merge_report() first, then SETs additional numeric fields.
    Only runs in 'full' mode.
    """
    if _get_mode() != "full":
        return merge_report(report_date, symbol, score, verdict,
                            semantic_summary=semantic_summary, embedding=embedding)
    # Ensure base Report node exists
    merge_report(report_date, symbol, score, verdict,
                 semantic_summary=semantic_summary, embedding=embedding)
    driver = _get_driver()
    if driver is None:
        return False
    report_id = f"report_{report_date}_{symbol}"
    try:
        with driver.session() as session:
            session.run(
                "MATCH (r:Report {id: $id}) "
                "SET r.price = $price, r.per = $per, r.pbr = $pbr, "
                "r.dividend_yield = $div, r.roe = $roe, r.market_cap = $mcap",
                id=report_id, price=float(price or 0),
                per=float(per or 0), pbr=float(pbr or 0),
                div=float(dividend_yield or 0), roe=float(roe or 0),
                mcap=float(market_cap or 0),
            )
        return True
    except Exception:
        return False


def merge_research_full(
    research_date: str, research_type: str, target: str,
    summary: str = "",
    grok_research: dict | None = None,
    x_sentiment: dict | None = None,
    news: list | None = None,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create Research node with semantic sub-nodes (KIK-413).

    Expands grok_research data into News, Sentiment, Catalyst, AnalystView
    nodes connected to the Research node via relationships.
    Only creates sub-nodes in 'full' mode.
    """
    if _get_mode() != "full":
        return merge_research(research_date, research_type, target, summary,
                              semantic_summary=semantic_summary, embedding=embedding)
    # Ensure base Research + Stock nodes exist
    merge_research(research_date, research_type, target, summary,
                   semantic_summary=semantic_summary, embedding=embedding)
    driver = _get_driver()
    if driver is None:
        return False
    research_id = f"research_{research_date}_{research_type}_{_safe_id(target)}"
    try:
        with driver.session() as session:
            # --- News nodes (from grok recent_news + yahoo news) ---
            news_items: list[dict | str] = []
            if grok_research and isinstance(grok_research.get("recent_news"), list):
                for item in grok_research["recent_news"][:5]:
                    if isinstance(item, str):
                        news_items.append({"title": item, "source": "grok"})
                    elif isinstance(item, dict):
                        news_items.append({**item, "source": "grok"})
            if isinstance(news, list):
                for item in news[:5]:
                    if isinstance(item, dict):
                        news_items.append({
                            "title": item.get("title", ""),
                            "source": item.get("publisher", "yahoo"),
                            "link": item.get("link", ""),
                        })
            for i, nitem in enumerate(news_items[:10]):
                nid = f"{research_id}_news_{i}"
                title = _truncate(nitem.get("title", ""), 500)
                source = nitem.get("source", "")[:50]
                link = nitem.get("link", "")[:500]
                session.run(
                    "MERGE (n:News {id: $id}) "
                    "SET n.date = $date, n.title = $title, "
                    "n.source = $source, n.link = $link "
                    "WITH n "
                    "MATCH (r:Research {id: $rid}) "
                    "MERGE (r)-[:HAS_NEWS]->(n)",
                    id=nid, date=research_date, title=title,
                    source=source, link=link, rid=research_id,
                )
                # MENTIONS→Stock for stock/business research
                if research_type in ("stock", "business"):
                    session.run(
                        "MATCH (n:News {id: $nid}) "
                        "MERGE (s:Stock {symbol: $symbol}) "
                        "MERGE (n)-[:MENTIONS]->(s)",
                        nid=nid, symbol=target,
                    )

            # --- Sentiment nodes ---
            # From grok x_sentiment
            if grok_research and isinstance(grok_research.get("x_sentiment"), dict):
                xs = grok_research["x_sentiment"]
                sid = f"{research_id}_sent_grok"
                session.run(
                    "MERGE (s:Sentiment {id: $id}) "
                    "SET s.date = $date, s.source = 'grok_x', "
                    "s.score = $score, s.summary = $summary "
                    "WITH s "
                    "MATCH (r:Research {id: $rid}) "
                    "MERGE (r)-[:HAS_SENTIMENT]->(s)",
                    id=sid, date=research_date,
                    score=float(xs.get("score", 0)),
                    summary=_truncate(xs.get("summary", ""), 500),
                    rid=research_id,
                )
            # From top-level x_sentiment (yahoo/yfinance)
            if isinstance(x_sentiment, dict) and x_sentiment:
                sid2 = f"{research_id}_sent_yahoo"
                pos = x_sentiment.get("positive", [])
                neg = x_sentiment.get("negative", [])
                pos_text = _truncate("; ".join(pos[:3]) if isinstance(pos, list) else str(pos), 500)
                neg_text = _truncate("; ".join(neg[:3]) if isinstance(neg, list) else str(neg), 500)
                session.run(
                    "MERGE (s:Sentiment {id: $id}) "
                    "SET s.date = $date, s.source = 'yahoo_x', "
                    "s.positive = $pos, s.negative = $neg "
                    "WITH s "
                    "MATCH (r:Research {id: $rid}) "
                    "MERGE (r)-[:HAS_SENTIMENT]->(s)",
                    id=sid2, date=research_date,
                    pos=pos_text, neg=neg_text, rid=research_id,
                )

            # --- Catalyst nodes ---
            if grok_research and isinstance(grok_research.get("catalysts"), dict):
                cats = grok_research["catalysts"]
                for polarity in ("positive", "negative"):
                    items = cats.get(polarity, [])
                    if isinstance(items, list):
                        for j, txt in enumerate(items[:5]):
                            cid = f"{research_id}_cat_{polarity[0]}_{j}"
                            session.run(
                                "MERGE (c:Catalyst {id: $id}) "
                                "SET c.date = $date, c.type = $polarity, "
                                "c.text = $text "
                                "WITH c "
                                "MATCH (r:Research {id: $rid}) "
                                "MERGE (r)-[:HAS_CATALYST]->(c)",
                                id=cid, date=research_date, polarity=polarity,
                                text=_truncate(str(txt), 500), rid=research_id,
                            )

            # --- AnalystView nodes ---
            if grok_research and isinstance(grok_research.get("analyst_views"), list):
                for k, view_text in enumerate(grok_research["analyst_views"][:5]):
                    avid = f"{research_id}_av_{k}"
                    session.run(
                        "MERGE (a:AnalystView {id: $id}) "
                        "SET a.date = $date, a.text = $text "
                        "WITH a "
                        "MATCH (r:Research {id: $rid}) "
                        "MERGE (r)-[:HAS_ANALYST_VIEW]->(a)",
                        id=avid, date=research_date,
                        text=_truncate(str(view_text), 500),
                        rid=research_id,
                    )
        return True
    except Exception:
        return False


def merge_market_context_full(
    context_date: str, indices: list[dict],
    grok_research: dict | None = None,
    semantic_summary: str = "", embedding: list[float] | None = None,
) -> bool:
    """Create MarketContext with semantic sub-nodes (KIK-413).

    Expands indices into Indicator nodes, and grok_research into
    UpcomingEvent, SectorRotation, and Sentiment nodes.
    Only creates sub-nodes in 'full' mode.
    """
    if _get_mode() != "full":
        return merge_market_context(context_date, indices,
                                     semantic_summary=semantic_summary,
                                     embedding=embedding)
    # Ensure base MarketContext node exists
    merge_market_context(context_date, indices,
                         semantic_summary=semantic_summary, embedding=embedding)
    driver = _get_driver()
    if driver is None:
        return False
    context_id = f"market_context_{context_date}"
    try:
        with driver.session() as session:
            # --- Indicator nodes (from indices) ---
            for i, idx in enumerate(indices[:20]):
                iid = f"{context_id}_ind_{i}"
                session.run(
                    "MERGE (ind:Indicator {id: $id}) "
                    "SET ind.date = $date, ind.name = $name, "
                    "ind.symbol = $symbol, ind.price = $price, "
                    "ind.daily_change = $dchange, ind.weekly_change = $wchange "
                    "WITH ind "
                    "MATCH (m:MarketContext {id: $mid}) "
                    "MERGE (m)-[:INCLUDES]->(ind)",
                    id=iid, date=context_date,
                    name=str(idx.get("name", ""))[:100],
                    symbol=str(idx.get("symbol", ""))[:20],
                    price=float(idx.get("price", 0) or 0),
                    dchange=float(idx.get("daily_change", 0) or 0),
                    wchange=float(idx.get("weekly_change", 0) or 0),
                    mid=context_id,
                )

            if not grok_research:
                return True

            # --- UpcomingEvent nodes ---
            events = grok_research.get("upcoming_events", [])
            if isinstance(events, list):
                for j, ev in enumerate(events[:5]):
                    eid = f"{context_id}_event_{j}"
                    session.run(
                        "MERGE (e:UpcomingEvent {id: $id}) "
                        "SET e.date = $date, e.text = $text "
                        "WITH e "
                        "MATCH (m:MarketContext {id: $mid}) "
                        "MERGE (m)-[:HAS_EVENT]->(e)",
                        id=eid, date=context_date,
                        text=_truncate(str(ev), 500), mid=context_id,
                    )

            # --- SectorRotation nodes ---
            rotations = grok_research.get("sector_rotation", [])
            if isinstance(rotations, list):
                for k, rot in enumerate(rotations[:3]):
                    rid = f"{context_id}_rot_{k}"
                    session.run(
                        "MERGE (sr:SectorRotation {id: $id}) "
                        "SET sr.date = $date, sr.text = $text "
                        "WITH sr "
                        "MATCH (m:MarketContext {id: $mid}) "
                        "MERGE (m)-[:HAS_ROTATION]->(sr)",
                        id=rid, date=context_date,
                        text=_truncate(str(rot), 500), mid=context_id,
                    )

            # --- Sentiment node (market-level) ---
            sentiment = grok_research.get("sentiment")
            if isinstance(sentiment, dict):
                sid = f"{context_id}_sent"
                session.run(
                    "MERGE (s:Sentiment {id: $id}) "
                    "SET s.date = $date, s.source = 'market', "
                    "s.score = $score, s.summary = $summary "
                    "WITH s "
                    "MATCH (m:MarketContext {id: $mid}) "
                    "MERGE (m)-[:HAS_SENTIMENT]->(s)",
                    id=sid, date=context_date,
                    score=float(sentiment.get("score", 0)),
                    summary=_truncate(sentiment.get("summary", ""), 500),
                    mid=context_id,
                )

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_stock_history(symbol: str) -> dict:
    """Get all graph relationships for a stock.

    Returns dict with keys: screens, reports, trades, health_checks,
    notes, themes, researches.
    """
    _empty = {"screens": [], "reports": [], "trades": [],
              "health_checks": [], "notes": [], "themes": [],
              "researches": []}
    driver = _get_driver()
    if driver is None:
        return dict(_empty)
    try:
        result = dict(_empty)
        with driver.session() as session:
            # Screens
            records = session.run(
                "MATCH (sc:Screen)-[:SURFACED]->(s:Stock {symbol: $symbol}) "
                "RETURN sc.date AS date, sc.preset AS preset, sc.region AS region "
                "ORDER BY sc.date DESC",
                symbol=symbol,
            )
            result["screens"] = [dict(r) for r in records]

            # Reports
            records = session.run(
                "MATCH (r:Report)-[:ANALYZED]->(s:Stock {symbol: $symbol}) "
                "RETURN r.date AS date, r.score AS score, r.verdict AS verdict "
                "ORDER BY r.date DESC",
                symbol=symbol,
            )
            result["reports"] = [dict(r) for r in records]

            # Trades
            records = session.run(
                "MATCH (t:Trade)-[:BOUGHT|SOLD]->(s:Stock {symbol: $symbol}) "
                "RETURN t.date AS date, t.type AS type, "
                "t.shares AS shares, t.price AS price "
                "ORDER BY t.date DESC",
                symbol=symbol,
            )
            result["trades"] = [dict(r) for r in records]

            # Health checks
            records = session.run(
                "MATCH (h:HealthCheck)-[:CHECKED]->(s:Stock {symbol: $symbol}) "
                "RETURN h.date AS date "
                "ORDER BY h.date DESC",
                symbol=symbol,
            )
            result["health_checks"] = [dict(r) for r in records]

            # Notes
            records = session.run(
                "MATCH (n:Note)-[:ABOUT]->(s:Stock {symbol: $symbol}) "
                "RETURN n.id AS id, n.date AS date, n.type AS type, "
                "n.content AS content "
                "ORDER BY n.date DESC",
                symbol=symbol,
            )
            result["notes"] = [dict(r) for r in records]

            # Themes
            records = session.run(
                "MATCH (s:Stock {symbol: $symbol})-[:HAS_THEME]->(t:Theme) "
                "RETURN t.name AS name",
                symbol=symbol,
            )
            result["themes"] = [r["name"] for r in records]

            # Researches (KIK-398)
            records = session.run(
                "MATCH (r:Research)-[:RESEARCHED]->(s:Stock {symbol: $symbol}) "
                "RETURN r.date AS date, r.research_type AS research_type, "
                "r.summary AS summary "
                "ORDER BY r.date DESC",
                symbol=symbol,
            )
            result["researches"] = [dict(r) for r in records]

        return result
    except Exception:
        return dict(_empty)
