# Graph Context: ナレッジグラフスキーマ + 自動コンテキスト注入 (KIK-411/420)

## Neo4j ナレッジグラフスキーマ

CSV/JSON が master、Neo4j は検索・関連付け用の view（dual-write パターン）。詳細は `docs/neo4j-schema.md` 参照。

**23 ノード:**
Stock(中心), Screen, Report, Trade, HealthCheck, Note, Theme, Sector,
Research, Watchlist, MarketContext, Portfolio,
News, Sentiment, Catalyst, AnalystView, Indicator, UpcomingEvent, SectorRotation,
StressTest, Forecast, ActionItem, Community

**主要リレーション:**
- `Screen-[SURFACED]->Stock` / `Report-[ANALYZED]->Stock` / `Trade-[BOUGHT|SOLD]->Stock`
- `Portfolio-[HOLDS]->Stock` (現在保有, KIK-414) / `Watchlist-[BOOKMARKED]->Stock`
- `Research-[HAS_NEWS]->News-[MENTIONS]->Stock` / `Research-[HAS_SENTIMENT]->Sentiment`
- `Research-[HAS_CATALYST]->Catalyst` / `Research-[HAS_ANALYST_VIEW]->AnalystView`
- `Research-[SUPERSEDES]->Research` (同一対象の新旧チェーン)
- `MarketContext-[INCLUDES]->Indicator` / `MarketContext-[HAS_EVENT]->UpcomingEvent`
- `Note-[ABOUT]->Stock` / `Note-[ABOUT]->Portfolio` / `Note-[ABOUT]->MarketContext` (KIK-491)
- `Research-[ANALYZES]->Sector` / `Research-[COMPLEMENTS]->MarketContext` (KIK-491)
- `Stock-[IN_SECTOR]->Sector` / `Stock-[HAS_THEME]->Theme`
- `ActionItem-[TARGETS]->Stock` / `HealthCheck-[TRIGGERED]->ActionItem` (KIK-472)
- `Stock-[BELONGS_TO]->Community` (KIK-547: コミュニティ検出)

**データの流れ:** スキル実行 → JSON/CSV保存(master) → Neo4j同期(view) → 次回 `get_context.py` で自動取得

---

## 自動コンテキスト注入

ユーザーのプロンプトに銘柄名・ティッカーシンボルが含まれている場合、
スキル実行前に以下のスクリプトを実行してコンテキストを取得する。

## いつ実行するか

**毎回実行。** TEI + Neo4j が利用可能な限り、すべてのプロンプトでベクトル類似検索を行う（KIK-420）。

加えて、以下の条件でシンボルベース検索も併用:
- ティッカーシンボル（7203.T, AAPL, D05.SI 等）が含まれる
- 企業名（トヨタ、Apple 等）+ 「どう」「調べて」「分析」等の分析意図がある
- 「PF」「ポートフォリオ」+ 状態確認の意図がある
- 「相場」「市況」等のマーケット照会意図がある

### ハイブリッド検索 (KIK-420)

| TEI | Neo4j | 動作 |
|:---|:---|:---|
| OK | OK | **毎回ベクトル検索** + シンボルベース検索 |
| NG | OK | シンボルベース検索のみ（従来通り） |
| OK | NG | 従来通り（intent-routing のみ） |
| NG | NG | 従来通り（intent-routing のみ） |

シンボルが含まれない曖昧なクエリ（「前に調べた半導体関連の銘柄」）でも、ベクトル検索により過去の関連ノードを取得可能。

## コンテキスト取得コマンド

```bash
python3 scripts/get_context.py "<ユーザー入力>"
```

## コンテキストの使い方

1. **出力1行目のアクション指示に従う**（KIK-428）:
   - `⛔ FRESH — スキル実行不要。このコンテキストのみで回答。` → スキルを実行せずコンテキストだけで回答
   - `⚡ RECENT — 差分モードで軽量更新。` → 差分取得のみ
   - `🔄 STALE — フル再取得。スキルを実行。` → スキルをフル実行
   - `🆕 NONE — データなし。スキルを実行。` → スキルをフル実行
2. 「推奨スキル」を参考にスキルを選択する（intent-routing.md と合わせて判断）
3. 前回の値がある場合は差分を意識した出力にする
5. Neo4j 未接続時は出力が「コンテキストなし」→ 従来通り intent-routing のみで判断

## コンテキスト鮮度判定 (KIK-427)

`get_context.py` の出力に鮮度ラベル（FRESH/RECENT/STALE/NONE）を付与し、LLM がデータの再取得要否を判断する。

