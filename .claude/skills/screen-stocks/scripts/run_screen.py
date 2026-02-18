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
from src.core.screening.screener import ValueScreener, QueryScreener, PullbackScreener, AlphaScreener, TrendingScreener, GrowthScreener
from src.output.formatter import format_markdown, format_query_markdown, format_pullback_markdown, format_alpha_markdown, format_trending_markdown, format_growth_markdown
from src.markets.japan import JapanMarket
from src.markets.us import USMarket
from src.markets.asean import ASEANMarket

try:
    from src.data.history_store import save_screening
    HAS_HISTORY = True
except ImportError:
    HAS_HISTORY = False

try:
    from src.output.formatter import format_shareholder_return_markdown
    HAS_SR_FORMAT = True
except ImportError:
    HAS_SR_FORMAT = False

try:
    from src.data.graph_query import get_screening_frequency
    HAS_GRAPH_QUERY = True
except ImportError:
    HAS_GRAPH_QUERY = False


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


def _print_recurring_picks(results):
    """Print recurring picks highlight if graph data available (KIK-406)."""
    if not HAS_GRAPH_QUERY or not results:
        return
    try:
        symbols = [r.get("symbol") for r in results if r.get("symbol")]
        if not symbols:
            return
        freq = get_screening_frequency(symbols)
        # Only show symbols that appeared 2+ times (current run counts as new)
        recurring = {s: c for s, c in freq.items() if c >= 2}
        if recurring:
            print("**再出現銘柄** (過去のスクリーニングにも登場):")
            for sym, cnt in sorted(recurring.items(), key=lambda x: -x[1]):
                print(f"  - {sym}: 過去{cnt}回出現")
            print()
    except Exception:
        pass


def run_trending_mode(args):
    """Run trending stock screening using Grok X search."""
    try:
        from src.data import grok_client as gc
        if not gc.is_available():
            print("Error: trending preset requires XAI_API_KEY environment variable.")
            print("Set: export XAI_API_KEY=your-api-key")
            sys.exit(1)
    except ImportError:
        print("Error: grok_client module not available.")
        sys.exit(1)

    region_key = args.region.lower()
    first_region = REGION_EXPAND.get(region_key, [region_key])[0]
    region_name = REGION_NAMES.get(first_region, region_key.upper())
    theme_label = f" [{args.theme}]" if args.theme else ""

    print(f"\n## {region_name} - Xトレンド銘柄{theme_label} スクリーニング結果\n")
    print("Step 1: X (Twitter) でトレンド銘柄を検索中...")

    screener = TrendingScreener(yahoo_client, gc)
    results, market_context = screener.screen(
        region=region_key, theme=args.theme, top_n=args.top,
    )

    print(f"Step 2: {len(results)}銘柄のファンダメンタルズを取得・スコアリング完了\n")
    print(format_trending_markdown(results, market_context))

    _print_recurring_picks(results)

    if HAS_HISTORY and results:
        try:
            save_screening(preset="trending", region=region_key, results=results)
        except Exception as e:
            print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
    print()


