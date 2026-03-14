"""Shared utilities for graph_store submodules (KIK-507).

Contains connection management, mode detection, error handling decorator,
and shared helper functions used across all graph_store submodules.
"""

import functools
import os
import re
import sys
import time
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

_driver = None
_unavailable_warned = False  # KIK-443: warn once on connection failure


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
    global _unavailable_warned
    driver = _get_driver()
    if driver is None:
        if not _unavailable_warned:
            print(
                "⚠️  Neo4jに接続できません\n"
                "    原因: Dockerコンテナが起動していない可能性があります\n"
                "    対処: docker compose up -d を実行してください\n"
                "    → Neo4jなしで続行します（コンテキストなし）",
                file=sys.stderr,
            )
            _unavailable_warned = True
        return False
    try:
        driver.verify_connectivity()
        _unavailable_warned = False  # reset on successful connection
        return True
    except Exception:
        if not _unavailable_warned:
            print(
                "⚠️  Neo4jに接続できません\n"
                "    原因: Dockerコンテナが起動していない可能性があります\n"
                "    対処: docker compose up -d を実行してください\n"
                "    → Neo4jなしで続行します（コンテキストなし）",
                file=sys.stderr,
            )
            _unavailable_warned = True
        return False


def close():
    """Close the Neo4j driver."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_id(text: str) -> str:
    """Make text safe for use in a node ID (replace non-alphanum with _)."""
    return re.sub(r"[^a-zA-Z0-9]", "_", text)


def _truncate(text: str, max_len: int = 500) -> str:
    """Truncate text to max_len characters."""
    if not isinstance(text, str):
        return str(text)[:max_len] if text else ""
    return text[:max_len]


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
# Schema
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
    # KIK-472 action item
    "CREATE CONSTRAINT action_item_id IF NOT EXISTS FOR (a:ActionItem) REQUIRE a.id IS UNIQUE",
    # KIK-547 community detection
    "CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE",
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
    # KIK-472 action item indexes
    "CREATE INDEX action_item_status IF NOT EXISTS FOR (a:ActionItem) ON (a.status)",
    "CREATE INDEX action_item_date IF NOT EXISTS FOR (a:ActionItem) ON (a.date)",
    # KIK-547 community detection indexes
    "CREATE INDEX community_level IF NOT EXISTS FOR (c:Community) ON (c.level)",
    "CREATE INDEX community_created IF NOT EXISTS FOR (c:Community) ON (c.created_at)",
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
# AI relationship cyphers (KIK-434)
# ---------------------------------------------------------------------------

_AI_REL_CYPHERS = {
    "INFLUENCES": (
        "MATCH (a {id: $fid}) MATCH (b {id: $tid}) "
        "MERGE (a)-[r:INFLUENCES]->(b) "
        "SET r.confidence = $conf, r.reason = $reason, "
        "r.created_by = 'ai', r.created_at = $ts"
    ),
    "CONTRADICTS": (
        "MATCH (a {id: $fid}) MATCH (b {id: $tid}) "
        "MERGE (a)-[r:CONTRADICTS]->(b) "
        "SET r.confidence = $conf, r.reason = $reason, "
        "r.created_by = 'ai', r.created_at = $ts"
    ),
    "CONTEXT_OF": (
        "MATCH (a {id: $fid}) MATCH (b {id: $tid}) "
        "MERGE (a)-[r:CONTEXT_OF]->(b) "
        "SET r.confidence = $conf, r.reason = $reason, "
        "r.created_by = 'ai', r.created_at = $ts"
    ),
    "INFORMS": (
        "MATCH (a {id: $fid}) MATCH (b {id: $tid}) "
        "MERGE (a)-[r:INFORMS]->(b) "
        "SET r.confidence = $conf, r.reason = $reason, "
        "r.created_by = 'ai', r.created_at = $ts"
    ),
    "SUPPORTS": (
        "MATCH (a {id: $fid}) MATCH (b {id: $tid}) "
        "MERGE (a)-[r:SUPPORTS]->(b) "
        "SET r.confidence = $conf, r.reason = $reason, "
        "r.created_by = 'ai', r.created_at = $ts"
    ),
}


def create_ai_relationship(
    from_id: str,
    to_id: str,
    rel_type: str,
    confidence: float,
    reason: str,
) -> bool:
    """MERGE an AI-determined semantic relationship between two nodes (KIK-434)."""
    if _get_mode() == "off":
        return False
    cypher = _AI_REL_CYPHERS.get(rel_type)
    if not cypher:
        return False
    driver = _get_driver()
    if driver is None:
        return False
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        with driver.session() as session:
            session.run(
                cypher,
                fid=from_id, tid=to_id,
                conf=float(confidence),
                reason=str(reason)[:500],
                ts=ts,
            )
        return True
    except Exception:
        return False


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