### 鮮度ラベル

| ラベル | 基準 | LLMの行動 |
|:---|:---|:---|
| **FRESH** | `CONTEXT_FRESH_HOURS` 以内（デフォルト24h） | コンテキストのみで回答。API再取得しない |
| **RECENT** | `CONTEXT_RECENT_HOURS` 以内（デフォルト168h=7日） | 差分モードで軽量に更新 |
| **STALE** | `CONTEXT_RECENT_HOURS` 超 | フル再取得（レポート/リサーチを再実行） |
| **NONE** | データなし | ゼロから実行 |

### 環境変数

```bash
# グローバル閾値（時間単位）
CONTEXT_FRESH_HOURS=24      # これ以内 → FRESH
CONTEXT_RECENT_HOURS=168    # これ以内 → RECENT / これ超 → STALE
```

未設定時はデフォルト値（24h / 168h）で動作。

## スキル推奨の優先度

| 関係性 | 推奨スキル | 理由 |
|:---|:---|:---|
| 保有銘柄（BOUGHT あり） | `/stock-portfolio health` | 保有者として診断優先 |
| テーゼ3ヶ月経過 | `/stock-portfolio health` + レビュー促し | 定期振り返りタイミング |
| EXIT 判定あり | `/screen-stocks`（同セクター代替） | 乗り換え提案 |
| ウォッチ中（BOOKMARKED） | `/stock-report` + 前回差分 | 買い時かの判断材料 |
| 3回以上スクリーニング出現 | `/stock-report` + 注目フラグ | 繰り返し上位で注目度高 |
| 直近リサーチ済み（RECENT） | 差分のみ取得 | API コスト削減（鮮度判定で自動判断） |
| 懸念メモあり | `/stock-report` + 懸念再検証 | 心配事項の確認 |
| 過去データあり | `/stock-report` | 過去の文脈を踏まえた分析 |
| 未知の銘柄 | `/stock-report` | ゼロから調査 |
| 市況照会 | `/market-research market` | 市況コンテキスト参照 |
| ポートフォリオ照会 | `/stock-portfolio health` | PF全体の診断 |

## intent-routing.md との連携

1. **graph-context が先**: まずコンテキストを取得し、推奨スキルを確認
2. **intent-routing で最終判断**: ユーザーの意図と推奨スキルを照合して最終決定
3. **推奨は参考**: graph-context の推奨はあくまで参考。ユーザーの明示的な意図が優先

例:
- graph-context: 保有銘柄 → health 推奨
- ユーザー: 「7203.Tの最新ニュースは？」
- 最終判断: ユーザーの意図（ニュース）優先 → `/market-research stock 7203.T`
  ただし「保有銘柄である」という情報はコンテキストとして活用

## 前提知識統合原則 (KIK-466)

スクリプト実行後、`get_context.py` の出力（Neo4j知識）とスキル出力（数値データ）を統合して回答を構成する。
数値を並べるだけでなく、蓄積された文脈を踏まえた**解釈**を加える。

### 5つの統合ルール

1. **数値だけを並べない** — PER 8.5倍 → 「前回レポート時の12.3倍から大幅低下。業績悪化か割安化か要確認」
2. **過去との差分を示す** — 前回データがあれば必ず比較コメントを付ける（改善/悪化/横ばい）
3. **投資メモを参照する** — 懸念メモ・テーゼ・ターゲットがあれば回答に織り込む（「懸念メモ: 中国リスク → 最新ニュースで改善兆候」等）
4. **売買履歴を活用する** — BOUGHT/SOLD 記録があれば保有者視点のコメントを付加（「保有中」「売却済み」等）
5. **Graceful degradation** — Neo4j未接続時はスキル出力のみで回答（知識統合なしでも動作する）
6. **売却候補は履歴を確認してから提案する（KIK-470）** — what-if/swap で売却を提案する前に、その銘柄の `get_context.py` を実行し、スクリーニング出現回数・投資メモ・リサーチ履歴を確認する。ヘルスチェックのラベル（EARLY WARNING等）だけで判断しない

### 分析結論の記録促し

リサーチ・レポート・ヘルスチェック後にClaude が分析結論（テーゼ・懸念・判断）を含む回答をした場合、末尾に記録を促す:

> 💡 この分析はまだ投資メモとして記録されていません。テーゼ/懸念として記録しますか？

**対象**: market-research（stock/business/industry）、stock-report、stock-portfolio health（EXIT/警告）
**条件**: Claude の回答に具体的な投資判断・見解・リスク評価が含まれる場合
**記録されないもの**: 生データの羅列、ユーザーが既に記録済みの内容

