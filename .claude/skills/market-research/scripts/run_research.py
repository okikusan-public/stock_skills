#!/usr/bin/env python3
"""Entry point for the market-research skill."""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from src.data import yahoo_client

# HAS_MODULE パターン
try:
    from src.core.research.researcher import research_stock, research_industry, research_market
    HAS_RESEARCHER = True
except ImportError:
    HAS_RESEARCHER = False

try:
    from src.core.research.researcher import research_business
    HAS_BUSINESS = True
except ImportError:
    HAS_BUSINESS = False

try:
    from src.output.research_formatter import (
        format_stock_research,
        format_industry_research,
        format_market_research,
    )
    HAS_FORMATTER = True
except ImportError:
    HAS_FORMATTER = False

try:
    from src.output.research_formatter import format_business_research
    HAS_BUSINESS_FORMATTER = True
except ImportError:
    HAS_BUSINESS_FORMATTER = False


def cmd_stock(args):
    """銘柄リサーチ"""
    if not HAS_RESEARCHER:
        print("Error: researcher モジュールが見つかりません。")
        sys.exit(1)

    print(f"リサーチ中: {args.symbol} ...")
    result = research_stock(args.symbol, yahoo_client)

    if HAS_FORMATTER:
        print(format_stock_research(result))
    else:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_industry(args):
    """業界リサーチ"""
    if not HAS_RESEARCHER:
        print("Error: researcher モジュールが見つかりません。")
        sys.exit(1)

    print(f"業界リサーチ中: {args.theme} ...")
    result = research_industry(args.theme)

    if HAS_FORMATTER:
        print(format_industry_research(result))
    else:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_market(args):
    """マーケットリサーチ"""
    if not HAS_RESEARCHER:
        print("Error: researcher モジュールが見つかりません。")
        sys.exit(1)

    print(f"マーケットリサーチ中: {args.market} ...")
    result = research_market(args.market, yahoo_client)

    if HAS_FORMATTER:
        print(format_market_research(result))
    else:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_business(args):
    """ビジネスモデル分析"""
    if not HAS_BUSINESS:
        print("Error: researcher モジュール (research_business) が見つかりません。")
        sys.exit(1)

    print(f"ビジネスモデル分析中: {args.symbol} ...")
    result = research_business(args.symbol, yahoo_client)

    if HAS_BUSINESS_FORMATTER:
        print(format_business_research(result))
    else:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="深掘りリサーチツール")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # stock
    p_stock = subparsers.add_parser("stock", help="銘柄リサーチ")
    p_stock.add_argument("symbol", help="ティッカーシンボル (例: 7203.T, AAPL)")
    p_stock.set_defaults(func=cmd_stock)

    # industry
    p_industry = subparsers.add_parser("industry", help="業界・テーマリサーチ")
    p_industry.add_argument("theme", help="業界名またはテーマ (例: 半導体, AI)")
    p_industry.set_defaults(func=cmd_industry)

    # market
    p_market = subparsers.add_parser("market", help="マーケット概況リサーチ")
    p_market.add_argument("market", help="マーケット名や指数 (例: 日経平均, S&P500)")
    p_market.set_defaults(func=cmd_market)

    # business
    p_business = subparsers.add_parser("business", help="ビジネスモデル分析")
    p_business.add_argument("symbol", help="ティッカーシンボル (例: 7751.T, AAPL)")
    p_business.set_defaults(func=cmd_business)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
