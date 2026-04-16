# Intent Routing: 自然言語インターフェース

このシステムは自然言語で話しかけるだけで、適切なスキルを自動判定して実行する。
ユーザーはコマンド名を知る必要はない。

## 原則

1. **ユーザーの意図を最優先で汲み取る** — キーワードマッチではなく、文脈から意図を推論する
2. **曖昧なときは確認する** — 複数のスキルが該当しそうな場合、短く選択肢を提示する
3. **会話の流れを引き継ぐ** — 直前に扱った銘柄やPFの状態を覚えて、省略された情報を補完する
4. **必要なら複数スキルを連鎖する** — 1つの発言に複数の意図が含まれていれば順番に実行する
5. **グラフコンテキストを活用する** — `graph-context.md` のルールに従い、スキル実行前に過去の経緯を取得して判断材料にする

---

## Step 1: ドメイン判定

ユーザーの発言を、まず8つのドメインのどれかに分類する。

| ドメイン | 意図 | 代表的な表現 |
|:---|:---|:---|
| **発見** | 新しい銘柄を探したい | 探す、スクリーニング、いい株、おすすめ、割安株、高配当株 |
| **分析** | 特定の銘柄・業界・市場を知りたい | 〇〇ってどう、調べて、分析、リサーチ、ニュース |
| **保有管理** | 持ち株について操作・確認したい | PF、ポートフォリオ、買った、売った、損益、ヘルスチェック |
| **リスク** | リスクや将来を評価したい | 暴落、ストレス、リスク、怖い、ヘッジ |
| **監視** | 気になる銘柄を記録したい | ウォッチ、気になる、監視 |
| **記録** | 投資判断をメモしたい | メモ、ノート、記録、テーゼ、学び、懸念、lesson |
| **知識** | 過去の分析結果を検索したい | 前回、以前、履歴、常連銘柄、繰り返し、市況 |
| **プランモード** | プランを立ててから実行したい | プランモードで、プランで、プラン立てて、計画して実行 |
| **メタ** | システム自体について知りたい | 何ができる、機能一覧、改善、カイゼン |

---

## Step 2: ドメイン内でスキルを選択

### 発見ドメイン → `/screen-stocks`

```
「いい日本株ある？」      → /screen-stocks japan alpha
「米国の高配当株を探して」  → /screen-stocks us high-dividend
「押し目の銘柄」          → /screen-stocks japan pullback
「Xで話題の銘柄は？」     → /screen-stocks japan trending
「長期で持てる株」        → /screen-stocks japan long-term
「テクノロジーの割安株」   → /screen-stocks japan value --sector Technology
「AI関連の割安株」        → /screen-stocks us --theme ai --preset value
「半導体の成長株」        → /screen-stocks us --theme ai --preset high-growth
「防衛関連株を探して」    → /screen-stocks us --theme defense --preset alpha
「売られすぎの株」        → /screen-stocks japan contrarian
「逆張りで拾えそうな株」   → /screen-stocks japan contrarian
「過剰に売られてる銘柄」   → /screen-stocks japan contrarian
「急騰銘柄」              → /screen-stocks japan momentum
「ブレイクアウト検出」    → /screen-stocks japan momentum
「モメンタム銘柄」        → /screen-stocks japan momentum
```

**KIK-452 GraphRAG コンテキスト**: スクリーニング結果の末尾に、Neo4j ナレッジグラフから取得したセクタートレンド・投資メモ・テーマ情報が構造化データとして自動表示される（Neo4j 接続時のみ）。Claude Code LLM がこの構造化データを解釈して統合サマリーを生成する（KIK-532: Grok API 呼び出しを廃止）。Neo4j 未接続の場合はこのセクションは非表示となり、スクリーニング本体の動作には影響しない。

**region 推定**: 日本/JP → japan, 米国/US → us, ASEAN → asean, シンガポール → sg, 香港 → hk, 韓国 → kr, 台湾 → tw, 中国 → cn, 指定なし → japan

**preset 推定**:

