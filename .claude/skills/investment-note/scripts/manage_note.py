#!/usr/bin/env python3
"""Entry point for the investment-note skill (KIK-408)."""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from src.data.note_manager import save_note, load_notes, delete_note


def cmd_save(args):
    """Save a note."""
    if not args.symbol:
        print("Error: --symbol は必須です。")
        sys.exit(1)
    if not args.content:
        print("Error: --content は必須です。")
        sys.exit(1)

    note = save_note(
        symbol=args.symbol,
        note_type=args.type,
        content=args.content,
        source=args.source,
    )
    print(f"メモを保存しました: {note['id']}")
    print(f"  銘柄: {note['symbol']} / タイプ: {note['type']}")
    print(f"  内容: {note['content']}")


def cmd_list(args):
    """List notes."""
    notes = load_notes(symbol=args.symbol, note_type=args.type)

    if not notes:
        if args.symbol:
            print(f"{args.symbol} のメモはありません。")
        else:
            print("メモはありません。")
        return

    label_parts = []
    if args.symbol:
        label_parts.append(args.symbol)
    if args.type:
        label_parts.append(args.type)
    label = " / ".join(label_parts) if label_parts else "全件"

    print(f"## 投資メモ一覧 ({label}: {len(notes)} 件)\n")
    print("| 日付 | 銘柄 | タイプ | 内容 |")
    print("|:-----|:-----|:-------|:-----|")
    for n in notes:
        content = n.get("content", "")
        short = content[:50] + "..." if len(content) > 50 else content
        short = short.replace("|", "\\|").replace("\n", " ")
        print(f"| {n.get('date', '-')} | {n.get('symbol', '-')} | {n.get('type', '-')} | {short} |")

    print(f"\n合計 {len(notes)} 件")


def cmd_delete(args):
    """Delete a note by ID."""
    if not args.id:
        print("Error: --id は必須です。")
        sys.exit(1)

    if delete_note(args.id):
        print(f"メモを削除しました: {args.id}")
    else:
        print(f"メモが見つかりません: {args.id}")


def main():
    parser = argparse.ArgumentParser(description="投資メモ管理")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = subparsers.add_parser("save", help="メモ保存")
    p_save.add_argument("--symbol", required=True, help="ティッカーシンボル (例: 7203.T)")
    p_save.add_argument(
        "--type", default="observation",
        choices=["thesis", "observation", "concern", "review", "target", "lesson"],
        help="メモタイプ",
    )
    p_save.add_argument("--content", required=True, help="メモ内容")
    p_save.add_argument("--source", default="manual", help="ソース (例: manual, health-check)")
    p_save.set_defaults(func=cmd_save)

    # list
    p_list = subparsers.add_parser("list", help="メモ一覧")
    p_list.add_argument("--symbol", default=None, help="銘柄でフィルタ")
    p_list.add_argument("--type", default=None, help="タイプでフィルタ")
    p_list.set_defaults(func=cmd_list)

    # delete
    p_delete = subparsers.add_parser("delete", help="メモ削除")
    p_delete.add_argument("--id", required=True, help="メモID")
    p_delete.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
