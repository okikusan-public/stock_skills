# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Design Philosophy

**このシステムは「自然言語ファースト」で設計されている。**

ユーザーはスラッシュコマンドやパラメータを覚える必要はない。日本語で意図を伝えるだけで、適切なスキルが自動的に選択・実行される。

- 「いい日本株ある？」→ スクリーニングが走る
- 「トヨタってどう？」→ 個別レポートが出る
- 「PF大丈夫かな」→ ヘルスチェックが実行される
- 「改善点ある？」→ システム自身を分析して提案する

スキル（`/screen-stocks` 等）はあくまで内部実装であり、ユーザーインターフェースではない。自然言語からの意図推論が第一の入口であり、コマンドは補助手段に過ぎない。

新機能を追加する際は、**ユーザーがどんな言葉でその機能を呼び出すか**を常に考え、`intent-routing.md` にその表現を反映すること。

## Project Overview

割安株スクリーニングシステム。Yahoo Finance API（yfinance）を使って日本株・米国株・ASEAN株・香港株・韓国株・台湾株等60地域から割安銘柄をスクリーニングする。Claude Code Skills として動作し、自然言語で話しかけるだけで適切な機能が実行される。

## Commands

```bash
# スクリーニング実行（EquityQuery方式 - デフォルト）
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset value --top 10

# Xトレンド銘柄スクリーニング（Grok API、XAI_API_KEY 必須）
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset trending --top 10
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region us --preset trending --theme "AI" --top 10

# 長期投資候補スクリーニング（高ROE・EPS成長・高配当・安定大型株）
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset long-term --top 10

# 個別銘柄レポート
python3 .claude/skills/stock-report/scripts/generate_report.py 7203.T

# ウォッチリスト操作
python3 .claude/skills/watchlist/scripts/manage_watchlist.py list

# 深掘りリサーチ（銘柄/業界/マーケット/ビジネスモデル）
python3 .claude/skills/market-research/scripts/run_research.py stock 7203.T
python3 .claude/skills/market-research/scripts/run_research.py industry 半導体
python3 .claude/skills/market-research/scripts/run_research.py market 日経平均
python3 .claude/skills/market-research/scripts/run_research.py business 7751.T

# ストレステスト実行
python3 .claude/skills/stress-test/scripts/run_stress_test.py --portfolio 7203.T,AAPL,D05.SI

# ポートフォリオ管理
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py snapshot
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py buy --symbol 7203.T --shares 100 --price 2850 --currency JPY
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py sell --symbol AAPL --shares 5
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py analyze
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py health
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py forecast
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py rebalance
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py simulate --years 5 --monthly-add 50000 --target 15000000
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py what-if --add "7203.T:100:2850,AAPL:10:250"
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py backtest --preset alpha --region jp --days 90
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py list

# 投資メモ管理
python3 .claude/skills/investment-note/scripts/manage_note.py save --symbol 7203.T --type thesis --content "EV普及で部品需要増"
python3 .claude/skills/investment-note/scripts/manage_note.py list
python3 .claude/skills/investment-note/scripts/manage_note.py delete --id NOTE_ID

# 知識グラフ照会（自然言語）
python3 .claude/skills/graph-query/scripts/run_query.py "7203.Tの前回レポートは？"

# テスト
python3 -m pytest tests/ -q

# 依存インストール
pip install -r requirements.txt
```

## Architecture