| ユーザーの表現 | preset |
|:---|:---|
| いい株、おすすめ、有望 | alpha |
| 割安、バリュー、PER低い | value |
| 高配当、配当がいい | high-dividend |
| 成長、グロース、純成長、高成長、成長率重視 | growth |
| 成長バリュー、成長＋割安、成長性と割安度 | growth-value |
| 超割安、ディープバリュー | deep-value |
| クオリティ、高品質 | quality |
| 押し目、調整中、下がってるけど良い株 | pullback |
| トレンド、話題、Xで話題、SNS、バズ | trending |
| 長期、じっくり、安定成長、バイ＆ホールド | long-term |
| 還元、株主還元、自社株買い、バイバック、総還元 | shareholder-return |
| 安定して還元、継続的に高還元、還元が続いてる | shareholder-return（✅/📈 銘柄を推奨） |
| 爆発的成長、ハイグロース、利益不問の成長株、赤字成長株、PSR重視、売上急成長 | high-growth |
| 小型成長株、マイクロキャップ、10倍株、小型グロース、テンバガー候補、小型急成長 | small-cap-growth |
| 逆張り、売られすぎ、過剰反応、底打ち、リバウンド狙い、反発狙い | contrarian |
| 急騰、ブレイクアウト、モメンタム、勢い、上昇トレンド強気 | momentum |
| 市場の期待株、PER高くても成長してる株、成長プレミアム、ハイPER成長 | market-darling |
| 指定なし | alpha |

**KIK-439 関連（テーマスクリーニング）**:
- テーマ + プリセット: `--theme <テーマ>` をプリセットと組み合わせて使用
- 「AI株」「半導体」「AI関連」「AI銘柄」→ `--theme ai`
- 「EV」「電気自動車」「次世代自動車」→ `--theme ev`
- 「クラウド」「SaaS」→ `--theme cloud-saas`
- 「サイバーセキュリティ」「セキュリティ株」→ `--theme cybersecurity`
- 「バイオ」「創薬」「バイオテック」→ `--theme biotech`
- 「再エネ」「太陽光」「再生可能エネルギー」→ `--theme renewable-energy`
- 「防衛」「軍需」「航空宇宙」→ `--theme defense`
- 「フィンテック」「金融テック」→ `--theme fintech`
- 「ヘルスケア」「医療機器」「医療」→ `--theme healthcare`
- 組み合わせ例: 「AI関連で割安株」→ `--theme ai --preset value`、「半導体の成長株」→ `--theme ai --preset high-growth`
- `trending`/`pullback`/`alpha` プリセットは `--theme` 未対応（他のプリセットのみ）

**KIK-440 関連（トレンドテーマ自動検出）**:
- 「今熱いテーマは？」「トレンドテーマ」「注目セクター」 → `--auto-theme`（Grokでテーマ自動検出）
- 「今どのセクターが熱い？」 → `--auto-theme`（テーマ一覧 + スクリーニング）
- 「今の相場で何を買えばいい？」 → `--auto-theme`（テーマ検出 + デフォルトpreset）
- 「トレンドテーマで割安株」 → `--auto-theme --preset value`
- 「注目テーマの成長株」 → `--auto-theme --preset high-growth`
- `--auto-theme` と `--theme` は排他（同時使用不可）
- `--auto-theme` は `trending`/`pullback`/`alpha` プリセットと非対応
- `XAI_API_KEY` 必須（Grok API でテーマ検出）
- 違い: `trending` = X上の話題の**個別銘柄**を検出、`--auto-theme` = トレンドの**テーマ・セクター**を検出して各テーマで質の高い銘柄を探す

### 分析ドメイン → `/stock-report` or `/market-research`

**判定基準**: 数値分析か定性分析か

| ユーザーの意図 | スキル | 判断基準 |
|:---|:---|:---|
| バリュエーション、割安度、PER/PBR、還元率 | `/stock-report` | 数値ベースの分析 |
| 最新ニュース、センチメント、深掘り分析 | `/market-research stock` | 定性的な深掘り |
| 業界の動向、トレンド | `/market-research industry` | 業界名・テーマが対象 |
| マーケット概況、相場の状況 | `/market-research market` | 市場全体が対象 |
| 市況チェック、温度感、VIX、F&G、金利推移、イールドカーブ | 定量+定性 同時実行 | 下記KIK-567参照 |
| ビジネスモデル、事業構造、セグメント、収益構造、何で稼いでる | `/market-research business` | 事業の仕組みが対象 |
| 過去の分析結果、前回のレポート、以前のスクリーニング | `/graph-query` | 過去データの参照（知識ドメインへ連携） |
| 似た銘柄、類似銘柄、関連銘柄、同じグループ | `/graph-query` | コミュニティ検索（KIK-547） |

