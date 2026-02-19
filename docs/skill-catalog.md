# Skill Catalog

8つの Claude Code Skills の一覧。すべて `.claude/skills/<name>/SKILL.md` で定義され、`scripts/*.py` で実装。

---

## Overview

| Skill | Description | Core Dependencies |
|:---|:---|:---|
| screen-stocks | 割安株スクリーニング (60地域, 11プリセット) | screening/*.py, yahoo_client |
| stock-report | 個別銘柄バリュエーションレポート | indicators.py, value_trap.py, yahoo_client |
| market-research | 深掘りリサーチ (銘柄/業界/市場/ビジネスモデル) | researcher.py, grok_client |
| watchlist | ウォッチリスト管理 (add/remove/list) | (直接 JSON) |
| stress-test | ポートフォリオストレステスト (8シナリオ) | risk/*.py, yahoo_client |
| stock-portfolio | ポートフォリオ管理 (12サブコマンド) | portfolio/*.py, health_check.py, return_estimate.py |
| investment-note | 投資メモ管理 (save/list/delete) | note_manager.py, graph_store.py |
| graph-query | 知識グラフ自然言語照会 | graph_nl_query.py, graph_query.py |

---

## 1. screen-stocks

割安株スクリーニング。EquityQuery 方式で銘柄リスト不要のスクリーニングを実行。

**Script**: `.claude/skills/screen-stocks/scripts/run_screen.py`

**Options**:
- `--region`: 対象地域 (japan, us, asean, sg, hk, kr, tw, cn, etc.)
- `--preset`: 戦略プリセット (alpha, value, high-dividend, growth, growth-value, deep-value, quality, pullback, trending, long-term, shareholder-return)
- `--sector`: セクター絞り込み (e.g. Technology)
- `--top N`: 上位N件表示
- `--with-pullback`: 押し目分析を付加
- `--theme`: trending プリセットのテーマ指定

**Examples**:
```bash
python3 run_screen.py --region japan --preset alpha --top 10
python3 run_screen.py --region us --preset trending --theme "AI" --top 10
python3 run_screen.py --region japan --preset growth --top 10
python3 run_screen.py --region japan --preset long-term --top 10
```

**Output**: Markdown テーブル (銘柄/名前/スコア/PER/PBR/配当利回り/ROE)。直近売却済み銘柄は自動除外(KIK-418)、懸念/学びメモがある銘柄にはマーカー表示(KIK-419)。

**Annotation Markers** (KIK-418/419):
- ⚠️ = 懸念メモあり (concern)
- 📝 = 学びメモあり (lesson)
- 👀 = 様子見 (observation に「見送り」「待ち」等キーワード)
- 直近90日以内の売却銘柄は結果から自動除外

**Core Dependencies**: `src/core/screening/screener.py`, `indicators.py`, `filters.py`, `query_builder.py`, `alpha.py`, `technicals.py`, `src/data/screen_annotator.py`

---

## 2. stock-report

個別銘柄の詳細バリュエーションレポート。

**Script**: `.claude/skills/stock-report/scripts/generate_report.py`

**Input**: ティッカーシンボル (e.g. 7203.T, AAPL)

**Examples**:
```bash
python3 generate_report.py 7203.T
python3 generate_report.py AAPL
```

**Output**: Markdown レポート (基本情報/バリュエーション/割安度判定/株主還元率/3年還元推移/バリュートラップ判定)

**Core Dependencies**: `src/core/screening/indicators.py`, `src/core/value_trap.py`, `src/data/yahoo_client.py`

---

## 3. market-research

Grok API (X検索/Web検索) と yfinance を統合した深掘りリサーチ。

**Script**: `.claude/skills/market-research/scripts/run_research.py`

**Subcommands**:
- `stock <symbol>`: 個別銘柄の最新ニュース・Xセンチメント
- `industry <name>`: 業界動向リサーチ
- `market <name>`: マーケット概況
- `business <symbol>`: ビジネスモデル・事業構造分析

**Examples**:
```bash
python3 run_research.py stock 7203.T
python3 run_research.py industry 半導体
python3 run_research.py market 日経平均
python3 run_research.py business 7751.T
```

**Output**: Markdown レポート (概要/ニュース/Xトレンド/分析)

**Core Dependencies**: `src/core/research/researcher.py`, `src/data/grok_client.py`, `src/data/yahoo_client.py`

**Note**: XAI_API_KEY 環境変数が必要。未設定時は Grok 部分をスキップして yfinance のみで生成。

---

## 4. watchlist

ウォッチリストの CRUD 管理。

**Script**: `.claude/skills/watchlist/scripts/manage_watchlist.py`

**Subcommands**:
- `list [--name NAME]`: 一覧表示
- `add --name NAME --symbols SYM1,SYM2`: 銘柄追加
- `remove --name NAME --symbols SYM1`: 銘柄削除

**Examples**:
```bash
python3 manage_watchlist.py list
python3 manage_watchlist.py add --name "注目" --symbols "7203.T,AAPL"
python3 manage_watchlist.py remove --name "注目" --symbols "7203.T"
```

**Output**: Markdown リスト

**Core Dependencies**: なし (直接 JSON ファイルを読み書き)

---

## 5. stress-test

ポートフォリオのストレステスト。8つの定義済みシナリオ + カスタムシナリオ。

**Script**: `.claude/skills/stress-test/scripts/run_stress_test.py`

**Options**:
- `--portfolio`: 銘柄リスト (カンマ区切り) またはPFから自動取得
- `--scenario`: シナリオ指定 (トリプル安, ドル高円安, etc.)

**Examples**:
```bash
python3 run_stress_test.py --portfolio 7203.T,AAPL,D05.SI
python3 run_stress_test.py --scenario テック暴落
```

**Output**: Markdown レポート (相関行列/ショック感応度/シナリオ分析/因果連鎖/推奨アクション)。実行結果は `data/history/stress_test/` に自動保存 (KIK-428)。

**Scenarios**: トリプル安、ドル高円安、米国リセッション、日銀利上げ、米中対立、インフレ再燃、テック暴落、円高ドル安

**Auto-Save** (KIK-428): 実行完了時に `data/history/stress_test/{date}_{scenario}.json` へ自動保存。Neo4j にも StressTest ノード + STRESSED リレーションを dual-write。

**Core Dependencies**: `src/core/risk/correlation.py`, `shock_sensitivity.py`, `scenario_analysis.py`, `scenario_definitions.py`, `recommender.py`, `src/data/history_store.py`

---

## 6. stock-portfolio

ポートフォリオ管理。12のサブコマンドで保有管理・分析・シミュレーションを実行。

**Script**: `.claude/skills/stock-portfolio/scripts/run_portfolio.py`

**Subcommands**:

| Command | Description |
|:---|:---|
| `list` | 保有銘柄一覧 (CSV 表示) |
| `snapshot` | 現在価格・損益・通貨換算のスナップショット |
| `buy` | 購入記録追加 |
| `sell` | 売却記録 |
| `analyze` | 構造分析 (セクター/地域/通貨 HHI) |
| `health` | ヘルスチェック (3段階アラート+クロス検出+バリュートラップ+還元安定度) |
| `forecast` | 推定利回り (3シナリオ)。結果は自動保存 (KIK-428) |
| `rebalance` | リバランス提案 |
| `simulate` | 複利シミュレーション |
| `what-if` | What-If シミュレーション (銘柄追加の影響) |
| `backtest` | 過去のスクリーニング結果からリターン検証 |

**Examples**:
```bash
python3 run_portfolio.py snapshot
python3 run_portfolio.py buy --symbol 7203.T --shares 100 --price 2850 --currency JPY
python3 run_portfolio.py sell --symbol AAPL --shares 5
python3 run_portfolio.py health
python3 run_portfolio.py simulate --years 5 --monthly-add 50000 --target 15000000
python3 run_portfolio.py what-if --add "7203.T:100:2850,AAPL:10:250"
python3 run_portfolio.py backtest --preset alpha --region jp --days 90
```

**Auto-Save** (KIK-428): forecast サブコマンド実行完了時に `data/history/forecast/{date}_forecast.json` へ自動保存。Neo4j にも Forecast ノード + FORECASTED リレーションを dual-write。

**Core Dependencies**: `src/core/portfolio/portfolio_manager.py`, `concentration.py`, `rebalancer.py`, `simulator.py`, `backtest.py`, `portfolio_simulation.py`, `src/core/health_check.py`, `return_estimate.py`, `value_trap.py`, `src/data/history_store.py`

---

## 7. investment-note

投資メモの管理。JSON + Neo4j の dual-write パターン。

**Script**: `.claude/skills/investment-note/scripts/manage_note.py`

**Subcommands**:
- `save --symbol SYM --type TYPE --content TEXT [--source SRC]`
- `list [--symbol SYM] [--type TYPE]`
- `delete --id NOTE_ID`

**Note Types**: thesis, observation, concern, review, target, lesson

**Examples**:
```bash
python3 manage_note.py save --symbol 7203.T --type thesis --content "EV普及で部品需要増"
python3 manage_note.py list --symbol 7203.T
python3 manage_note.py list --type lesson
python3 manage_note.py delete --id abc123
```

**Output**: Markdown テーブル (日付/銘柄/タイプ/内容)

**Core Dependencies**: `src/data/note_manager.py`, `src/data/graph_store.py`

---

## 8. graph-query

知識グラフへの自然言語クエリ。テンプレートマッチで正規表現パターンから graph_query.py の関数にディスパッチ。

**Script**: `.claude/skills/graph-query/scripts/run_query.py`

**Input**: 自然言語クエリ

**Supported Query Types**:

| Pattern | Query Type | Function |
|:---|:---|:---|
| 前回、以前、過去のレポート | prior_report | `get_prior_report(symbol)` |
| 何回もスクリーニング、繰り返し候補 | recurring_picks | `get_recurring_picks()` |
| リサーチ履歴、前に調べた | research_chain | `get_research_chain(type, target)` |
| 最近の相場、市況 | market_context | `get_recent_market_context()` |
| 取引履歴、売買記録 | trade_context | `get_trade_context(symbol)` |
| メモ、ノート一覧 | stock_notes | `get_trade_context(symbol).notes` |
| ストレステスト履歴、前回のストレステスト | stress_test_history | `get_stress_test_history(symbol)` (KIK-428) |
| フォーキャスト推移、前回の見通し | forecast_history | `get_forecast_history(symbol)` (KIK-428) |

**Examples**:
```bash
python3 run_query.py "7203.Tの前回レポートは？"
python3 run_query.py "繰り返し候補に上がってる銘柄は？"
python3 run_query.py "AAPLの取引履歴"
python3 run_query.py "最近の市況は？"
```

**Output**: Markdown テーブル (クエリタイプに応じたフォーマット)

**Core Dependencies**: `src/data/graph_nl_query.py`, `src/data/graph_query.py`, `src/data/graph_store.py`

---

## Skill → Core Module Dependency Map

```
screen-stocks ──→ screening/{screener,indicators,filters,query_builder,alpha,technicals}
                   yahoo_client, grok_client (trending only)

stock-report ───→ screening/indicators, value_trap
                   yahoo_client

market-research → research/researcher
                   grok_client, yahoo_client

watchlist ──────→ (none - direct JSON)

stress-test ────→ risk/{correlation,shock_sensitivity,scenario_analysis,scenario_definitions,recommender}
                   yahoo_client

stock-portfolio → portfolio/{portfolio_manager,concentration,rebalancer,simulator,backtest,portfolio_simulation}
                   health_check, return_estimate, value_trap
                   yahoo_client

investment-note → note_manager, graph_store

graph-query ────→ graph_nl_query, graph_query, graph_store

(auto-context) ─→ auto_context (graph_store, graph_query)
                   ※ スキルではなく rules/graph-context.md + scripts/get_context.py
                   ※ スキル実行前に自動でコンテキスト注入
```
