#!/usr/bin/env python3
"""Initialize Neo4j knowledge graph and import existing history (KIK-397/398).

Usage:
    python3 scripts/init_graph.py [--history-dir data/history] [--notes-dir data/notes]
    python3 scripts/init_graph.py --rebuild   # full wipe + reimport

This script:
1. Creates schema constraints and indexes
2. Imports existing history files (screen/report/trade/health/research)
3. Imports portfolio holdings and watchlists
4. Imports existing notes
5. Links research SUPERSEDES chains
6. Is idempotent (safe to run multiple times)
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.graph_store import (
    clear_all,
    init_schema,
    is_available,
    link_research_supersedes,
    merge_health,
    merge_note,
    merge_report,
    merge_research,
    merge_screen,
    merge_stock,
    merge_trade,
    merge_watchlist,
)


def import_screens(history_dir: str) -> int:
    """Import screening history files."""
    d = Path(history_dir) / "screen"
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            screen_date = data.get("date", "")
            preset = data.get("preset", "")
            region = data.get("region", "")
            results = data.get("results", [])
            symbols = [r.get("symbol", "") for r in results if r.get("symbol")]

            # Merge stock nodes with metadata
            for r in results:
                sym = r.get("symbol", "")
                if sym:
                    merge_stock(
                        symbol=sym,
                        name=r.get("name", ""),
                        sector=r.get("sector", ""),
                    )

            merge_screen(screen_date, preset, region, len(results), symbols)
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_reports(history_dir: str) -> int:
    """Import report history files."""
    d = Path(history_dir) / "report"
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            symbol = data.get("symbol", "")
            if not symbol:
                continue
            merge_stock(
                symbol=symbol,
                name=data.get("name", ""),
                sector=data.get("sector", ""),
            )
            merge_report(
                report_date=data.get("date", ""),
                symbol=symbol,
                score=data.get("value_score", 0),
                verdict=data.get("verdict", ""),
            )
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_trades(history_dir: str) -> int:
    """Import trade history files."""
    d = Path(history_dir) / "trade"
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            symbol = data.get("symbol", "")
            if not symbol:
                continue
            merge_stock(symbol=symbol)
            merge_trade(
                trade_date=data.get("date", ""),
                trade_type=data.get("trade_type", "buy"),
                symbol=symbol,
                shares=data.get("shares", 0),
                price=data.get("price", 0),
                currency=data.get("currency", "JPY"),
                memo=data.get("memo", ""),
            )
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_health(history_dir: str) -> int:
    """Import health check history files."""
    d = Path(history_dir) / "health"
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            health_date = data.get("date", "")
            summary = data.get("summary", {})
            positions = data.get("positions", [])
            symbols = [p.get("symbol", "") for p in positions if p.get("symbol")]
            merge_health(health_date, summary, symbols)
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_research(history_dir: str) -> int:
    """Import research history files and build SUPERSEDES chains."""
    d = Path(history_dir) / "research"
    if not d.exists():
        return 0
    count = 0
    # Track unique (type, target) pairs for SUPERSEDES linking
    targets = defaultdict(set)
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            research_date = data.get("date", "")
            research_type = data.get("research_type", "")
            target = data.get("target", "")
            if not target:
                continue

            # For stock/business, also merge the Stock node
            if research_type in ("stock", "business"):
                merge_stock(symbol=target, name=data.get("name", ""))

            merge_research(
                research_date=research_date,
                research_type=research_type,
                target=target,
                summary=data.get("summary", ""),
            )
            targets[research_type].add(target)
            count += 1
        except (json.JSONDecodeError, OSError):
            continue

    # Build SUPERSEDES chains for each unique type+target
    for rtype, target_set in targets.items():
        for t in target_set:
            link_research_supersedes(rtype, t)

    return count


def import_notes(notes_dir: str) -> int:
    """Import note files."""
    d = Path(notes_dir)
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            notes = data if isinstance(data, list) else [data]
            for note in notes:
                note_id = note.get("id", "")
                if not note_id:
                    continue
                merge_note(
                    note_id=note_id,
                    note_date=note.get("date", ""),
                    note_type=note.get("type", "observation"),
                    content=note.get("content", ""),
                    symbol=note.get("symbol"),
                    source=note.get("source", ""),
                )
                count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_portfolio(csv_path: str) -> int:
    """Import portfolio holdings as Stock nodes (skip cash positions)."""
    p = Path(csv_path)
    if not p.exists():
        return 0
    count = 0
    try:
        with open(p, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row.get("symbol", "")
                if not symbol or symbol.upper().endswith(".CASH"):
                    continue
                merge_stock(symbol=symbol, name=row.get("memo", ""))
                count += 1
    except (OSError, csv.Error):
        pass
    return count


def import_watchlists(watchlists_dir: str) -> int:
    """Import watchlist files as Watchlist nodes with BOOKMARKED relationships."""
    d = Path(watchlists_dir)
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                symbols = json.load(f)
            if not isinstance(symbols, list):
                continue
            # Filter empty symbols
            symbols = [s for s in symbols if s]
            if not symbols:
                continue
            name = fp.stem  # filename without extension
            for sym in symbols:
                merge_stock(symbol=sym)
            merge_watchlist(name, symbols)
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def main():
    parser = argparse.ArgumentParser(description="Initialize Neo4j knowledge graph")
    parser.add_argument("--history-dir", default="data/history")
    parser.add_argument("--notes-dir", default="data/notes")
    parser.add_argument(
        "--portfolio-csv",
        default=".claude/skills/stock-portfolio/data/portfolio.csv",
    )
    parser.add_argument("--watchlists-dir", default="data/watchlists")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Delete all nodes and reimport everything",
    )
    args = parser.parse_args()

    print("Checking Neo4j connection...")
    if not is_available():
        print("ERROR: Neo4j is not reachable. Start with: docker compose up -d")
        sys.exit(1)

    if args.rebuild:
        print("Rebuilding: deleting all nodes...")
        clear_all()
        print("All nodes deleted.")

    print("Initializing schema...")
    if not init_schema():
        print("ERROR: Failed to create schema.")
        sys.exit(1)
    print("Schema initialized.")

    print(f"\nImporting history from {args.history_dir}...")
    screens = import_screens(args.history_dir)
    reports = import_reports(args.history_dir)
    trades = import_trades(args.history_dir)
    health = import_health(args.history_dir)
    research = import_research(args.history_dir)

    print(f"  Screens:  {screens}")
    print(f"  Reports:  {reports}")
    print(f"  Trades:   {trades}")
    print(f"  Health:   {health}")
    print(f"  Research: {research}")

    print(f"\nImporting portfolio from {args.portfolio_csv}...")
    portfolio = import_portfolio(args.portfolio_csv)
    print(f"  Holdings: {portfolio}")

    print(f"\nImporting watchlists from {args.watchlists_dir}...")
    watchlists = import_watchlists(args.watchlists_dir)
    print(f"  Watchlists: {watchlists}")

    print(f"\nImporting notes from {args.notes_dir}...")
    notes = import_notes(args.notes_dir)
    print(f"  Notes:    {notes}")

    total = screens + reports + trades + health + research + portfolio + watchlists + notes
    print(f"\nDone. Total {total} records imported.")


if __name__ == "__main__":
    main()
