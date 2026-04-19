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
  prompt: "<agent.md の内容> + <examples.yaml の内容> + <ユーザーの入力> + <コンテキスト>"
})
```

- サブエージェントの prompt に agent.md と examples.yaml の内容を含める
- サブエージェントは自律的にツール（tools/）を使ってデータ取得・判断・出力する

### Screener 起動時の追加コンテキスト（KIK-670）

Screener を起動する前に `tools/portfolio_io.py` の `load_portfolio()` で保有銘柄リストを取得し、prompt に含める。

```
# Screener の prompt に渡す情報
1. agent.md + examples.yaml の内容
2. ユーザーの入力
3. 前段エージェントの結果（連鎖時：投資テーゼ・文脈・除外理由を含む）
4. 既保有銘柄リスト（以下の銘柄は結果から除外すること）
```

保有銘柄リストの取得が失敗した場合（CSV なし等）は除外なしで続行する。

### 連鎖 vs 並列の判断基準（KIK-672）

#### エージェント間の並列判断

`agents: [A, B]` は原則 **順序付き連鎖** であり、A の結果を B の prompt に渡す。

| パターン | 判断 | 例 |
|:---|:---|:---|
| A の出力が B の入力に影響する | **連鎖** | researcher → screener（テーマ特定→テーマ別スクリーニング） |
| A と B が独立した観点で同じ対象を調査する | **並列** | health-checker + researcher（定量+定性で市況チェック） |

並列起動してよいのは、routing.yaml に明示的に独立と判断できる場合のみ。迷ったら連鎖を選ぶ。

#### オーケストレーター主導の並列化（KIK-673）

**サブエージェントに並列を指示しても逐次実行される。** オーケストレーター自身が複数の Agent ツールを1つのメッセージで同時発行して強制的に並列化する。

##### Screener の並列化

テーマ×地域の組み合わせごとに独立した Screener サブエージェントを起動する:

```
# NG: 1つのScreenerに全テーマを任せる（逐次実行される）
Agent(screener, prompt="4テーマ全部やれ")

# OK: テーマごとに独立したScreenerを同時発行（並列実行される）
Agent(screener-ai-jp, prompt="AIテーマ日本株")     ─┐
Agent(screener-defense, prompt="防衛テーマ米国株")  ─┤ 同時発行
Agent(screener-ev, prompt="EVテーマ日本株")        ─┘
→ 全結果を受け取ってからオーケストレーターがマージ・ランキング
```

##### Reviewer の並列化

3レビュアーを独立したサブエージェントとして起動する:

```
# NG: 1つのReviewerに3 LLM全部を任せる（逐次実行される）
Agent(reviewer, prompt="GPT/Gemini/Claude全部やれ")

# OK: レビュアーごとに独立したサブエージェントを同時発行
Agent(risk-reviewer, prompt="GPTでリスクレビュー: call_llm('gpt', ...)")   ─┐
Agent(logic-reviewer, prompt="Geminiでロジックレビュー: call_llm('gemini', ...)") ─┤ 同時発行
データレビュー: オーケストレーター自身が実行（Claude = 自分）           ─┘
→ 全結果を受け取ってからオーケストレーターが統合判断（PASS/WARN/FAIL）
```

##### 単一テーマ・単一レビューの場合

テーマが1つだけ、またはレビューが軽量な場合は、従来通り1つのサブエージェントに任せてよい。並列化は複数の独立タスクがある場合のみ適用する。

### Reviewer 自動挿入（KIK-659）

エージェント実行後、`orchestration.yaml` の `auto_review` ルールに従い Reviewer の要否を **自動判定** する。
判定は仕組みで強制されるため、オーケストレーターが意識的に判断する必要はない。

**トリガー条件**（いずれかに該当 → Reviewer を自動起動）:
1. 実行エージェントに `strategist` が含まれる
2. 実行エージェントに `screener` が含まれる（スクリーニング結果も投資判断の入口）
3. routing.yaml の該当パターンに `review: true` フラグがある
4. 出力に投資判断キーワード（売却/購入/入替/リバランス等）が含まれる

**二重実行防止**: 同一セッションで既に Reviewer が実行済みの場合はスキップする。

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

- スクリーニング0件 → 条件緩和して自律リトライ（最大2回）
- Reviewer PASS/WARN → そのまま出力（自律）
- **Reviewer FAIL → FAIL理由と修正方針案をユーザーに提示 → 承認後リトライ**（最大2回）
- 再試行上限到達 → 現時点の結果をそのまま提示

## Post-Action

### 1. 結果をユーザーに提示

エージェントの出力をユーザーに提示する。Reviewer の自動挿入は `orchestration.yaml` の `auto_review` で制御。

### 2. データ保存（自律実行）（KIK-674）

エージェント実行後、結果を以下に保存する。**ユーザーの指示を待たず自律的に実行する。**

| エージェント | GraphRAG 保存 | data/ ローカル保存 |
|:---|:---|:---|
| Screener | merge_screen() | data/screening_results/{preset}_{date}.json |
| Analyst | merge_report() | data/reports/{symbol}_{date}.json |
| Researcher | merge_note(type=observation) | data/research/{topic}_{date}.json |
| Health Checker | merge_note(type=observation) | data/session_logs/{date}.json |
| Strategist | merge_note(type=review) | data/session_logs/{date}.json |
| Reviewer | merge_note(type=review) | data/reviews/{date}.json |

売買が実行された場合は merge_trade() も実行する。

**データ保存原則**:
- **data/ (JSON/CSV) は常に保存する。** GraphRAG の有無に関わらない
- GraphRAG (Neo4j) は接続時のみ dual-write

### 3. 次のアクションを提案

- 次の自然なアクションを1-2個提案する
- 直前の会話で扱った銘柄・結果を引き継ぎ、省略された情報を補完する

## References

- ルーティング few-shot: [routing.yaml](./routing.yaml)
- 自律修正ループ: [orchestration.yaml](./orchestration.yaml)
