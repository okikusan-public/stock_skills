#!/usr/bin/env python3
"""Backfill community detection for existing Stock nodes (KIK-548).

Usage:
    python3 scripts/backfill_communities.py [--dry-run] [--cutoff 0.3] [--top-k 10] [--resolution 1.0]

Runs the community detection pipeline (KIK-547) on all Stock nodes in Neo4j:
1. Fetch co-occurrence vectors (Screen/Theme/Sector/News)
2. Compute weighted Jaccard similarity
3. Run Louvain community detection
4. Save Community nodes + BELONGS_TO relationships

Idempotent: re-running clears existing communities and regenerates.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.graph_store import _get_driver, is_available


def backfill(
    similarity_cutoff: float = 0.3,
    top_k: int = 10,
    resolution: float = 1.0,
    dry_run: bool = False,
) -> dict:
    """Run community detection and return statistics.

    Returns dict with keys: stock_count, community_count, max_size, min_size,
    avg_size, isolated_count, communities.
    """
    from src.data.graph_query.community import (
        _fetch_cooccurrence_vectors,
        _compute_jaccard_similarity,
        _run_louvain,
        _auto_name_community,
        _save_communities,
    )

    driver = _get_driver()
    if driver is None:
        print("ERROR: Neo4j driver not available.")
        return {}

    # Step 1: Fetch co-occurrence vectors
    print("Fetching co-occurrence vectors...")
    vectors = _fetch_cooccurrence_vectors(driver)
    stock_count = len(vectors)
    print(f"  Found {stock_count} Stock nodes with co-occurrence data")

    if stock_count < 2:
        print("  Insufficient data (need at least 2 stocks). Exiting.")
        return {
            "stock_count": stock_count,
            "community_count": 0,
            "max_size": 0,
            "min_size": 0,
            "avg_size": 0.0,
            "isolated_count": stock_count,
            "communities": [],
        }

    # Step 2: Compute similarity
    print(f"Computing Jaccard similarity (cutoff={similarity_cutoff}, top_k={top_k})...")
    edges = _compute_jaccard_similarity(vectors, similarity_cutoff, top_k)
    print(f"  Found {len(edges)} similarity edges")

    if not edges:
        print("  No similarity edges above cutoff. All stocks are isolated.")
        return {
            "stock_count": stock_count,
            "community_count": 0,
            "max_size": 0,
            "min_size": 0,
            "avg_size": 0.0,
            "isolated_count": stock_count,
            "communities": [],
        }

    # Step 3: Louvain community detection
    print(f"Running Louvain community detection (resolution={resolution})...")
    communities = _run_louvain(edges, resolution)
    print(f"  Detected {len(communities)} communities")

    # Step 4: Auto-name communities
    print("Auto-naming communities...")
    with driver.session() as session:
        for comm in communities:
            comm["name"] = _auto_name_community(
                comm["members"], session, comm["community_id"]
            )

    # Compute statistics
    clustered_stocks = set()
    for c in communities:
        clustered_stocks.update(c["members"])
    isolated_count = stock_count - len(clustered_stocks)

    sizes = [c["size"] for c in communities]
    stats = {
        "stock_count": stock_count,
        "community_count": len(communities),
        "max_size": max(sizes) if sizes else 0,
        "min_size": min(sizes) if sizes else 0,
        "avg_size": round(sum(sizes) / len(sizes), 1) if sizes else 0.0,
        "isolated_count": isolated_count,
        "communities": communities,
    }

    # Step 5: Save to Neo4j
    if dry_run:
        print("\n[DRY-RUN] Would save the following communities:")
    else:
        print("Saving communities to Neo4j...")
        _save_communities(communities)
        print("  Done.")

    return stats


def _print_report(stats: dict, dry_run: bool = False) -> None:
    """Print backfill execution report."""
    if not stats:
        return

    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"\n{'=' * 50}")
    print(f"{prefix}Community Backfill Report")
    print(f"{'=' * 50}")
    print(f"  Stock nodes processed:  {stats['stock_count']}")
    print(f"  Communities generated:  {stats['community_count']}")
    if stats["community_count"] > 0:
        print(f"  Max cluster size:       {stats['max_size']}")
        print(f"  Min cluster size:       {stats['min_size']}")
        print(f"  Avg cluster size:       {stats['avg_size']}")
    print(f"  Isolated nodes:         {stats['isolated_count']}")

    if stats.get("communities"):
        print(f"\n  Communities:")
        for c in stats["communities"]:
            members_str = ", ".join(c["members"][:5])
            if len(c["members"]) > 5:
                members_str += f" +{len(c['members']) - 5} more"
            print(f"    [{c['community_id']}] {c['name']} ({c['size']} stocks): {members_str}")

    print(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill community detection for existing stocks (KIK-548)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without making changes",
    )
    parser.add_argument(
        "--cutoff", type=float, default=0.3,
        help="Minimum Jaccard similarity to create an edge (default: 0.3)",
    )
    parser.add_argument(
        "--top-k", type=int, default=10,
        help="Maximum similar neighbors per stock (default: 10)",
    )
    parser.add_argument(
        "--resolution", type=float, default=1.0,
        help="Louvain resolution parameter (default: 1.0)",
    )
    args = parser.parse_args()

    print("Checking Neo4j connection...")
    if not is_available():
        print("ERROR: Neo4j is not reachable. Start with: docker compose up -d")
        sys.exit(1)

    try:
        import networkx  # noqa: F401
    except ImportError:
        print("ERROR: networkx is required. Install with: pip install networkx")
        sys.exit(1)

    if args.dry_run:
        print("\n[DRY-RUN MODE] No changes will be made.\n")

    stats = backfill(
        similarity_cutoff=args.cutoff,
        top_k=args.top_k,
        resolution=args.resolution,
        dry_run=args.dry_run,
    )

    _print_report(stats, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