```
Skills (.claude/skills/*/SKILL.md → scripts/*.py)
  │  ユーザーの /command を受けてスクリプトを実行
  │
  ├─ screen-stocks/run_screen.py   … --region --preset --sector --with-pullback
  ├─ stock-report/generate_report.py
  ├─ market-research/run_research.py … stock/industry/market/business (Grok API深掘り)
  ├─ watchlist/manage_watchlist.py
  ├─ stress-test/run_stress_test.py
  ├─ investment-note/manage_note.py  … save/list/delete (投資メモCRUD)
  ├─ graph-query/run_query.py        … 自然言語→グラフ照会
  └─ stock-portfolio/run_portfolio.py … snapshot/buy/sell/analyze/health/forecast/rebalance/simulate/what-if/backtest/list
      │
      │  sys.path.insert で project root を追加して src/ を import
      ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Core (src/core/)                                            │
  │                                                           │
  │  [root] 共通モジュール                                      │
  │  models.py ─ dataclass定義(Position/ForecastResult/HealthResult等) │
  │  common.py ─ 共通ユーティリティ(is_cash/is_etf/safe_float)   │
  │  ticker_utils.py ─ ティッカー推論(通貨/地域マッピング)         │
  │  health_check.py ─ 保有銘柄ヘルスチェック(3段階アラート+クロス検出+トラップ検出+還元安定度) │
  │  return_estimate.py ─ 推定利回り(アナリスト+過去リターン+ニュース+Xセンチメント) │
  │  value_trap.py ─ バリュートラップ検出(health_checkから独立)     │
  │                                                           │
  │  screening/ ─ スクリーニングエンジン                          │
  │    screener.py ─ 4つのスクリーナー(Query/Value/Pullback/Alpha) │
  │    indicators.py ─ バリュースコア(0-100点)+株主還元率+安定度   │
  │    filters.py ─ ファンダメンタルズ条件フィルタ                  │
  │    query_builder.py ─ EquityQuery構築                      │
  │    alpha.py ─ 変化スコア(アクルーアルズ/売上加速/FCF/ROE趨勢)  │
  │    technicals.py ─ 押し目判定(RSI/BB/バウンススコア)          │
  │                                                           │
  │  portfolio/ ─ ポートフォリオ管理・分析                        │
  │    portfolio_manager.py ─ CSVベースのポートフォリオ管理        │
  │    portfolio_simulation.py ─ What-Ifシミュレーション           │
  │    portfolio_bridge.py ─ PF CSV→ストレステスト連携            │
  │    concentration.py ─ HHI集中度分析                          │
  │    rebalancer.py ─ リスク制約付きリバランス提案エンジン          │
  │    simulator.py ─ 複利シミュレーション(3シナリオ+配当再投資+積立) │
  │    backtest.py ─ 蓄積データからリターン検証・ベンチマーク比較     │
  │                                                           │
  │  risk/ ─ リスク分析・ストレステスト                           │
  │    correlation.py ─ 日次リターン・相関行列・因子分解            │
  │    shock_sensitivity.py ─ ショック感応度スコア                 │
  │    scenario_analysis.py ─ シナリオ分析(実行ロジック)           │
  │    scenario_definitions.py ─ シナリオ定義(8シナリオ+ETF資産クラス) │
  │    recommender.py ─ ルールベース推奨アクション                  │
  │                                                           │
  │  research/ ─ 深掘りリサーチ                                  │
  │    researcher.py ─ yfinance+Grok API統合リサーチ              │
  └─────────────────────────────────────────────────────────┘
      │                    │                    │
  Markets            Data                  Output
  src/markets/       src/data/             src/output/
  base.py (ABC)      yahoo_client.py       formatter.py
  japan.py           (24h JSON cache,      stress_formatter.py
  us.py               EquityQuery,         portfolio_formatter.py
  asean.py            1秒ディレイ,         research_formatter.py
                      異常値ガード)
                     grok_client.py
                     (Grok API X/Web Search,
                      XAI_API_KEY 環境変数,
                      未設定時スキップ,
                      銘柄/業界/市場リサーチ)
                     history_store.py
                     (スキル実行時の自動蓄積,
                      data/history/ へ日付付きJSON,
                      screen/report/trade/health/
                      research/market_context,
                      Neo4j dual-write: JSON=master, Neo4j=view)
                     graph_store.py
                     (Neo4jナレッジグラフCRUD,
                      スキーマ初期化+MERGE操作,
                      Stock/Screen/Report/Trade/Health/
                      Research/Watchlist/Note/MarketContext,
                      SUPERSEDES チェーン,
                      graceful degradation)
                     graph_query.py
                     (Neo4jナレッジグラフ照会,
                      前回レポート比較/再出現銘柄/
                      リサーチ履歴/市況コンテキスト/
                      売買コンテキスト/常連銘柄,
                      Neo4j不可時は空/None返却)
                     note_manager.py
                     (投資メモ管理,
                      JSON=master, Neo4j=view,
                      thesis/observation/concern/review/target/lesson)
                     graph_nl_query.py
                     (自然言語→グラフ照会ディスパッチ,
                      テンプレートマッチ→graph_query関数,
                      前回レポート/常連銘柄/リサーチ履歴/
                      市況/取引コンテキスト/メモ照会)

  Scripts: scripts/
           init_graph.py ─ Neo4jスキーマ初期化+既存履歴インポート
           hooks/pre-commit ─ src/変更時のドキュメント更新チェック(KIK-407)
                           (screen/report/trade/health/research/
                            portfolio/watchlist/notes/market_context,
                            --rebuild)

  Config: config/screening_presets.yaml (7プリセット)
          config/exchanges.yaml (60+地域の取引所・閾値)

  Rules: .claude/rules/
          intent-routing.md  ─ 自然言語→スキル判定ルール（2段階ドメインルーティング）
          workflow.md        ─ 開発ワークフロー（設計→実装→テスト→レビュー→ドキュメント更新→完了）
          development.md     ─ 開発ルール・Git・テスト
          screening.md       ─ スクリーニング開発ルール (path-specific)
          portfolio.md       ─ ポートフォリオ開発ルール (path-specific)
          testing.md         ─ テスト開発ルール (path-specific)
```

## Post-Implementation Rule

**機能実装後は必ずドキュメント・ルールを更新すること。** 詳細は `.claude/rules/workflow.md` の「7. ドキュメント・ルール更新」を参照。

更新対象: `intent-routing.md`、該当 `SKILL.md`、`CLAUDE.md`、`rules/*.md`、`README.md`
