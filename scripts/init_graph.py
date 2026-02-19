#!/usr/bin/env python3
"""Initialize Neo4j knowledge graph and import existing history (KIK-397/398/420).

Usage:
    python3 scripts/init_graph.py [--history-dir data/history] [--notes-dir data/notes]
    python3 scripts/init_graph.py --rebuild   # full wipe + reimport (with embeddings if TEI available)

This script:
1. Creates schema constraints and indexes (including vector indexes, KIK-420)
2. Imports existing history files (screen/report/trade/health/research)
3. Imports portfolio holdings and watchlists
4. Imports existing notes
5. Links research SUPERSEDES chains
6. Generates semantic_summary + embedding for each node (KIK-420, TEI optional)
7. Is idempotent (safe to run multiple times)
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
    get_mode,
    init_schema,
    is_available,
    link_research_supersedes,
    merge_forecast,
    merge_health,
    merge_market_context,
    merge_market_context_full,
    merge_note,
    merge_report,
    merge_report_full,
    merge_research,
    merge_research_full,
    merge_screen,
    merge_stock,
    merge_stress_test,
    merge_trade,
    merge_watchlist,
    sync_portfolio,
)

# KIK-420: Optional embedding support (graceful degradation if TEI unavailable)
try:
    from src.data import embedding_client, summary_builder
    HAS_EMBEDDING = True
except ImportError:
    HAS_EMBEDDING = False


def _get_embedding(summary_text: str) -> "list[float] | None":
    """Get embedding for summary text. Returns None if TEI unavailable."""
    if not HAS_EMBEDDING:
        return None
    try:
        return embedding_client.get_embedding(summary_text)
    except Exception:
        return None


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

            # KIK-420: Generate embedding
            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    top_syms = symbols[:5]
                    summary_text = summary_builder.build_screen_summary(
                        screen_date, preset, region, top_syms)
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_screen(screen_date, preset, region, len(results), symbols,
                         semantic_summary=summary_text, embedding=emb)
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
            # KIK-420: Generate embedding
            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_report_summary(
                        symbol, data.get("name", ""),
                        data.get("value_score", 0), data.get("verdict", ""),
                        data.get("sector", ""))
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_report_full(
                report_date=data.get("date", ""),
                symbol=symbol,
                score=data.get("value_score", 0),
                verdict=data.get("verdict", ""),
                price=data.get("price", 0),
                per=data.get("per", 0),
                pbr=data.get("pbr", 0),
                dividend_yield=data.get("dividend_yield", 0),
                roe=data.get("roe", 0),
                market_cap=data.get("market_cap", 0),
                semantic_summary=summary_text,
                embedding=emb,
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

            # KIK-420: Generate embedding
            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_trade_summary(
                        data.get("date", ""), data.get("trade_type", "buy"),
                        symbol, data.get("shares", 0), data.get("memo", ""))
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_trade(
                trade_date=data.get("date", ""),
                trade_type=data.get("trade_type", "buy"),
                symbol=symbol,
                shares=data.get("shares", 0),
                price=data.get("price", 0),
                currency=data.get("currency", "JPY"),
                memo=data.get("memo", ""),
                semantic_summary=summary_text,
                embedding=emb,
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

            # KIK-420: Generate embedding
            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_health_summary(
                        health_date, summary)
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_health(health_date, summary, symbols,
                         semantic_summary=summary_text, embedding=emb)
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

            # KIK-420: Generate embedding
            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_research_summary(
                        research_type, target,
                        {"summary": data.get("summary", "")})
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_research_full(
                research_date=research_date,
                research_type=research_type,
                target=target,
                summary=data.get("summary", ""),
                grok_research=data.get("grok_research"),
                x_sentiment=data.get("x_sentiment"),
                news=data.get("news"),
                semantic_summary=summary_text,
                embedding=emb,
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


def import_market_context(history_dir: str) -> int:
    """Import market context history files."""
    d = Path(history_dir) / "market_context"
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            context_date = data.get("date", "")
            if not context_date:
                continue
            indices = data.get("indices", [])

            # KIK-420: Generate embedding
            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_market_context_summary(
                        context_date, indices, data.get("grok_research"))
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_market_context_full(
                context_date=context_date, indices=indices,
                grok_research=data.get("grok_research"),
                semantic_summary=summary_text,
                embedding=emb,
            )
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
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
                # KIK-420: Generate embedding
                summary_text = ""
                emb = None
                if HAS_EMBEDDING:
                    try:
                        summary_text = summary_builder.build_note_summary(
                            note.get("symbol", ""),
                            note.get("type", "observation"),
                            note.get("content", ""))
                        emb = _get_embedding(summary_text)
                    except Exception:
                        pass

                merge_note(
                    note_id=note_id,
                    note_date=note.get("date", ""),
                    note_type=note.get("type", "observation"),
                    content=note.get("content", ""),
                    symbol=note.get("symbol"),
                    source=note.get("source", ""),
                    semantic_summary=summary_text,
                    embedding=emb,
                )
                count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_portfolio(csv_path: str) -> int:
    """Import portfolio holdings as Stock nodes and sync HOLDS relationships."""
    p = Path(csv_path)
    if not p.exists():
        return 0
    count = 0
    holdings = []
    try:
        with open(p, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row.get("symbol", "")
                if not symbol or symbol.upper().endswith(".CASH"):
                    continue
                merge_stock(symbol=symbol, name=row.get("memo", ""))
                holdings.append(row)
                count += 1
    except (OSError, csv.Error):
        pass

    # KIK-414: Sync Portfolio→HOLDS→Stock relationships
    if holdings:
        try:
            sync_portfolio(holdings)
        except Exception:
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
            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_watchlist_summary(
                        name, symbols)
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass
            merge_watchlist(name, symbols,
                            semantic_summary=summary_text, embedding=emb)
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_stress_tests(history_dir: str) -> int:
    """Import stress test history files (KIK-428)."""
    d = Path(history_dir) / "stress_test"
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            test_date = data.get("date", "")
            scenario = data.get("scenario", "")
            symbols = data.get("symbols", [])
            portfolio_impact = data.get("portfolio_impact", 0)
            var_result = data.get("var_result", {})

            for sym in symbols:
                if sym:
                    merge_stock(symbol=sym)

            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_stress_test_summary(
                        test_date, scenario, portfolio_impact, len(symbols))
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_stress_test(
                test_date=test_date, scenario=scenario,
                portfolio_impact=portfolio_impact, symbols=symbols,
                var_95=var_result.get("var_95_daily", 0),
                var_99=var_result.get("var_99_daily", 0),
                semantic_summary=summary_text, embedding=emb,
            )
            count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count


def import_forecasts(history_dir: str) -> int:
    """Import forecast history files (KIK-428)."""
    d = Path(history_dir) / "forecast"
    if not d.exists():
        return 0
    count = 0
    for fp in sorted(d.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            forecast_date = data.get("date", "")
            portfolio = data.get("portfolio", {})
            positions = data.get("positions", [])
            symbols = [p.get("symbol", "") for p in positions if p.get("symbol")]

            for sym in symbols:
                if sym:
                    merge_stock(symbol=sym)

            summary_text = ""
            emb = None
            if HAS_EMBEDDING:
                try:
                    summary_text = summary_builder.build_forecast_summary(
                        forecast_date,
                        portfolio.get("optimistic"),
                        portfolio.get("base"),
                        portfolio.get("pessimistic"),
                        len(symbols))
                    emb = _get_embedding(summary_text)
                except Exception:
                    pass

            merge_forecast(
                forecast_date=forecast_date,
                optimistic=portfolio.get("optimistic", 0),
                base=portfolio.get("base", 0),
                pessimistic=portfolio.get("pessimistic", 0),
                symbols=symbols,
                total_value_jpy=data.get("total_value_jpy", 0),
                semantic_summary=summary_text, embedding=emb,
            )
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

    # KIK-420: Check TEI availability
    tei_ok = False
    if HAS_EMBEDDING:
        tei_ok = embedding_client.is_available()
    if tei_ok:
        print("TEI embedding service: available (embeddings will be generated)")
    else:
        print("TEI embedding service: not available (skipping embeddings)")

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
    market_ctx = import_market_context(args.history_dir)
    stress_tests = import_stress_tests(args.history_dir)
    forecasts = import_forecasts(args.history_dir)

    print(f"  Screens:        {screens}")
    print(f"  Reports:        {reports}")
    print(f"  Trades:         {trades}")
    print(f"  Health:         {health}")
    print(f"  Research:       {research}")
    print(f"  MarketContext:  {market_ctx}")
    print(f"  StressTests:    {stress_tests}")
    print(f"  Forecasts:      {forecasts}")

    print(f"\nImporting portfolio from {args.portfolio_csv}...")
    portfolio = import_portfolio(args.portfolio_csv)
    print(f"  Holdings: {portfolio}")

    print(f"\nImporting watchlists from {args.watchlists_dir}...")
    watchlists = import_watchlists(args.watchlists_dir)
    print(f"  Watchlists: {watchlists}")

    print(f"\nImporting notes from {args.notes_dir}...")
    notes = import_notes(args.notes_dir)
    print(f"  Notes:    {notes}")

    total = screens + reports + trades + health + research + stress_tests + forecasts + portfolio + watchlists + notes
    print(f"\nDone. Total {total} records imported.")


if __name__ == "__main__":
    main()