**迷ったとき**:
- 「〇〇ってどう？」「〇〇を調べて」 → `/stock-report`（まず数値から）
- 「〇〇を深掘りして」「〇〇の最新情報」「〇〇のニュース」 → `/market-research stock`
- 「〇〇のビジネスモデル」「〇〇は何で稼いでる？」「事業構造を教えて」 → `/market-research business`
- 「〇〇について詳しく」 → 両方実行して統合レポート

**KIK-567 関連（市況チェック — 定量+定性）**:
- 「市況チェック」「相場の温度感」「VIXは？」「F&Gは？」「金利の推移」「イールドカーブ」 → 2つ同時実行:
  1. `python3 scripts/market_dashboard.py`（定量: VIX/F&G/金利/イールドカーブ）
  2. `/market-research market`（定性: Grokでニュース・センチメント）
  → Claude が両方の出力を統合して回答
- 「VIXだけ見せて」「金利の推移」 → `python3 scripts/market_dashboard.py` のみ（定量だけ）
- 「市況ニュース」「最新の相場観」 → `/market-research market` のみ（定性だけ）

**KIK-375 関連**:
- 「還元率」「自社株買い」「株主還元」「トータルリターン」 → `/stock-report`（株主還元セクションで表示）

**KIK-380 関連**:
- 「過去の還元率」「3年間の還元推移」「還元のトレンド」 → `/stock-report`（3年還元率履歴で表示）

**KIK-383 関連**:
- 「安定的に還元している株」「継続高還元」 → `/screen-stocks --preset shareholder-return`（安定度マーク付き）
- 「一時的な高還元？」「本当に還元が続く？」 → `/stock-report`（安定度評価で表示）
- スクリーニング結果の ⚠️ マーク銘柄は一時的高還元の可能性あり

**KIK-469 関連（ETF対応）**:
- 「VGKってどう？」「SPYを調べて」「このETFの経費率は？」 → `/stock-report`（ETF自動検出 → ETF専用レポート）
- ETFの場合、PER/PBR/ROEの代わりに経費率・AUM・ファンド規模を表示
- ヘルスチェックでもETF固有の評価（経費率ラベル・AUMラベル）を表示

### 保有管理ドメイン → `/stock-portfolio`

**KIK-596 関連（投資判断マルチエージェント）**:
- 入替提案、新規購入判断、売却判断、リバランス、調整アドバイスの**実行**を伴う発言には、`.claude/rules/plan-check.md` の Plan→Execute→Review フローを適用する
- 「PF見せて」「損益は？」等の情報照会や、「買った」「売った」等の記録は対象外
- 判定: 文末が「〜したい」「〜すべき？」「〜探して」「〜直して」等の行動要求であること
- 最初に `python3 scripts/extract_constraints.py "<ユーザー入力>"` を実行し、lessonから制約条件を抽出してからプランを策定する

**サブコマンド判定**:

