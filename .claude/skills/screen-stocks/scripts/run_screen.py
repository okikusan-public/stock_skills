#!/usr/bin/env python3
"""Entry point for the screen-stocks skill.

Supports two modes:
  --mode query  (default): Uses yfinance EquityQuery -- no symbol list needed.
  --mode legacy          : Uses the original ValueScreener
                           with predefined symbol lists per market.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from src.data import yahoo_client
from src.core.screener import ValueScreener, QueryScreener, PullbackScreener
from src.output.formatter import format_markdown, format_query_markdown, format_pullback_markdown
from src.markets.japan import JapanMarket
from src.markets.us import USMarket
from src.markets.asean import ASEANMarket


# Legacy market classes
MARKETS = {
    "japan": JapanMarket,
    "us": USMarket,
    "asean": ASEANMarket,
}

# Mapping from user-facing region names to yfinance region codes.
# Single-region entries map to one code; multi-region entries expand to a list.
REGION_EXPAND = {
    "japan": ["jp"],
    "jp": ["jp"],
    "us": ["us"],
    "asean": ["sg", "th", "my", "id", "ph"],
    "sg": ["sg"],
    "singapore": ["sg"],
    "th": ["th"],
    "thailand": ["th"],
    "my": ["my"],
    "malaysia": ["my"],
    "id": ["id"],
    "indonesia": ["id"],
    "ph": ["ph"],
    "philippines": ["ph"],
    "hk": ["hk"],
    "hongkong": ["hk"],
    "kr": ["kr"],
    "korea": ["kr"],
    "tw": ["tw"],
    "taiwan": ["tw"],
    "cn": ["cn"],
    "china": ["cn"],
    "all": ["jp", "us", "sg", "th", "my", "id", "ph"],
}

REGION_NAMES = {
    "jp": "日本株",
    "us": "米国株",
    "sg": "シンガポール株",
    "th": "タイ株",
    "my": "マレーシア株",
    "id": "インドネシア株",
    "ph": "フィリピン株",
    "hk": "香港株",
    "kr": "韓国株",
    "tw": "台湾株",
    "cn": "中国株",
}

VALID_SECTORS = [
    "Technology",
    "Financial Services",
    "Healthcare",
    "Consumer Cyclical",
    "Industrials",
    "Communication Services",
    "Consumer Defensive",
    "Energy",
    "Basic Materials",
    "Real Estate",
    "Utilities",
]


def run_query_mode(args):
    """Run screening using EquityQuery (default mode)."""
    region_key = args.region.lower()
    regions = REGION_EXPAND.get(region_key)
    if regions is None:
        # Treat as raw 2-letter region code
        regions = [region_key]

    # pullback preset uses PullbackScreener
    if args.preset == "pullback":
        screener = PullbackScreener(yahoo_client)
        for region_code in regions:
            region_name = REGION_NAMES.get(region_code, region_code.upper())
            print(f"\n## {region_name} - 押し目買い スクリーニング結果\n")
            print("Step 1: ファンダメンタルズ条件で絞り込み中...")
            results = screener.screen(region=region_code, top_n=args.top)
            print(f"Step 2-3 完了: {len(results)}銘柄が条件に合致\n")
            print(format_pullback_markdown(results))
            print()
        return

    screener = QueryScreener(yahoo_client)

    for region_code in regions:
        region_name = REGION_NAMES.get(region_code, region_code.upper())
        sector_label = f" [{args.sector}]" if args.sector else ""

        results = screener.screen(
            region=region_code,
            preset=args.preset,
            sector=args.sector,
            top_n=args.top,
        )

        print(f"\n## {region_name} - {args.preset}{sector_label} スクリーニング結果 (EquityQuery)\n")
        print(format_query_markdown(results))
        print()


def run_legacy_mode(args):
    """Run screening using the original ValueScreener."""
    # Map region to legacy market names
    region_to_market = {
        "japan": "japan",
        "jp": "japan",
        "us": "us",
        "asean": "asean",
        "all": "all",
    }
    market_key = region_to_market.get(args.region.lower())
    if market_key is None:
        print(f"Error: Legacy mode only supports japan/us/asean/all. Got: {args.region}")
        print("Use --mode query for other regions.")
        sys.exit(1)

    if market_key == "all":
        markets_to_run = list(MARKETS.items())
    else:
        if market_key not in MARKETS:
            print(f"Error: Unknown market '{market_key}'")
            sys.exit(1)
        markets_to_run = [(market_key, MARKETS[market_key])]

    client = yahoo_client

    for market_name, market_cls in markets_to_run:
        market = market_cls()

        screener = ValueScreener(client, market)
        results = screener.screen(preset=args.preset, top_n=args.top)
        print(f"\n## {market.name} - {args.preset} スクリーニング結果\n")
        print(format_markdown(results))
        print()


def main():
    parser = argparse.ArgumentParser(description="割安株スクリーニング")

    # --region is the primary argument; --market is kept for backward compatibility
    parser.add_argument(
        "--region",
        default=None,
        help="Region/market to screen (e.g. japan, us, asean, sg, hk, kr, tw, cn)",
    )
    parser.add_argument(
        "--market",
        default=None,
        help="(Legacy) Alias for --region. Kept for backward compatibility.",
    )
    parser.add_argument(
        "--preset",
        default="value",
        choices=["value", "high-dividend", "growth-value", "deep-value", "quality", "pullback"],
    )
    parser.add_argument(
        "--sector",
        default=None,
        help=f"Sector filter. Options: {', '.join(VALID_SECTORS)}",
    )
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--mode",
        default="query",
        choices=["query", "legacy"],
        help="Screening mode: 'query' (EquityQuery, default) or 'legacy' (symbol list based)",
    )

    args = parser.parse_args()

    # Resolve --region from --market if --region not given
    if args.region is None:
        args.region = args.market if args.market else "japan"

    # Normalize region
    args.region = args.region.lower()

    # Validate sector
    if args.sector is not None:
        # Allow case-insensitive matching
        matched = None
        for s in VALID_SECTORS:
            if s.lower() == args.sector.lower():
                matched = s
                break
        if matched is None:
            print(f"Warning: Unknown sector '{args.sector}'. Valid sectors:")
            for s in VALID_SECTORS:
                print(f"  - {s}")
            sys.exit(1)
        args.sector = matched

    # pullback preset always uses query mode (needs EquityQuery + technical analysis)
    if args.preset == "pullback" and args.mode == "legacy":
        print("Note: pullback preset requires query mode. Switching to --mode query.")
        args.mode = "query"

    if args.mode == "query":
        run_query_mode(args)
    else:
        run_legacy_mode(args)


if __name__ == "__main__":
    main()
