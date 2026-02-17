# Intent Routing: 自然言語インターフェース

このシステムは自然言語で話しかけるだけで、適切なスキルを自動判定して実行する。
ユーザーはコマンド名を知る必要はない。

## 原則

1. **ユーザーの意図を最優先で汲み取る** — キーワードマッチではなく、文脈から意図を推論する
2. **曖昧なときは確認する** — 複数のスキルが該当しそうな場合、短く選択肢を提示する
3. **会話の流れを引き継ぐ** — 直前に扱った銘柄やPFの状態を覚えて、省略された情報を補完する
4. **必要なら複数スキルを連鎖する** — 1つの発言に複数の意図が含まれていれば順番に実行する

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
```

**region 推定**: 日本/JP → japan, 米国/US → us, ASEAN → asean, シンガポール → sg, 香港 → hk, 韓国 → kr, 台湾 → tw, 中国 → cn, 指定なし → japan

**preset 推定**:

| ユーザーの表現 | preset |
|:---|:---|
| いい株、おすすめ、有望 | alpha |
| 割安、バリュー、PER低い | value |
| 高配当、配当がいい | high-dividend |
| 成長、グロース | growth-value |
| 超割安、ディープバリュー | deep-value |
| クオリティ、高品質 | quality |
| 押し目、調整中、下がってるけど良い株 | pullback |
| トレンド、話題、Xで話題、SNS、バズ | trending |
| 長期、じっくり、安定成長、バイ＆ホールド | long-term |
| 還元、株主還元、自社株買い、バイバック、総還元 | shareholder-return |
| 安定して還元、継続的に高還元、還元が続いてる | shareholder-return（✅/📈 銘柄を推奨） |
| 指定なし | alpha |

### 分析ドメイン → `/stock-report` or `/market-research`

**判定基準**: 数値分析か定性分析か

| ユーザーの意図 | スキル | 判断基準 |
|:---|:---|:---|
| バリュエーション、割安度、PER/PBR、還元率 | `/stock-report` | 数値ベースの分析 |
| 最新ニュース、センチメント、深掘り分析 | `/market-research stock` | 定性的な深掘り |
| 業界の動向、トレンド | `/market-research industry` | 業界名・テーマが対象 |
| マーケット概況、相場の状況 | `/market-research market` | 市場全体が対象 |
| ビジネスモデル、事業構造、セグメント、収益構造、何で稼いでる | `/market-research business` | 事業の仕組みが対象 |
| 過去の分析結果、前回のレポート、以前のスクリーニング | `/graph-query` | 過去データの参照（知識ドメインへ連携） |

**迷ったとき**:
- 「〇〇ってどう？」「〇〇を調べて」 → `/stock-report`（まず数値から）
- 「〇〇を深掘りして」「〇〇の最新情報」「〇〇のニュース」 → `/market-research stock`
- 「〇〇のビジネスモデル」「〇〇は何で稼いでる？」「事業構造を教えて」 → `/market-research business`
- 「〇〇について詳しく」 → 両方実行して統合レポート

**KIK-375 関連**:
- 「還元率」「自社株買い」「株主還元」「トータルリターン」 → `/stock-report`（株主還元セクションで表示）

**KIK-380 関連**:
- 「過去の還元率」「3年間の還元推移」「還元のトレンド」 → `/stock-report`（3年還元率履歴で表示）

**KIK-383 関連**:
- 「安定的に還元している株」「継続高還元」 → `/screen-stocks --preset shareholder-return`（安定度マーク付き）
- 「一時的な高還元？」「本当に還元が続く？」 → `/stock-report`（安定度評価で表示）
- スクリーニング結果の ⚠️ マーク銘柄は一時的高還元の可能性あり

### 保有管理ドメイン → `/stock-portfolio`

**サブコマンド判定**:

| ユーザーの意図 | コマンド |
|:---|:---|
| **現況確認**: PF見せて、損益、スナップショット | `snapshot` |
| **売買記録**: 〇〇を買った/売った | `buy` / `sell` |
| **一覧表示**: 銘柄一覧、リスト、CSV | `list` |
| **構造分析**: 偏り、集中度、HHI、セクター比率 | `analyze` |
| **健全性**: ヘルスチェック、利確判断、損切り、まだ持つべき？ | `health` |
| **将来予測**: 期待リターン、利回り、今後の見通し、forecast | `forecast` |
| **リバランス**: バランス改善、配分調整、偏り直したい | `rebalance` |
| **シミュレーション**: 〇年後、複利、積立、老後、目標額 | `simulate` |
| **過去検証**: バックテスト、検証、過去の成績 | `backtest` |
| **What-If**: 追加したら、買ったらどうなる、影響、シミュレーション追加 | `what-if` |
| **売買→記録**: 買った理由を記録したい、投資理由をメモ | `buy` → `/investment-note save --type thesis` |
| **損切り→学び**: 損切りの学びを記録、反省メモ | `sell` → `/investment-note save --type lesson` |

**KIK-376 関連**:
- 「〇〇を追加したらどうなる？」「〇〇を買ったらPFどう変わる？」「影響は？」 → `what-if`
- 形式: `what-if --add "SYMBOL:SHARES:PRICE,..."` 例: `what-if --add "7203.T:100:2850,AAPL:10:250"`

**KIK-374 関連**:
- 「ゴールデンクロス」「デッドクロス」「クロス」 → `health`（クロスイベント検出で表示）

**KIK-381 関連**:
- 「バリュートラップ」「割安罠」「見せかけの割安」 → `health`（バリュートラップ検出で表示）
- `/stock-report` でも個別銘柄のバリュートラップ判定を表示

**KIK-403 関連**:
- 「還元安定度」「一時的高還元」「還元が続くか」 → `health`（還元安定度評価で表示）
- ヘルスチェックで一時的高還元（⚠️）は早期警告に昇格
- 長期適性判定に総還元率（配当+自社株買い）を使用

**buy/sell の自然言語変換**:
- 「トヨタを100株 2850円で買った」→ `buy --symbol 7203.T --shares 100 --price 2850 --currency JPY`
- 「AAPLを5株売った」→ `sell --symbol AAPL --shares 5`
- 企業名はティッカーシンボルに変換する

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
「トヨタについてメモしておいて」  → /investment-note save --symbol 7203.T
「投資テーゼを記録」            → /investment-note save --type thesis
「学びを残す」                 → /investment-note save --type lesson
「メモ一覧」                   → /investment-note list
「AAPLのメモ」                → /investment-note list --symbol AAPL
「メモ削除」                   → /investment-note delete --id NOTE_ID
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

### 知識ドメイン → `/graph-query`

```
「7203.Tの前回レポートは？」        → /graph-query "7203.Tの前回レポート"
「繰り返し候補に上がってる銘柄は？」  → /graph-query "繰り返し候補"
「AAPLのリサーチ履歴」              → /graph-query "AAPLのリサーチ履歴"
「最近の市況は？」                  → /graph-query "市況"
「7203.Tの取引履歴」               → /graph-query "7203.Tの取引履歴"
```

**判定**: 「前回」「以前」「履歴」「常連」「繰り返し」「市況コンテキスト」などの過去データ検索意図

### メタドメイン — システム自体への質問

ユーザーがスキルの使い方やシステムの機能について聞いてきた場合、以下を参照して回答する。

**「何ができるの？」「機能一覧」「使い方」**:

```
このシステムは自然言語で以下のことができます:

🔍 銘柄を探す
  「いい日本株ある？」「米国の高配当株を探して」「Xで話題の株」
  → 9つの戦略 × 60地域からスクリーニング

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
| `/graph-query` で過去レポート表示 | 「最新も見たい」「今はどう？」 | → `/stock-report <銘柄>` |
| `/investment-note list` でメモ表示 | 「この銘柄を調べて」 | → `/stock-report <銘柄>` |
| `/stock-report` でレポート生成 | 「懸念をメモしておいて」 | → `/investment-note save --symbol <銘柄> --type concern --content ...` |
| `/screen-stocks` の結果表示後 | 「前にも出てきた？」「繰り返し候補？」 | → `/graph-query "よく出る銘柄"` |

---

## 複合意図の自動連鎖

1つの発言に複数の意図が含まれる場合、適切な順序で実行して結果を統合する。

**パターンは固定しない** — 以下は代表例であり、ユーザーの意図に応じて柔軟に組み合わせる。

### 診断 → 対策
```
「PFのリスクを確認して、やばい銘柄があれば代わりを探して」
→ 1. /stock-portfolio health
→ 2. EXIT 銘柄があれば /screen-stocks で代替候補を検索
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