def run_query_mode(args):
    """Run screening using EquityQuery (default mode)."""
    region_key = args.region.lower()
    regions = REGION_EXPAND.get(region_key)
    if regions is None:
        # Treat as raw 2-letter region code
        regions = [region_key]

    # trending preset uses TrendingScreener (Grok-based)
    if args.preset == "trending":
        run_trending_mode(args)
        return

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
            _print_recurring_picks(results)
            if HAS_HISTORY and results:
                try:
                    save_screening(preset="pullback", region=region_code, results=results)
                except Exception as e:
                    print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
            print()
        return

    # growth preset uses GrowthScreener
    if args.preset == "growth":
        screener = GrowthScreener(yahoo_client)
        for region_code in regions:
            region_name = REGION_NAMES.get(region_code, region_code.upper())
            sector_label = f" [{args.sector}]" if args.sector else ""
            print(f"\n## {region_name} - 純成長株{sector_label} スクリーニング結果\n")
            print("Step 1: 成長条件で絞り込み中 (EquityQuery)...")
            results = screener.screen(region=region_code, top_n=args.top, sector=args.sector)
            print(f"Step 2: {len(results)}銘柄のEPS成長率を取得・ソート完了\n")
            print(format_growth_markdown(results))
            _print_recurring_picks(results)
            if HAS_HISTORY and results:
                try:
                    save_screening(preset="growth", region=region_code, results=results, sector=args.sector)
                except Exception as e:
                    print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
            print()
        return

    # alpha preset uses AlphaScreener
    if args.preset == "alpha":
        screener = AlphaScreener(yahoo_client)
        for region_code in regions:
            region_name = REGION_NAMES.get(region_code, region_code.upper())
            print(f"\n## {region_name} - アルファシグナル スクリーニング結果\n")
            print("Step 1: 割安足切り (EquityQuery)...")
            results = screener.screen(region=region_code, top_n=args.top)
            print(f"Step 2-4 完了: {len(results)}銘柄がアルファ条件に合致\n")
            print(format_alpha_markdown(results))
            _print_recurring_picks(results)
            if HAS_HISTORY and results:
                try:
                    save_screening(preset="alpha", region=region_code, results=results)
                except Exception as e:
                    print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
            print()
        return

    screener = QueryScreener(yahoo_client)

    for region_code in regions:
        region_name = REGION_NAMES.get(region_code, region_code.upper())
        sector_label = f" [{args.sector}]" if args.sector else ""

        if args.with_pullback:
            results = screener.screen(
                region=region_code,
                preset=args.preset,
                sector=args.sector,
                top_n=args.top,
                with_pullback=True,
            )
            pullback_label = " + 押し目フィルタ"
            print(f"\n## {region_name} - {args.preset}{sector_label}{pullback_label} スクリーニング結果 (EquityQuery)\n")
            print(format_pullback_markdown(results))
            _print_recurring_picks(results)
            if HAS_HISTORY and results:
                try:
                    save_screening(preset=args.preset, region=region_code, results=results, sector=args.sector)
                except Exception as e:
                    print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
        else:
            results = screener.screen(
                region=region_code,
                preset=args.preset,
                sector=args.sector,
                top_n=args.top,
            )
            print(f"\n## {region_name} - {args.preset}{sector_label} スクリーニング結果 (EquityQuery)\n")
            if args.preset == "shareholder-return" and HAS_SR_FORMAT:
                print(format_shareholder_return_markdown(results))
            else:
                print(format_query_markdown(results))
            _print_recurring_picks(results)
            if HAS_HISTORY and results:
                try:
                    save_screening(preset=args.preset, region=region_code, results=results, sector=args.sector)
                except Exception as e:
                    print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
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
        if HAS_HISTORY and results:
            try:
                save_screening(preset=args.preset, region=market_name, results=results)
            except Exception as e:
                print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)
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
        choices=["value", "high-dividend", "growth", "growth-value", "deep-value", "quality", "pullback", "alpha", "trending", "long-term", "shareholder-return"],
    )
    parser.add_argument(
        "--sector",
        default=None,
        help=f"Sector filter. Options: {', '.join(VALID_SECTORS)}",
    )
    parser.add_argument(
        "--theme",
        default=None,
        help="Theme filter for trending preset (e.g., AI, semiconductor, EV)",
    )
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--with-pullback",
        action="store_true",
        default=False,
        help="任意プリセットにテクニカル押し目フィルタを追加適用",
    )
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

    if args.preset == "alpha" and args.mode == "legacy":
        print("Note: alpha preset requires query mode. Switching to --mode query.")
        args.mode = "query"

    if args.preset == "growth" and args.mode == "legacy":
        print("Note: growth preset requires query mode. Switching to --mode query.")
        args.mode = "query"

    if args.preset == "trending" and args.mode == "legacy":
        print("Note: trending preset requires query mode. Switching to --mode query.")
        args.mode = "query"

    if args.mode == "query":
        run_query_mode(args)
    else:
        run_legacy_mode(args)


if __name__ == "__main__":
    main()