| ユーザーの意図 | コマンド |
|:---|:---|
| **現況確認**: PF見せて、損益、スナップショット | `snapshot` |
| **売買記録**: 〇〇を買った/売った | `buy` / `sell` |
| **一覧表示**: 銘柄一覧、リスト、CSV | `list` |
| **構造分析**: 偏り、集中度、HHI、セクター比率、規模別構成、大型小型比率 | `analyze` |
| **健全性**: ヘルスチェック、利確判断、損切り、まだ持つべき？、小型株比率、小型株アロケーション | `health` |
| **将来予測**: 期待リターン、利回り、今後の見通し、forecast | `forecast` |
| **リバランス**: バランス改善、配分調整、偏り直したい | `rebalance` |
| **シミュレーション**: 〇年後、複利、積立、老後、目標額 | `simulate` |
| **過去検証**: バックテスト、検証、過去の成績 | `backtest` |
| **What-If**: 追加したら、買ったらどうなる、影響、シミュレーション追加 | `what-if` |
| **パフォーマンスレビュー**: 売買成績、勝率、損益統計、何%取れた | `review` |
| **調整アドバイス**: 何を売るべき？、どう直す？、具体的に何をすべき？、処方箋、調整プラン、どうしたらいい、アドバイス、改善して、直して、対策、手を打って、アクションプラン、次のアクション、問題点と対策 | `adjust` |
| **売買→記録**: 買った理由を記録したい、投資理由をメモ | `buy` → `/investment-note save --type thesis` |
| **損切り→学び**: 損切りの学びを記録、反省メモ | `sell` → `/investment-note save --type lesson` |

**KIK-376 関連**:
- 「〇〇を追加したらどうなる？」「〇〇を買ったらPFどう変わる？」「影響は？」 → `what-if`
- 形式: `what-if --add "SYMBOL:SHARES:PRICE,..."` 例: `what-if --add "7203.T:100:2850,AAPL:10:250"`

**KIK-451 関連（スワップシミュレーション）**:
- 「〇〇を売って△△を買ったら？」「入れ替えたらどうなる？」「乗り換えシミュレーション」 → `what-if --remove --add`
- 「〇〇を売ったら資金はいくら？」「売却シミュレーション」「〇〇を手放したらPFがどう変わる？」 → `what-if --remove`
- 形式:
  - スワップ: `what-if --remove "SYMBOL:SHARES,..." --add "SYMBOL:SHARES:PRICE,..."`
  - 売却のみ: `what-if --remove "SYMBOL:SHARES,..."`（価格不要・時価で試算）
- 例: `what-if --remove "7203.T:100" --add "9984.T:50:7500"`
- スワップ出力: 売却代金試算 / 資金収支（差額） / 売却銘柄ヘルスチェック / 「このスワップは推奨」等の判定

**KIK-374 関連**:
- 「ゴールデンクロス」「デッドクロス」「クロス」 → `health`（クロスイベント検出で表示）

**KIK-381 関連**:
- 「バリュートラップ」「割安罠」「見せかけの割安」 → `health`（バリュートラップ検出で表示）
- `/stock-report` でも個別銘柄のバリュートラップ判定を表示

**KIK-403 関連**:
- 「還元安定度」「一時的高還元」「還元が続くか」 → `health`（還元安定度評価で表示）
- ヘルスチェックで一時的高還元（⚠️）は早期警告に昇格
- 長期適性判定に総還元率（配当+自社株買い）を使用

**KIK-438 関連（小型株アロケーション）**:
- 「小型株比率」「小型株アロケーション」「小型株の割合」「小型株多すぎ？」 → `health`（小型株比率サマリーで表示）
- 「規模別構成」「大型小型の比率」「時価総額バランス」 → `analyze`（規模別構成テーブルで表示）
- ヘルスチェックで小型株は `[小型]` バッジ付き + EARLY_WARNING→CAUTION自動昇格
- PF全体の小型株比率: >25% 警告、>35% 危険

**buy/sell の自然言語変換**:
- 「トヨタを100株 2850円で買った」→ `buy --symbol 7203.T --shares 100 --price 2850 --currency JPY`
- 「AAPLを5株売った」→ `sell --symbol AAPL --shares 5`
- 「NVDAを5株138ドルで売った」→ `sell --symbol NVDA --shares 5 --price 138`
- 企業名はティッカーシンボルに変換する

**KIK-444: buy/sell 確認ステップ**:
- `--yes` なしで実行すると確認プレビューが表示されコマンドは終了する（記録はされない）
- 確認後「記録して」「OK」「はい」→ `buy --yes` / `sell --yes` で再実行
- 「確認なしで記録して」「そのままいれて」→ 最初から `--yes` を付けて実行

