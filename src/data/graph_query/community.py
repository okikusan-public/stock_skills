"""Community detection via co-occurrence analysis (KIK-547).

Computes stock similarity from shared Screen/Theme/Sector/News signals,
then runs Louvain community detection to cluster similar stocks.
All computation is Python-side (no GDS dependency required).
"""

from datetime import datetime
from itertools import combinations
from typing import Optional

from src.data.graph_query import _common

try:
    import networkx as nx
    from networkx.algorithms.community import louvain_communities

    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False


# ---------------------------------------------------------------------------
# Default signal weights for weighted Jaccard similarity
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS = {
    "screens": 1.0,
    "themes": 0.8,
    "news": 0.6,
    "sectors": 0.5,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_communities(
    similarity_cutoff: float = 0.3,
    top_k: int = 10,
    resolution: float = 1.0,
) -> list[dict]:
    """Run community detection pipeline.

    Steps:
    1. Query co-occurrence vectors from Neo4j
    2. Compute weighted Jaccard similarity (Python)
    3. Run Louvain community detection (networkx)
    4. Auto-name communities from common Sector/Theme
    5. Save Community nodes + BELONGS_TO relationships

    Returns list of dicts: {community_id, name, level, size, members}
    Empty list if Neo4j unavailable or insufficient data.
    """
    if not _HAS_NETWORKX:
        return []
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        vectors = _fetch_cooccurrence_vectors(driver)
        if len(vectors) < 2:
            return []
        edges = _compute_jaccard_similarity(vectors, similarity_cutoff, top_k)
        if not edges:
            return []
        communities = _run_louvain(edges, resolution)
        if not communities:
            return []
        # Auto-name and save
        with driver.session() as session:
            for comm in communities:
                comm["name"] = _auto_name_community(
                    comm["members"], session, comm["community_id"]
                )
        _save_communities(communities)
        return communities
    except Exception:
        return []


def get_communities(level: int = 0) -> list[dict]:
    """Retrieve existing Community nodes from Neo4j.

    Returns list of dicts: {id, name, size, level, created_at, members}
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (c:Community) "
                "WHERE c.level = $level "
                "OPTIONAL MATCH (s:Stock)-[:BELONGS_TO]->(c) "
                "RETURN c.id AS id, c.name AS name, c.size AS size, "
                "c.level AS level, c.created_at AS created_at, "
                "collect(s.symbol) AS members "
                "ORDER BY c.size DESC",
                level=level,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


def get_stock_community(symbol: str) -> Optional[dict]:
    """Get the community a stock belongs to.

    Returns {community_id, name, size, level, peers} or None.
    """
    driver = _common._get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (s:Stock {symbol: $symbol})-[:BELONGS_TO]->(c:Community) "
                "OPTIONAL MATCH (peer:Stock)-[:BELONGS_TO]->(c) "
                "WHERE peer.symbol <> $symbol "
                "RETURN c.id AS community_id, c.name AS name, "
                "c.size AS size, c.level AS level, "
                "collect(peer.symbol) AS peers",
                symbol=symbol,
            )
            record = result.single()
            if record is None:
                return None
            return dict(record)
    except Exception:
        return None


def get_similar_stocks(
    symbol: str,
    top_k: int = 5,
    similarity_cutoff: float = 0.3,
) -> list[dict]:
    """Get stocks most similar to the given symbol.

    Lightweight version: computes similarity without full community detection.
    Returns list of dicts: {symbol, similarity, shared_screens, shared_themes,
    shared_sectors, shared_news}
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        vectors = _fetch_cooccurrence_vectors(driver)
        if symbol not in vectors:
            return []
        target = vectors[symbol]
        results = []
        for other_sym, other_vec in vectors.items():
            if other_sym == symbol:
                continue
            sim = _jaccard_single(target, other_vec)
            if sim >= similarity_cutoff:
                results.append(
                    {
                        "symbol": other_sym,
                        "similarity": round(sim, 4),
                        "shared_screens": len(
                            target["screens"] & other_vec["screens"]
                        ),
                        "shared_themes": len(target["themes"] & other_vec["themes"]),
                        "shared_sectors": len(
                            target["sectors"] & other_vec["sectors"]
                        ),
                        "shared_news": len(target["news"] & other_vec["news"]),
                    }
                )
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_cooccurrence_vectors(driver) -> dict[str, dict[str, set]]:
    """Query Neo4j for Stock co-occurrence signals.

    Returns {symbol: {"screens": set, "themes": set, "sectors": set, "news": set}}
    """
    vectors: dict[str, dict[str, set]] = {}

    def _ensure(sym: str) -> dict[str, set]:
        if sym not in vectors:
            vectors[sym] = {
                "screens": set(),
                "themes": set(),
                "sectors": set(),
                "news": set(),
            }
        return vectors[sym]

    with driver.session() as session:
        # Screen co-occurrence
        for r in session.run(
            "MATCH (sc:Screen)-[:SURFACED]->(s:Stock) "
            "RETURN s.symbol AS symbol, collect(DISTINCT sc.id) AS ids"
        ):
            v = _ensure(r["symbol"])
            v["screens"] = set(r["ids"])

        # Theme co-occurrence
        for r in session.run(
            "MATCH (s:Stock)-[:HAS_THEME]->(t:Theme) "
            "RETURN s.symbol AS symbol, collect(DISTINCT t.name) AS names"
        ):
            v = _ensure(r["symbol"])
            v["themes"] = set(r["names"])

        # Sector membership
        for r in session.run(
            "MATCH (s:Stock)-[:IN_SECTOR]->(sec:Sector) "
            "RETURN s.symbol AS symbol, collect(DISTINCT sec.name) AS names"
        ):
            v = _ensure(r["symbol"])
            v["sectors"] = set(r["names"])

        # News co-occurrence
        for r in session.run(
            "MATCH (n:News)-[:MENTIONS]->(s:Stock) "
            "RETURN s.symbol AS symbol, collect(DISTINCT n.id) AS ids"
        ):
            v = _ensure(r["symbol"])
            v["news"] = set(r["ids"])

    return vectors


def _jaccard_single(
    a: dict[str, set],
    b: dict[str, set],
    weights: Optional[dict[str, float]] = None,
) -> float:
    """Compute weighted Jaccard similarity between two co-occurrence vectors."""
    w = weights or _DEFAULT_WEIGHTS
    numerator = 0.0
    denominator = 0.0
    for key, weight in w.items():
        a_set = a.get(key, set())
        b_set = b.get(key, set())
        union = len(a_set | b_set)
        if union == 0:
            continue
        intersection = len(a_set & b_set)
        numerator += weight * intersection / union
        denominator += weight
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _compute_jaccard_similarity(
    vectors: dict[str, dict[str, set]],
    cutoff: float,
    top_k: int,
    weights: Optional[dict[str, float]] = None,
) -> list[tuple[str, str, float]]:
    """Compute weighted Jaccard similarity between all Stock pairs.

    Returns list of (symbol_a, symbol_b, similarity) above cutoff,
    limited to top_k per node.
    """
    all_edges: list[tuple[str, str, float]] = []
    symbols = list(vectors.keys())

    for sym_a, sym_b in combinations(symbols, 2):
        sim = _jaccard_single(vectors[sym_a], vectors[sym_b], weights)
        if sim >= cutoff:
            all_edges.append((sym_a, sym_b, sim))

    if not all_edges:
        return []

    # Apply top_k limit per node
    from collections import defaultdict

    neighbor_count: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for a, b, s in all_edges:
        neighbor_count[a].append((b, s))
        neighbor_count[b].append((a, s))

    # Keep only top_k neighbors per node
    kept_pairs: set[tuple[str, str]] = set()
    for sym in neighbor_count:
        neighbors = sorted(neighbor_count[sym], key=lambda x: x[1], reverse=True)
        for nb, _ in neighbors[:top_k]:
            pair = tuple(sorted([sym, nb]))
            kept_pairs.add(pair)

    return [(a, b, s) for a, b, s in all_edges if tuple(sorted([a, b])) in kept_pairs]


def _run_louvain(
    edges: list[tuple[str, str, float]],
    resolution: float = 1.0,
) -> list[dict]:
    """Run Louvain community detection on the similarity graph.

    Returns list of {community_id, members, level}
    """
    if not _HAS_NETWORKX:
        return []

    G = nx.Graph()
    for a, b, w in edges:
        G.add_edge(a, b, weight=w)

    if G.number_of_nodes() == 0:
        return []

    communities_sets = louvain_communities(G, weight="weight", resolution=resolution)

    result = []
    for idx, members in enumerate(sorted(communities_sets, key=len, reverse=True)):
        result.append(
            {
                "community_id": idx,
                "members": sorted(members),
                "level": 0,
                "size": len(members),
            }
        )
    return result


def _auto_name_community(
    members: list[str],
    session,
    fallback_id: int = 0,
) -> str:
    """Generate a human-readable name for a community.

    Picks the most common Sector and Theme among members.
    """
    if not members:
        return f"Community_{fallback_id}"

    # Most common sector
    sector_result = session.run(
        "MATCH (s:Stock)-[:IN_SECTOR]->(sec:Sector) "
        "WHERE s.symbol IN $symbols "
        "RETURN sec.name AS name, count(*) AS cnt "
        "ORDER BY cnt DESC LIMIT 1",
        symbols=members,
    )
    sector_record = sector_result.single()
    sector_name = sector_record["name"] if sector_record else None

    # Most common theme
    theme_result = session.run(
        "MATCH (s:Stock)-[:HAS_THEME]->(t:Theme) "
        "WHERE s.symbol IN $symbols "
        "RETURN t.name AS name, count(*) AS cnt "
        "ORDER BY cnt DESC LIMIT 1",
        symbols=members,
    )
    theme_record = theme_result.single()
    theme_name = theme_record["name"] if theme_record else None

    if sector_name and theme_name:
        return f"{sector_name} x {theme_name}"
    if sector_name:
        return sector_name
    if theme_name:
        return theme_name
    return f"Community_{fallback_id}"


def _save_communities(communities: list[dict]) -> bool:
    """Save Community nodes and BELONGS_TO relationships to Neo4j.

    Clears previous Community nodes first (idempotent).
    """
    from src.data.graph_store import _common as gs_common

    if gs_common._get_mode() == "off":
        return False
    driver = gs_common._get_driver()
    if driver is None:
        return False
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        with driver.session() as session:
            # Clear existing communities
            session.run(
                "MATCH (c:Community) DETACH DELETE c"
            )
            # Create new communities
            for comm in communities:
                comm_id = f"community_{comm['level']}_{comm['community_id']}"
                session.run(
                    "CREATE (c:Community {"
                    "id: $id, name: $name, size: $size, "
                    "level: $level, created_at: $ts})",
                    id=comm_id,
                    name=comm.get("name", f"Community_{comm['community_id']}"),
                    size=comm["size"],
                    level=comm["level"],
                    ts=ts,
                )
                for symbol in comm["members"]:
                    session.run(
                        "MATCH (s:Stock {symbol: $symbol}) "
                        "MATCH (c:Community {id: $cid}) "
                        "MERGE (s)-[:BELONGS_TO]->(c)",
                        symbol=symbol,
                        cid=comm_id,
                    )
        return True
    except Exception:
        return False
