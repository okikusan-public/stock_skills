#!/usr/bin/env python3
"""Entry point for the graph-query skill (KIK-409)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from src.data.graph_nl_query import query


def main():
    if len(sys.argv) < 2:
        print("Usage: run_query.py \"自然言語クエリ\"")
        sys.exit(1)

    user_input = " ".join(sys.argv[1:])
    result = query(user_input)

    if result is None:
        print("クエリに一致するデータが見つかりませんでした。")
        print("\n対応クエリ例:")
        print("  - 「7203.T の前回レポートは？」")
        print("  - 「繰り返し候補に上がってる銘柄は？」")
        print("  - 「AAPL のリサーチ履歴」")
        print("  - 「最近の市況は？」")
        print("  - 「7203.T の取引履歴」")
        sys.exit(0)

    print(result["formatted"])


if __name__ == "__main__":
    main()
