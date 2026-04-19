---
name: stock-skills
description: 投資アシスタント。自然言語の意図を判定し、5エージェント(screener/analyst/researcher/strategist/reviewer)に振り分ける。
user_invocable: true
---

# Stock Skills Orchestrator

ユーザーの自然言語入力を解釈し、適切なエージェントにルーティングする。

## Routing

1. `routing.yaml` を参照し、ユーザーの意図に最も近い example からエージェントを選定する
2. 単一エージェント（`agent`）→ そのエージェントをサブエージェントとして起動
3. 複数エージェント（`agents`）→ 配列の順序でサブエージェントを連鎖起動し、結果を統合
4. 該当パターンなし → `agents` セクションの `role` と `triggers` から柔軟に判定

## Execution

エージェントは必ず **Agent ツールでサブエージェントとして起動**する。自分で agent.md を読んで直接実行してはならない。

```
Agent({
  description: "<エージェント名>: <タスク概要>",
  prompt: "<agent.md の内容> + <examples.yaml の内容> + <ユーザーの入力>"
})
```

- サブエージェントの prompt に agent.md と examples.yaml の内容を含める
- サブエージェントは自律的にツール（tools/）を使ってデータ取得・判断・出力する
- 複数エージェント連鎖の場合、前のエージェントの結果を次のエージェントの prompt に渡す
- 独立したエージェント（例: analyst + researcher）は並列起動する

## Direct Actions（記録系操作）

routing.yaml で `action: direct` に分類される操作はエージェント不要。オーケストレーターが直接実行する。

### 書く

| 操作 | ツール | データ保存先 |
|:---|:---|:---|
| 投資メモ保存（thesis/concern/lesson/observation/review/target/journal） | `tools/graphrag.py` merge_note | CSV(master) + Neo4j(view) |
| ウォッチリスト追加・削除 | CSV 直接読み書き | CSV(master) + Neo4j(view) |
| 売買記録（buy/sell） | `tools/graphrag.py` merge_trade | CSV(master) + Neo4j(view) |

判断不要のデータ操作なのでエージェントは起動しない。

### 読む（各エージェントが GraphRAG 経由で取得）

| データ | 読むエージェント | 活用方法 |
|:---|:---|:---|
| 投資メモ | Analyst, Strategist | 過去の分析・テーゼとの比較 |
| lesson | Strategist, Reviewer | 判断前の制約条件、バイアス補正 |
| ウォッチリスト | Screener | 候補と重複チェック |
| 売買記録 | Health Checker, Analyst | PF診断、保有者視点の分析 |

### データ保存原則

- マスター: CSV/JSON（Claude Code が直接読み書き）
- ビュー: GraphRAG / Neo4j（dual-write）
- GraphRAG がなくても動作する（graceful degradation）

## Orchestration（自律修正ループ）

`orchestration.yaml` に従い、エージェント実行後の自動リトライ・エスカレーションを制御する。

- スクリーニング0件 → 条件緩和して再起動（最大2回）
- Reviewer FAIL → FAIL理由を踏まえて再起動（最大2回）
- 再試行上限到達 → 現時点の結果をそのまま提示
- ユーザーに聞くのは **売買の最終実行のみ**。分析・レビュー・修正は全て自律で完結

## Post-Action

- エージェント実行後、次の自然なアクションを1-2個提案する
- 投資判断を伴う出力（売買・入替・リバランス）は必ず reviewer エージェントを通す
- `agents` に strategist が含まれるパターンは reviewer を自動挿入する
- 直前の会話で扱った銘柄・結果を引き継ぎ、省略された情報を補完する

## References

- ルーティング few-shot: [routing.yaml](./routing.yaml)
- 自律修正ループ: [orchestration.yaml](./orchestration.yaml)
- コンテキスト注入: [graph-context.md](../../rules/graph-context.md)
- 投資判断フロー: [plan-check.md](../../rules/plan-check.md)
