"""Portfolio command: what-if -- Run What-If simulation (add/remove/swap stocks)."""

import json
import sys

from portfolio_commands import (
    HAS_WHAT_IF,
    HAS_WHAT_IF_FORMATTER,
    format_what_if,
    parse_add_arg,
    parse_remove_arg,
    print_removal_contexts,
    run_what_if_simulation,
    yahoo_client,
)


def cmd_what_if(
    csv_path: str,
    add_str: str | None,
    remove_str: str | None = None,
) -> None:
    """Run What-If simulation: add/remove stocks and compare metrics. (KIK-451)"""
    if not HAS_WHAT_IF:
        print("Error: portfolio_simulation モジュールが見つかりません。")
        sys.exit(1)

    if not add_str and not remove_str:
        print("Error: --add または --remove のいずれかを指定してください。")
        sys.exit(1)

    # 1. Parse arguments
    try:
        proposed = parse_add_arg(add_str) if add_str else []
    except ValueError as e:
        print(f"Error (--add): {e}")
        sys.exit(1)

    try:
        removals = parse_remove_arg(remove_str) if remove_str else None
    except ValueError as e:
        print(f"Error (--remove): {e}")
        sys.exit(1)

    # KIK-470: Show context for removal candidates
    if removals:
        removal_symbols = [r["symbol"] for r in removals]
        print_removal_contexts(removal_symbols)

    print("What-If シミュレーション実行中...\n")

    # 2. Run simulation
    try:
        result = run_what_if_simulation(csv_path, proposed, yahoo_client, removals=removals)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # 3. Output
    if HAS_WHAT_IF_FORMATTER:
        print(format_what_if(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