**KIK-441: 売却価格の確認フロー**:
- 「売った」と言ってきた場合、価格が未指定なら確認する: 「売却単価を教えてもらえますか？実現損益を記録できます。（スキップしてもOK）」
- 価格あり → `sell --symbol ... --shares ... --price <価格>` 実行
- スキップ → `sell --symbol ... --shares ...` 実行（価格なし）

**KIK-441: review コマンドの自然言語変換**:
- 「売買成績を見たい」「勝率は？」「損益統計」「何%取れた？」 → `review`
- 「今年の成績」 → `review --year <今年>`
- 「NVDAの売買成績」 → `review --symbol NVDA`

**KIK-568: adjust の自然言語判定**:
- 「PFどうしたらいい？」「PFのアドバイス」「PFを改善して」「PFの対策」「手を打って」→ `adjust`（health未実行でも直接実行）
- health との判定基準: 「改善」「対策」「アドバイス」「直す」「どうしたらいい」「どうすべき」「アクション」→ adjust優先。「チェック」「確認」「診断」「大丈夫？」→ health

**rebalance の戦略推定**:
- 「リスクを抑えたい」→ `--strategy defensive`
- 「攻めたい」→ `--strategy aggressive`
- 「テック偏重を直したい」→ `--reduce-sector Technology`

**simulate のパラメータ推定**:
- 「5年後にいくら？」→ `--years 5`
- 「月10万追加して3年後に2000万いける？」→ `--years 3 --monthly-add 100000 --target 20000000`

### リスクドメイン → `/stress-test`

```
「暴落したらどうなる？」     → /stress-test（PFから銘柄を自動取得）
「円安リスクは？」          → /stress-test --scenario ドル高円安
「テック暴落に耐えられる？」  → /stress-test --scenario テック暴落
```

**PFとの連携**: ポートフォリオが存在する場合、銘柄リストを自動取得して実行する

**シナリオ推定**: トリプル安、ドル高円安、米国リセッション、日銀利上げ、米中対立、インフレ再燃、テック暴落、円高ドル安 + カスタム

### 監視ドメイン → `/watchlist`

```
「気になるから記録しておいて」 → /watchlist add
「ウォッチリスト見せて」      → /watchlist list
```

### 記録ドメイン → `/investment-note`

```
「トヨタについてメモしておいて」      → /investment-note save --symbol 7203.T
「投資テーゼを記録」                → /investment-note save --type thesis
「学びを残す」                     → /investment-note save --type lesson
「PF全体のメモ」「ポートフォリオの振り返り」 → /investment-note save --category portfolio --type review
「市況メモ」「マクロの気づき」       → /investment-note save --category market --type observation
「メモ一覧」                       → /investment-note list
「AAPLのメモ」                    → /investment-note list --symbol AAPL
「PFのメモ」                      → /investment-note list --category portfolio
「メモ削除」                       → /investment-note delete --id NOTE_ID
「日記」「投資日記」「今日の振り返り」     → /investment-note save --type journal
「今週はトレードしない」「ノートレード」    → /investment-note save --type journal --content ...
「雑感」「つぶやき」                     → /investment-note save --type journal
```

**タイプ推定**:

| ユーザーの表現 | type |
|:---|:---|
| テーゼ、仮説、投資理由 | thesis |
| 気づき、観察 | observation |
| 懸念、心配、リスク | concern |
| 振り返り、レビュー | review |
| 目標株価、ターゲット | target |
| 学び、反省、教訓 | lesson |
| 損切りライン、利確ライン、ストップロス、テイクプロフィット、exit基準 | exit-rule |
| 日記、ジャーナル、振り返り日記、フリーメモ、雑感、つぶやき | journal |

**KIK-503: target メモ保存後の Linear issue 登録促し**:

`/investment-note save --type target` 実行後、末尾に以下の促しメッセージを表示する:

> 📋 この予定を Linear issue にも登録しますか？（Investment Checkpoints プロジェクト）

- ユーザーが「はい」「登録して」→ MCP (`mcp__claude_ai_Linear__create_issue`) で issue 作成
  - team: `Kikuchi`
  - project: `Investment Checkpoints`
  - title: メモ内容から要約（例: 「7203.T 購入検討 - 目標株価 3000円」）
  - description: メモの全文
  - priority: 3 (Normal)
