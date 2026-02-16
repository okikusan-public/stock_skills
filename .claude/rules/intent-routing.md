# Intent Routing: 自然言語 → スキル判定ルール

ユーザーがスキルコマンド（`/screen-stocks` 等）を明示せず自然言語で話しかけた場合、以下のルールで適切なスキルを判定し実行する。

## 判定テーブル

| ユーザーの意図・キーワード | 実行スキル | パラメータ推定 |
|:---|:---|:---|
| 割安、スクリーニング、探す、銘柄検索、いい株、おすすめ | `/screen-stocks` | region と preset を文脈から推定。デフォルト: japan, value。「いい日本株ある？」→ japan alpha |
| ポートフォリオ、PF、損益、持ち株、保有、一覧 | `/stock-portfolio snapshot` | |
| リスク、怖い、ヘッジ、分散、ストレス、暴落したら | `/stress-test` | PFから銘柄を自動取得。シナリオ名があればそれを使う |
| 健全性、利確、損切り、まだ持つべき？、アラート | `/stock-portfolio health` | |
| 期待値、利回り、今後の見通し、予想、見通し | `/stock-portfolio forecast` | |
| リバランス、配分、バランス、偏り、集中 | `/stock-portfolio rebalance` | 戦略を文脈から推定 |
| シミュレーション、複利、〇年後、将来、積立、老後、目標額 | `/stock-portfolio simulate` | years/monthly-add/target を文脈から推定 |
| 〇〇を調べて、〇〇の分析、〇〇ってどう？ | `/stock-report` | ティッカーシンボルを推定（例: トヨタ → 7203.T） |
| 買った、購入、〇〇株買った | `/stock-portfolio buy` | 銘柄・株数・価格を文脈から抽出 |
| 売った、売却、〇〇手放した | `/stock-portfolio sell` | 銘柄・株数を文脈から抽出 |
| ウォッチ、監視、気になる銘柄 | `/watchlist` | add/show/list を文脈から判定 |
| トレンド、話題の株、Xで話題、SNSで注目、バズ、Twitterで人気 | `/screen-stocks --preset trending` | region と theme を文脈から推定 |
| リサーチ、深掘り、詳しく調べて、最新情報、ニュース、業界動向、マーケット概況、相場 | `/market-research` | stock/industry/market を文脈から推定。ティッカーや企業名があれば stock、業界名やテーマがあれば industry、マーケットや指数名があれば market |

## region 推定ルール

| ユーザー入力 | region |
|:---|:---|
| 日本株、日本、JP | japan |
| 米国株、アメリカ、US | us |
| ASEAN、東南アジア | asean |
| シンガポール | sg |
| 香港 | hk |
| 韓国 | kr |
| 台湾 | tw |
| 指定なし | japan（デフォルト） |

## preset 推定ルール

| ユーザー入力 | preset |
|:---|:---|
| いい株、おすすめ、有望 | alpha |
| 割安、バリュー | value |
| 高配当、配当 | high-dividend |
| 成長、グロース | growth-value |
| 超割安、ディープバリュー | deep-value |
| 品質、クオリティ | quality |
| 押し目、調整中 | pullback |
| トレンド、話題、X、Twitter、SNS | trending |
| 長期、長期投資、じっくり、バイ＆ホールド、安定成長 | long-term |
| 還元、株主還元、自社株買い、バイバック、総還元 | shareholder-return |
| 指定なし | alpha（デフォルト） |

## 複合意図の処理

ユーザーが複数の意図を含む発言をした場合、順番に実行して結果を統合する。

### パターン1: 診断 → 対策
```
「ポートフォリオのリスクを確認して、やばい銘柄があれば代わりを探して」
→ 1. /stock-portfolio health を実行
→ 2. EXIT/WARNING 銘柄があれば /screen-stocks で代替候補を検索
```

### パターン2: 診断 → 深掘り
```
「PF大丈夫かな？」
→ 1. /stock-portfolio health を実行
→ 2. アラートがあれば /stress-test も自動実行して詳細分析
```

### パターン3: 売買 → 確認
```
「トヨタ100株買った、PFのバランス見て」
→ 1. /stock-portfolio buy で記録
→ 2. /stock-portfolio analyze で構造分析表示
```

### パターン4: 全体診断
```
「総合的にPFチェックして」
→ 1. /stock-portfolio snapshot（現況）
→ 2. /stock-portfolio health（健全性）
→ 3. /stock-portfolio forecast（見通し）
→ 4. 問題があれば /stock-portfolio rebalance で改善案提示
```

### パターン5: 診断 → シミュレーション
```
「PFの見通しを確認して、5年後のシミュレーションも見たい」
→ 1. /stock-portfolio forecast を実行
→ 2. /stock-portfolio simulate --years 5 で将来推移を表示
```

### パターン6: リサーチ → スクリーニング
```
「半導体業界を調べて、有望な銘柄を探して」
→ 1. /market-research industry 半導体
→ 2. key_players から候補を抽出し /screen-stocks --sector で絞り込み
```

### パターン7: リサーチ → ポートフォリオ判断
```
「今の相場状況を確認して、PF大丈夫か見て」
→ 1. /market-research market 日本株市場
→ 2. /stock-portfolio health
→ 3. マーケット状況を踏まえた判断を補足
```

## リサーチタイプ推定ルール

| ユーザー入力 | command |
|:---|:---|
| ティッカーシンボル or 企業名 + 「リサーチ/深掘り/詳しく/最新情報」 | stock |
| 業界名・テーマ + 「動向/リサーチ/調査」 | industry |
| マーケット名・指数名 + 「概況/状況/どうなってる」 | market |
| 「相場」「マーケット」のみ | market（デフォルト: 日本株市場） |

## /stock-report vs /market-research stock の使い分け

| 意図 | 実行スキル |
|:---|:---|
| バリュエーション分析、割安度判定 | `/stock-report` |
| 最新ニュース・センチメント・深掘り | `/market-research stock` |
| 「〇〇ってどう？」（簡易） | `/stock-report` |
| 「〇〇を詳しくリサーチして」「〇〇の最新情報」 | `/market-research stock` |
| 「〇〇について調べて」 | `/stock-report`（既存ルール維持。明示的に「リサーチ」「深掘り」がある場合のみ /market-research） |
