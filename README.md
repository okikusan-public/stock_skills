# stock-skills

割安株スクリーニングシステム。Yahoo Finance API（yfinance）を使って60+地域から割安銘柄をスクリーニングする。[Claude Code](https://claude.ai/code) Skills として動作し、自然言語で話しかけるだけで適切な機能が実行される。

## セットアップ

```bash
pip install -r requirements.txt
```

Python 3.10+ が必要。依存: yfinance, pyyaml, numpy, pytest

Grok API（Xセンチメント分析）を利用する場合:
```bash
export XAI_API_KEY=xai-xxxxxxxxxxxxx
```

## スキル一覧

### `/screen-stocks` — 割安株スクリーニング

EquityQuery で日本株・米国株・ASEAN株等から銘柄を検索。11のプリセットと60+地域に対応。

```bash
# 基本
/screen-stocks japan value        # 日本株バリュー
/screen-stocks us high-dividend   # 米国高配当
/screen-stocks asean growth-value # ASEAN成長割安

# プリセット一覧
# value / high-dividend / growth / growth-value / deep-value / quality / pullback / alpha / trending / long-term / shareholder-return

# オプション
/screen-stocks japan value --sector Technology  # セクター指定
/screen-stocks japan value --with-pullback      # 押し目フィルタ追加
```

### `/stock-report` — 個別銘柄レポート

ティッカーシンボルを指定して財務分析レポートを生成。バリュエーション・割安度判定・**株主還元率**（配当+自社株買い）・バリュートラップ判定を表示。

```bash
/stock-report 7203.T    # トヨタ
/stock-report AAPL      # Apple
```

**出力項目:**
- セクター・業種
- バリュエーション（PER/PBR/配当利回り/ROE/利益成長率）
- 割安度判定（0-100点スコア）
- **株主還元**（配当利回り + 自社株買い利回り = 総株主還元率）

### `/watchlist` — ウォッチリスト管理

銘柄の追加・削除・一覧表示。

```bash
/watchlist list
/watchlist add my-list 7203.T AAPL
/watchlist show my-list
```

### `/stress-test` — ストレステスト

ポートフォリオのショック感応度・シナリオ分析・相関分析・VaR・推奨アクション。8つの事前定義シナリオ（トリプル安、テック暴落、円高ドル安等）。

```bash
/stress-test 7203.T,AAPL,D05.SI
/stress-test 7203.T,9984.T --scenario トリプル安
```

### `/market-research` — 深掘りリサーチ

銘柄・業界・マーケット・ビジネスモデルの深掘り分析。Grok API で最新ニュース・Xセンチメント・業界動向を取得。

```bash
/market-research stock 7203.T    # 銘柄リサーチ
/market-research industry 半導体  # 業界リサーチ
/market-research market 日経平均  # マーケット概況
/market-research business 7751.T # ビジネスモデル分析
```

### `/stock-portfolio` — ポートフォリオ管理

保有銘柄の売買記録・損益表示・構造分析・ヘルスチェック・推定利回り・リバランス・シミュレーション。多通貨対応（JPY換算）。

```bash
/stock-portfolio snapshot   # 現在の損益
/stock-portfolio buy 7203.T 100 2850 JPY
/stock-portfolio sell AAPL 5
/stock-portfolio analyze    # HHI集中度分析
/stock-portfolio health     # ヘルスチェック（3段階アラート + クロス検出 + バリュートラップ検出 + 還元安定度）
/stock-portfolio forecast   # 推定利回り（楽観/ベース/悲観 + ニュース + Xセンチメント）
/stock-portfolio rebalance  # リバランス提案
/stock-portfolio simulate   # 複利シミュレーション（3シナリオ + 配当再投資 + 積立）
/stock-portfolio what-if    # What-Ifシミュレーション
/stock-portfolio backtest   # スクリーニング結果のバックテスト
```

### `/investment-note` — 投資メモ

投資テーゼ・懸念・学びをノートとして記録・参照・削除。

```bash
/investment-note save --symbol 7203.T --type thesis --content "EV普及で部品需要増"
/investment-note list
/investment-note list --symbol AAPL
```

### `/graph-query` — 知識グラフ検索

過去のレポート・スクリーニング・取引・リサーチ履歴を自然言語で検索。

```bash
/graph-query "7203.Tの前回レポートは？"
/graph-query "繰り返し候補に上がってる銘柄は？"
/graph-query "NVDAのセンチメント推移"
```

## アーキテクチャ

```
Skills (.claude/skills/*/SKILL.md → scripts/*.py)
  │
  ▼
Core (src/core/)
  screening/ ─ screener, indicators, filters, query_builder, alpha, technicals
  portfolio/ ─ portfolio_manager, portfolio_simulation, concentration, rebalancer, simulator, backtest
  risk/      ─ correlation, shock_sensitivity, scenario_analysis, scenario_definitions, recommender
  research/  ─ researcher (yfinance + Grok API統合)
  [root]     ─ common, models, ticker_utils, health_check, return_estimate, value_trap
  │
  ├─ Markets (src/markets/) ─ japan/us/asean
  ├─ Data (src/data/)
  │    yahoo_client.py ─ 24h JSONキャッシュ
  │    grok_client.py ─ Grok API (Xセンチメント分析)
  │    graph_store.py ─ Neo4j ナレッジグラフ (dual-write)
  │    history_store.py ─ 実行履歴の自動蓄積
  ├─ Output (src/output/) ─ Markdown フォーマッタ
  └─ Config (config/) ─ プリセット・取引所定義
```

詳細は [CLAUDE.md](CLAUDE.md) を参照。

## Neo4j ナレッジグラフ（オプション）

スキル実行履歴を Neo4j に蓄積し、過去の分析・取引・リサーチを横断検索できる。

```bash
# Docker で Neo4j を起動
docker compose up -d

# スキーマ初期化 + 既存データインポート
python3 scripts/init_graph.py --rebuild
```

Neo4j 未接続でも全スキルが正常動作する（graceful degradation）。

## テスト

```bash
pytest tests/           # 全1573テスト (< 6秒)
pytest tests/core/ -v   # コアモジュール
```

## 免責事項

本ソフトウェアは投資判断の参考情報を提供するものであり、**投資成果を保証するものではありません**。本ソフトウェアの出力に基づく投資判断はすべて利用者自身の責任で行ってください。開発者は、本ソフトウェアの利用により生じたいかなる損害についても責任を負いません。

## ライセンス

本ソフトウェアはライセンスフリーです。誰でも自由に利用・改変・再配布できます。