- ユーザーが「不要」「スキップ」→ 何もしない
- **対象は `target` タイプのみ**。thesis/concern/review/lesson/journal/observation では促さない

### 知識ドメイン → `/graph-query`

```
「7203.Tの前回レポートは？」        → /graph-query "7203.Tの前回レポート"
「繰り返し候補に上がってる銘柄は？」  → /graph-query "繰り返し候補"
「AAPLのリサーチ履歴」              → /graph-query "AAPLのリサーチ履歴"
「最近の市況は？」                  → /graph-query "市況"
「7203.Tの取引履歴」               → /graph-query "7203.Tの取引履歴"
「NVDAのニュース履歴」              → /graph-query "NVDAのニュース履歴"
「NVDAのセンチメント推移」           → /graph-query "NVDAのセンチメント推移"
「NVDAのカタリスト」                → /graph-query "NVDAのカタリスト"
「7203.TのPER推移」                → /graph-query "7203.TのPER推移"
「今後のイベント」                  → /graph-query "今後のイベント"
「マクロ指標の推移」                → /graph-query "マクロ指標の推移"
「前回のストレステスト結果」          → /graph-query "ストレステスト履歴"
「フォーキャストの推移」             → /graph-query "フォーキャスト推移"
「前回の見通し」                    → /graph-query "前回の見通し"
「アクションアイテム」               → /graph-query "アクションアイテム"
「タスク一覧」                      → /graph-query "アクションアイテム"
「やるべきこと」                    → /graph-query "アクションアイテム"
「7203.Tのアクション」              → /graph-query "7203.Tのアクションアイテム"
「7203.Tに似た銘柄は？」            → /graph-query "7203.Tのコミュニティ"
「類似銘柄を見せて」                → /graph-query "銘柄コミュニティ"
「同じグループの株」                → /graph-query "コミュニティ"
「関連銘柄」                        → /graph-query "コミュニティ"
「銘柄の共通点」                    → /graph-query "銘柄の関係性"
```

**判定**: 「前回」「以前」「履歴」「常連」「繰り返し」「市況コンテキスト」「ニュース」「センチメント」「カタリスト」「材料」「バリュエーション推移」「イベント」「指標」「ストレステスト結果」「フォーキャスト推移」「見通し」「アクションアイテム」「タスク」「やるべきこと」「似た銘柄」「類似銘柄」「関連銘柄」「コミュニティ」「同じグループ」「クラスタ」などの過去データ・関係性検索意図

### プランモードドメイン → `/plan-execute` (KIK-600)

「プランモードで」「プランで」「プラン立てて」等の発言があった場合、`/plan-execute` スキルを起動する。

- プランモードはすべてのドメインと組み合わせ可能
- 「PFをチェックして、プランモードで」→ /plan-execute（PFチェックのプランを設計→実行）
- 「トヨタを調べて、プランで」→ /plan-execute（調査プランを設計→実行）
- 「PFを改善して、プランモードで」→ /plan-execute → Plan-Checkにエスカレーション

**注意**: スキルを直接指定した場合（`/stock-report 7203.T` 等）はプランニングをスキップして即実行する。

### メタドメイン — システム自体への質問

ユーザーがスキルの使い方やシステムの機能について聞いてきた場合、以下を参照して回答する。

**「何ができるの？」「機能一覧」「使い方」**:

