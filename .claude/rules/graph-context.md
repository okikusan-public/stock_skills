# Graph Context: ナレッジグラフスキーマ + 自動コンテキスト注入 (KIK-411)

## Neo4j ナレッジグラフスキーマ

CSV/JSON が master、Neo4j は検索・関連付け用の view（dual-write パターン）。詳細は `docs/neo4j-schema.md` 参照。

**19 ノード:**
Stock(中心), Screen, Report, Trade, HealthCheck, Note, Theme, Sector,
Research, Watchlist, MarketContext, Portfolio,
News, Sentiment, Catalyst, AnalystView, Indicator, UpcomingEvent, SectorRotation

**主要リレーション:**
- `Screen-[SURFACED]->Stock` / `Report-[ANALYZED]->Stock` / `Trade-[BOUGHT|SOLD]->Stock`
- `Portfolio-[HOLDS]->Stock` (現在保有, KIK-414) / `Watchlist-[BOOKMARKED]->Stock`
- `Research-[HAS_NEWS]->News-[MENTIONS]->Stock` / `Research-[HAS_SENTIMENT]->Sentiment`
- `Research-[HAS_CATALYST]->Catalyst` / `Research-[HAS_ANALYST_VIEW]->AnalystView`
- `Research-[SUPERSEDES]->Research` (同一対象の新旧チェーン)
- `MarketContext-[INCLUDES]->Indicator` / `MarketContext-[HAS_EVENT]->UpcomingEvent`
- `Note-[ABOUT]->Stock` / `Stock-[IN_SECTOR]->Sector` / `Stock-[HAS_THEME]->Theme`

**データの流れ:** スキル実行 → JSON/CSV保存(master) → Neo4j同期(view) → 次回 `get_context.py` で自動取得

---

## 自動コンテキスト注入

ユーザーのプロンプトに銘柄名・ティッカーシンボルが含まれている場合、
スキル実行前に以下のスクリプトを実行してコンテキストを取得する。

## いつ実行するか

以下の条件のいずれかに該当する場合:
- ティッカーシンボル（7203.T, AAPL, D05.SI 等）が含まれる
- 企業名（トヨタ、Apple 等）+ 「どう」「調べて」「分析」等の分析意図がある
- 「PF」「ポートフォリオ」+ 状態確認の意図がある
- 「相場」「市況」等のマーケット照会意図がある

## コンテキスト取得コマンド

```bash
python3 scripts/get_context.py "<ユーザー入力>"
```

## コンテキストの使い方

1. 出力された「過去の経緯」をスキル実行の判断材料にする
2. 「推奨スキル」を参考にスキルを選択する（intent-routing.md と合わせて判断）
3. 前回の値がある場合は差分を意識した出力にする
4. Neo4j 未接続時は出力が「コンテキストなし」→ 従来通り intent-routing のみで判断

## スキル推奨の優先度

| 関係性 | 推奨スキル | 理由 |
|:---|:---|:---|
| 保有銘柄（BOUGHT あり） | `/stock-portfolio health` | 保有者として診断優先 |
| テーゼ3ヶ月経過 | `/stock-portfolio health` + レビュー促し | 定期振り返りタイミング |
| EXIT 判定あり | `/screen-stocks`（同セクター代替） | 乗り換え提案 |
| ウォッチ中（BOOKMARKED） | `/stock-report` + 前回差分 | 買い時かの判断材料 |
| 3回以上スクリーニング出現 | `/stock-report` + 注目フラグ | 繰り返し上位で注目度高 |
| 直近リサーチ済み（7日以内） | 差分のみ取得 | API コスト削減 |
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

## graceful degradation

- Neo4j 未接続時: スクリプトは「コンテキストなし」を出力 → 従来通りの動作
- スクリプトエラー時: 無視して intent-routing のみで判断
- シンボル検出できない場合: 「コンテキストなし」→ 通常の intent-routing
