---
name: investment-note
description: 投資メモの管理。投資テーゼ・懸念・学びなどをノートとして記録・参照・削除。
argument-hint: "[save|list|delete] [--symbol SYMBOL] [--type TYPE] [--content TEXT] [--id NOTE_ID]"
allowed-tools: Bash(python3 *)
---

# 投資メモ管理スキル

$ARGUMENTS を解析し、以下のコマンドを実行してください。

## 実行コマンド

```bash
python3 /Users/kikuchihiroyuki/stock-skills/.claude/skills/investment-note/scripts/manage_note.py $ARGUMENTS
```

結果をそのまま表示してください。

## コマンド一覧

### save -- メモ保存

```bash
python3 .../manage_note.py save --symbol 7203.T --type thesis --content "EV普及で部品需要増"
```

### list -- メモ一覧

```bash
python3 .../manage_note.py list [--symbol 7203.T] [--type concern]
```

### delete -- メモ削除

```bash
python3 .../manage_note.py delete --id note_2025-02-17_7203_T_abc12345
```

## ノートタイプ

| タイプ | 意味 | 使い方例 |
|:---|:---|:---|
| thesis | 投資テーゼ | 「EV普及で部品需要増」 |
| observation | 気づき | 「3回連続スクリーニング上位」 |
| concern | 懸念 | 「中国市場の減速リスク」 |
| review | 振り返り | 「3ヶ月保有、テーゼ通り推移」 |
| target | 目標・出口 | 「PER 15 で利確」 |
| lesson | 学び | 「バリュートラップだった」 |

## 引数の解釈ルール（自然言語対応）

| ユーザー入力 | コマンド |
|:-----------|:--------|
| 「トヨタについてメモ: EV需要が...」 | save --symbol 7203.T --type observation --content "..." |
| 「AAPLの懸念: 中国売上の減速」 | save --symbol AAPL --type concern --content "中国売上の減速" |
| 「バリュートラップの学び」 | save --type lesson --content "..." |
| 「メモ一覧」「ノート見せて」 | list |
| 「トヨタのメモ」 | list --symbol 7203.T |
| 「メモを削除」 | delete --id ... |

タイプの自動判定:
- 投資テーマ/買う理由/論拠 → thesis
- 観察/気づき/メモ → observation
- 懸念/リスク/心配 → concern
- レビュー/振り返り/反省 → review
- 目標価格/買い増し/利確 → target
- 学び/教訓/失敗から → lesson