```
このシステムは自然言語で以下のことができます:

🔍 銘柄を探す
  「いい日本株ある？」「米国の高配当株を探して」「Xで話題の株」
  → 14の戦略 × 60地域からスクリーニング

📊 銘柄を分析する
  「トヨタってどう？」「AAPLの還元率は？」
  → バリュエーション・割安度・株主還元率
  → 3年間の株主還元率推移（配当+自社株買い）
  → バリュートラップ判定（低PER+利益減少の警告）

📰 深掘りリサーチ
  「半導体業界を調べて」「今の相場は？」
  → Grok API で最新ニュース・Xセンチメント・業界動向

💼 ポートフォリオ管理
  「PF見せて」「トヨタ100株買った」「ヘルスチェック」
  → 損益表示・売買記録・構造分析・健全性チェック
  → ゴールデンクロス/デッドクロス検出
  → バリュートラップ検出（低PER+利益減少の警告）
  → 株主還元安定度評価（✅安定/📈増加/⚠️一時的/📉低下）
  → 小型株アロケーション監視（[小型]バッジ・比率警告・感度引き上げ）
  → 推定利回り・リバランス・複利シミュレーション

⚡ リスク分析
  「暴落したらどうなる？」「円安リスクは？」
  → 8シナリオ × 相関分析 × VaR × 推奨アクション

👀 ウォッチリスト
  「気になるから記録して」「監視リスト見せて」

📝 投資メモ
  「トヨタについてメモ」「学びを記録」「メモ一覧」
  → 投資テーゼ・懸念・学びをノートとして記録・参照

🔎 知識グラフ検索
  「前回のレポートは？」「常連銘柄は？」「最近の市況は？」
  → 過去の分析・スクリーニング・取引履歴を自然言語で検索
```

**「改善点ある？」「カイゼン」「システムの弱点」**:

以下の観点でシステムを分析し、改善提案を出力する:
1. 全 SKILL.md ファイルを読み込み、カバー範囲と実装状況を確認
2. `src/core/` のモジュール一覧と、各スキルからの利用状況を照合
3. テストカバレッジの薄い箇所を特定
4. intent-routing のキーワード漏れを検出
5. Linear の未完了 issue を確認
6. 改善提案をカテゴリ（新機能/UX改善/バグ修正/ドキュメント）× 優先度（High/Medium/Low）で整理

提案に同意があれば Linear issue を作成する。

---

## コンテキスト引き継ぎルール

直前の会話で特定の銘柄や操作結果が出ている場合、省略された情報を補完する。

| 直前のアクション | ユーザーの発言 | 推論 |
|:---|:---|:---|
| `/stock-report 7203.T` を実行 | 「ウォッチリストに入れて」 | → `/watchlist add <list> 7203.T` |
| `/stock-report 7203.T` を実行 | 「もっと詳しく」 | → `/market-research stock 7203.T` |
| `/stock-report 7203.T` を実行 | 「ストレステストして」 | → `/stress-test --portfolio 7203.T` |
| `/screen-stocks` の結果表示後 | 「1位の銘柄を調べて」 | → `/stock-report <1位のシンボル>` |
| `/stock-portfolio health` で EXIT | 「代わりを探して」 | → `/screen-stocks`（同セクター/リージョンで） |
| `/stock-portfolio forecast` 実行後 | 「シミュレーションも見たい」 | → `/stock-portfolio simulate` |
| `/stock-portfolio health` でバリュートラップ検出 | 「詳しく見たい」 | → `/stock-report <該当銘柄>` |
| `/screen-stocks shareholder-return` で ⚠️ 表示 | 「⚠️の銘柄を詳しく」 | → `/stock-report <該当銘柄>` |
| `/screen-stocks shareholder-return` 結果表示後 | 「安定してるやつだけ見たい」 | → 結果から ✅/📈 のみフィルタ |
| `/stock-portfolio buy` で購入記録 | 「メモしておいて」「投資理由を記録」 | → `/investment-note save --symbol <銘柄> --type thesis --content ...` |
| `/stock-portfolio health` で EXIT 判定 | 「学びを記録」「反省メモ」 | → `/investment-note save --symbol <銘柄> --type lesson --content ...` |
| `/stock-portfolio health` で EXIT 判定 | 「具体的にどうすれば？」「処方箋出して」「どうしたらいい」「改善して」「アドバイス」 | → `/stock-portfolio adjust` |
| `/stock-portfolio health` で EXIT 判定 | 「売って乗り換えたい」「代替を買ったらどうなる？」 | → `what-if --remove "<EXIT銘柄>:SHARES" --add "<代替>:SHARES:PRICE"` |
| `what-if --remove` 実行後 | 「代替を探して」「乗り換え先を調べて」 | → `/screen-stocks`（同セクターで） |
| `/graph-query` で過去レポート表示 | 「最新も見たい」「今はどう？」 | → `/stock-report <銘柄>` |
| `/investment-note list` でメモ表示 | 「この銘柄を調べて」 | → `/stock-report <銘柄>` |
| `/stock-report` でレポート生成 | 「懸念をメモしておいて」 | → `/investment-note save --symbol <銘柄> --type concern --content ...` |
| `/screen-stocks` の結果表示後 | 「前にも出てきた？」「繰り返し候補？」 | → `/graph-query "よく出る銘柄"` |
| `/stock-report 7203.T` を実行 | 「似た銘柄は？」「同じグループの株」 | → `/graph-query "7203.Tのコミュニティ"` |
| `/stock-portfolio health` でコミュニティ集中警告 | 「どう直す？」「分散化したい」 | → コミュニティメンバー確認 → 別コミュニティの代替候補を提案 |

