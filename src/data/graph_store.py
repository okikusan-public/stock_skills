"""Neo4j graph store for investment knowledge graph (KIK-397).

Provides schema initialization and CRUD operations for the knowledge graph.
All writes use MERGE for idempotent operations.
Graceful degradation: if Neo4j is unavailable, operations are silently skipped.
"""

import os
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

_driver = None


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
]

_SCHEMA_INDEXES = [
    "CREATE INDEX stock_sector IF NOT EXISTS FOR (s:Stock) ON (s.sector)",
    "CREATE INDEX screen_date IF NOT EXISTS FOR (s:Screen) ON (s.date)",
    "CREATE INDEX report_date IF NOT EXISTS FOR (r:Report) ON (r.date)",
    "CREATE INDEX trade_date IF NOT EXISTS FOR (t:Trade) ON (t.date)",
    "CREATE INDEX note_type IF NOT EXISTS FOR (n:Note) ON (n.type)",
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
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Stock node
# ---------------------------------------------------------------------------

def merge_stock(symbol: str, name: str = "", sector: str = "", country: str = "") -> bool:
    """Create or update a Stock node."""
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
) -> bool:
    """Create a Screen node and SURFACED relationships to stocks."""
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
) -> bool:
    """Create a Report node and ANALYZED relationship."""
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
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Trade node
# ---------------------------------------------------------------------------

def merge_trade(
    trade_date: str, trade_type: str, symbol: str,
    shares: int, price: float, currency: str, memo: str = "",
) -> bool:
    """Create a Trade node and BOUGHT/SOLD relationship."""
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
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HealthCheck node
# ---------------------------------------------------------------------------

def merge_health(health_date: str, summary: dict, symbols: list[str]) -> bool:
    """Create a HealthCheck node and CHECKED relationships."""
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
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Note node
# ---------------------------------------------------------------------------

def merge_note(
    note_id: str, note_date: str, note_type: str, content: str,
    symbol: Optional[str] = None, source: str = "",
) -> bool:
    """Create a Note node and ABOUT relationship to a stock."""
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
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Theme tagging
# ---------------------------------------------------------------------------

def tag_theme(symbol: str, theme: str) -> bool:
    """Tag a stock with a theme."""
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
# Query helpers
# ---------------------------------------------------------------------------

def get_stock_history(symbol: str) -> dict:
    """Get all graph relationships for a stock.

    Returns dict with keys: screens, reports, trades, health_checks, notes, themes.
    """
    driver = _get_driver()
    if driver is None:
        return {"screens": [], "reports": [], "trades": [],
                "health_checks": [], "notes": [], "themes": []}
    try:
        result = {"screens": [], "reports": [], "trades": [],
                  "health_checks": [], "notes": [], "themes": []}
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

        return result
    except Exception:
        return {"screens": [], "reports": [], "trades": [],
                "health_checks": [], "notes": [], "themes": []}