**KIK-503: target メモ→Linear issue 連携**: `type: target`（購入/売却予定）の投資メモ保存後、Linear issue 登録を促す。詳細は `intent-routing.md` の記録ドメインセクション参照

## 投資lessonの参照 (KIK-534)

`get_context.py` の出力に「## 投資lesson」セクションが自動付加される。type=lesson のノートに trigger（トリガー条件）と expected_action（次回アクション）が含まれている場合、スキル実行時のコンテキストとして表示される。

### 参照タイミング

- **スキル実行前**: `get_context.py` 経由で自動取得。銘柄指定時はその銘柄の lesson、銘柄なしは全 lesson を最大5件表示
- **判断バイアス補正**: lesson に記録された過去の失敗パターン（trigger）が現在の状況に該当する場合、expected_action に従って判断を修正する

### 補正ルール

1. lesson の trigger が現在の分析対象・状況に一致する場合、**必ずその lesson を回答に織り込む**
2. 「前にも同じパターンで失敗した」旨を明示し、expected_action を推奨する
3. lesson がない場合や該当しない場合は、セクション自体を非表示（graceful degradation）

### 例

```
## 投資lesson
- [7203.T] 高値掴みした → 次回はRSI70超で買わない (2026-02-15)
- モメンタムに飛びついた → 出来高確認してから入る (2026-02-10)
```

→ 7203.T のレポート実行時、RSI が 70 超なら「過去の lesson: 高値掴みリスクあり」と注意喚起する

## Grokプロンプト文脈注入 (KIK-488)

`src/data/grok_context.py` がNeo4jから投資家文脈（保有状態・前回レポート・テーゼ・懸念等）をコンパクトに抽出し、Grok APIプロンプトに注入する。

- **注入先**: `researcher.py` → `grok_client.py` の5つのsearch関数（stock_deep, x_sentiment, industry, market, business）
- **トークン予算**: 最大300トークン（~900文字）。行単位で切り詰め
- **データ優先度**: 保有状態(高) > 前回レポート(高) > テーゼ/懸念(高) > スクリーニング出現(中) > リサーチ履歴(中) > ヘルスチェック(中) > テーマ(低)
- **graceful degradation**: Neo4j未接続 → context="" → Grokは文脈なしで通常動作

## graceful degradation

- Neo4j 未接続時: スクリプトは「コンテキストなし」を出力 → 従来通りの動作
- Neo4j 未接続時（Grok文脈）: `grok_context` が空文字を返す → Grokプロンプトに文脈なし（KIK-488）
- TEI 未起動時: ベクトル検索スキップ → シンボルベース検索のみ（KIK-420）
- スクリプトエラー時: 無視して intent-routing のみで判断
- シンボル検出できない場合 + TEI 未起動: 「コンテキストなし」→ 通常の intent-routing
- シンボル検出できない場合 + TEI 起動中: ベクトル検索で関連ノードを取得可能（KIK-420）

## プロアクティブ提案 (KIK-435)

スキル実行後、蓄積知識に基づく次のアクションを提案する。

### 自動組み込み (KIK-465)

各スキルスクリプトに `print_context()` と `print_suggestions()` が組み込まれており、スキル実行時に自動的にコンテキスト取得・提案表示が行われる。手動で `get_context.py` や `suggest.py` を呼ぶ必要はない。

- 冒頭: `print_context()` でグラフコンテキストを自動取得・表示
- 末尾: `print_suggestions()` でプロアクティブ提案を自動表示
- 10秒タイムアウト（SIGALRM）
- Neo4j 未接続・エラー時は graceful degradation（出力なし、クラッシュしない）

### CLI ラッパー（手動実行用）

```bash
python3 scripts/suggest.py [--symbol <ticker>] [--sector <sector>]
```

- 提案は最大 3 件。urgency: high（赤信号） > medium（要確認） > low（参考）

**トリガー種別:**

| 種別 | トリガー条件 | urgency |
|:---|:---|:---|
| 時間 | ヘルスチェック >14日未実施 | medium（>30日は high） |
| 時間 | テーゼメモ >90日経過 | medium |
| 時間 | 決算イベントが 7日以内 | high |
| 状態 | 同銘柄がスクリーニングで 3回以上上位 | medium |
| 状態 | 懸念メモが記録済み | medium |
| コンテキスト | リサーチセクターが保有銘柄と一致 | low |
| コンテキスト | 実行結果にキーワード一致（決算・利上げ・EXIT等） | low |