---

## 複合意図の自動連鎖

1つの発言に複数の意図が含まれる場合、適切な順序で実行して結果を統合する。

**パターンは固定しない** — 以下は代表例であり、ユーザーの意図に応じて柔軟に組み合わせる。

### 診断 → 対策
```
「PFのリスクを確認して、やばい銘柄があれば代わりを探して」
→ 1. /stock-portfolio health
→ 2. EXIT 銘柄があれば /screen-stocks で代替候補を検索
→ 3. 代替候補が見つかったら what-if --remove "<EXIT銘柄>:SHARES" --add "<代替>:SHARES:PRICE" を必ず実行してから提案（KIK-450）
```

### 売買 → 確認
```
「トヨタ100株買った、バランス見て」
→ 1. /stock-portfolio buy
→ 2. /stock-portfolio analyze
```

### 全体診断
```
「総合的にPFチェックして」
→ 1. /stock-portfolio snapshot（現況）
→ 2. /stock-portfolio health（健全性）
→ 3. /stock-portfolio forecast（見通し）
→ 4. 問題があれば /stock-portfolio rebalance で改善案
```

### リサーチ → 投資判断
```
「半導体業界を調べて、有望な銘柄を探して」
→ 1. /market-research industry 半導体
→ 2. /screen-stocks --sector Technology
```

### 市場確認 → PF判断
```
「今の相場状況を確認して、PF大丈夫か見て」
→ 1. /market-research market
→ 2. /stock-portfolio health
→ 3. 市場環境を踏まえた判断を補足
```

### 見通し → 将来予測
```
「PFの見通しを確認して、5年後のシミュレーションも」
→ 1. /stock-portfolio forecast
→ 2. /stock-portfolio simulate --years 5
```

### 売買 → 記録
```
「トヨタ100株買った、理由もメモして」
→ 1. /stock-portfolio buy --symbol 7203.T --shares 100 --price ...
→ 2. /investment-note save --symbol 7203.T --type thesis --content ...
```

### リサーチ → 記録
```
「トヨタを調べて、気になる点をメモして」
→ 1. /stock-report 7203.T
→ 2. /investment-note save --symbol 7203.T --type observation --content ...
```

### 知識グラフ → 最新分析
```
「前に調べた銘柄の最新状況を確認して」
→ 1. /graph-query "前に調べた銘柄"
→ 2. 結果の銘柄に /stock-report を実行
```

---

## 曖昧な場合の対応

意図が不明確な場合は、選択肢を短く提示して確認する。

```
ユーザー: 「配当について」

→ どちらの意味ですか？
  1. 高配当銘柄を探す（スクリーニング）
  2. 特定銘柄の配当・還元率を確認する（レポート）
  3. PFの配当利回りを確認する（フォーキャスト）
```

```
ユーザー: 「バリュートラップじゃないか確認して」

→ 対象による:
  1. 保有銘柄全体 → /stock-portfolio health（バリュートラップ検出付き）
  2. 特定の銘柄 → /stock-report（個別バリュートラップ判定）
```

```
ユーザー: 「メモを見せて」

→ どちらの意味ですか？
  1. 特定銘柄のメモ → /investment-note list --symbol <銘柄>
  2. 全メモ一覧 → /investment-note list
  3. 過去の分析記録 → /graph-query "過去のレポート"
```

ただし、文脈から明らかに判断できる場合は確認せずに実行する。
