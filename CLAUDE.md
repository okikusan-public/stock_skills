# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

割安株スクリーニングシステム。Yahoo Finance API（yfinance）を使って日本株・米国株・ASEAN株・香港株・韓国株・台湾株等60地域から割安銘柄をスクリーニングする。Claude Code Skills として動作し、`/screen-stocks`、`/stock-report`、`/watchlist`、`/stress-test`、`/stock-portfolio` コマンドで利用する。

## Commands

```bash
# スクリーニング実行（EquityQuery方式 - デフォルト）
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset value --top 10
# region: japan / us / asean / sg / th / my / id / ph / hk / kr / tw / cn / all
# preset: value / high-dividend / growth-value / deep-value / quality / pullback / alpha
# sector (optional): Technology / Financial Services / Healthcare / Consumer Cyclical / Industrials
#                     Communication Services / Consumer Defensive / Energy / Basic Materials
#                     Real Estate / Utilities
# --with-pullback: 任意プリセットに押し目フィルタを追加（例: --preset value --with-pullback）
# --mode legacy: 銘柄リスト方式（japan/us/asean のみ）

# 個別銘柄レポート
python3 .claude/skills/stock-report/scripts/generate_report.py 7203.T

# ウォッチリスト操作
python3 .claude/skills/watchlist/scripts/manage_watchlist.py list
python3 .claude/skills/watchlist/scripts/manage_watchlist.py add my-list 7203.T AAPL
python3 .claude/skills/watchlist/scripts/manage_watchlist.py show my-list

# ストレステスト実行
python3 .claude/skills/stress-test/scripts/run_stress_test.py --portfolio 7203.T,AAPL,D05.SI
python3 .claude/skills/stress-test/scripts/run_stress_test.py --portfolio 7203.T,9984.T --scenario トリプル安

# ポートフォリオ管理
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py snapshot
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py buy --symbol 7203.T --shares 100 --price 2850 --currency JPY
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py sell --symbol AAPL --shares 5
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py analyze
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py health
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py forecast
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py rebalance
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py rebalance --strategy defensive
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py rebalance --reduce-sector Technology --additional-cash 1000000
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py list

# テスト
python3 -m pytest tests/ -q                       # 全件実行（約600テスト, ~1秒）
python3 -m pytest tests/core/test_indicators.py -v # 特定モジュール
python3 -m pytest tests/ -k "test_value_score"     # キーワード指定

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
  ├─ watchlist/manage_watchlist.py
  ├─ stress-test/run_stress_test.py
  └─ stock-portfolio/run_portfolio.py … snapshot/buy/sell/analyze/health/forecast/rebalance/list
      │
      │  sys.path.insert で project root を追加して src/ を import
      ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Core (src/core/)                                        │
  │  screener.py ─ 4つのスクリーナーエンジン                     │
  │  indicators.py ─ バリュースコア(0-100点)                    │
  │  filters.py ─ ファンダメンタルズ条件フィルタ                   │
  │  query_builder.py ─ EquityQuery 構築                     │
  │  alpha.py ─ 変化スコア(アクルーアルズ/売上加速/FCF/ROE趨勢)    │
  │  technicals.py ─ 押し目判定(RSI/BB/バウンススコア)           │
  │  health_check.py ─ 保有銘柄ヘルスチェック(3段階アラート)       │
  │  return_estimate.py ─ 推定利回り(アナリスト+過去リターン+ニュース) │
  │  concentration.py ─ HHI集中度分析                          │
  │  correlation.py ─ 日次リターン・相関行列・因子分解              │
  │  shock_sensitivity.py ─ ショック感応度スコア                  │
  │  scenario_analysis.py ─ シナリオ分析(8シナリオ+ETF資産クラス)  │
  │  recommender.py ─ ルールベース推奨アクション                   │
  │  rebalancer.py ─ リスク制約付きリバランス提案エンジン            │
  │  portfolio_manager.py ─ CSV ベースのポートフォリオ管理         │
  │  portfolio_bridge.py ─ ポートフォリオCSV→ストレステスト連携     │
  └─────────────────────────────────────────────────────────┘
      │                    │                    │
  Markets            Data                  Output
  src/markets/       src/data/             src/output/
  base.py (ABC)      yahoo_client.py       formatter.py
  japan.py           (24h JSON cache,      stress_formatter.py
  us.py               EquityQuery,         portfolio_formatter.py
  asean.py            1秒ディレイ,
                      異常値ガード)
                     grok_client.py
                     (Grok API X Search,
                      XAI_API_KEY 環境変数,
                      未設定時スキップ)

  Config: config/screening_presets.yaml (7プリセット)
          config/exchanges.yaml (60+地域の取引所・閾値)
```

## Four Screening Engines

### QueryScreener（デフォルト）
`build_query()` → `screen_stocks()` [EquityQuery bulk API] → `_normalize_quote()` → `calculate_value_score()` → ソート。`--with-pullback` で押し目フィルタ追加可能。

### ValueScreener（Legacy, `--mode legacy`）
銘柄リスト1件ずつ `get_stock_info()` → `apply_filters()` → `calculate_value_score()`。japan/us/asean のみ。

### PullbackScreener（`--preset pullback`）
3段パイプライン: EquityQuery → `detect_pullback_in_uptrend()` → value_score。上昇トレンド中の一時調整を検出。"full"（完全一致）と"partial"（部分一致, bounce_score≥30）の2種類。

### AlphaScreener（`--preset alpha`）
4段パイプライン: EquityQuery(割安足切り) → `compute_change_score()` (3/4指標≥15点で通過) → 押し目判定 → 2軸スコアリング(value 100pt + change 100pt + 押し目ボーナス)。

## yahoo_client のデータ取得パターン

- **`get_stock_info(symbol)`**: `ticker.info` のみ。キャッシュ `{symbol}.json` (24h TTL)
- **`get_stock_detail(symbol)`**: info + price_history + balance_sheet + cashflow + income_stmt。キャッシュ `{symbol}_detail.json`
- **`screen_stocks(query)`**: EquityQuery ベースのバルクスクリーニング（キャッシュなし）
- **`get_price_history(symbol, period)`**: OHLCV DataFrame（キャッシュなし、デフォルト1年分）
- **`_sanitize_anomalies()`**: 異常値ガード — 配当利回り>15%、PBR<0.1/PBR>100、PER<0/PER>500、ROE>200% を None にサニタイズ

## Health Check (KIK-356/357)

`/stock-portfolio health` で保有銘柄の投資仮説検証。テクニカル（日次）とファンダ（四半期）の2軸で判定。

- **check_trend_health()**: SMA50/200, RSI から「上昇/横ばい/下降」を判定。SMA50割れ、RSI急落、デッドクロスを検出。
- **check_change_quality()**: alpha.py の `compute_change_score()` を再利用。passed_count で「良好/1指標↓/複数悪化」に分類。ETFは `_is_etf()` で検出し `quality_label="対象外"` を返す。
- **compute_alert_level()**: 3段階 — 早期警告（SMA50割れ等）、注意（SMA接近+指標悪化）、撤退（デッドクロス+複数悪化）。撤退にはテクニカル崩壊+ファンダ悪化の両方が必要（ファンダ良好ならCAUTION止まり）。
- **ETF判定**: `_is_etf()` は `bool()` truthiness チェック（`is not None` ではなく）。`[]`, `0`, `""` も falsy として扱う。

## Scenario Analysis (KIK-354/358)

8シナリオ: トリプル安、ドル高円安、米国リセッション、日銀利上げ、米中対立、インフレ再燃、テック暴落、円高ドル安。日本語エイリアス（`SCENARIO_ALIASES`）で自然言語入力に対応。

- **ETF資産クラスマッチング (KIK-358)**: `_ETF_ASSET_CLASS` マッピングで16銘柄を金・長期債・株式インカムに分類。`_match_target()` が `etf_asset_class` パラメータでETFをシナリオターゲットにマッチ。非株式ETF（金・債券）は自分の資産クラスのみマッチ。
- **`_match_target()`**: 地域→通貨→輸出/内需→ETF資産クラス→非テック→セクターの優先順でマッチング。

## Return Estimation (KIK-359/360)

`/stock-portfolio forecast` で保有銘柄の推定利回りを楽観/ベース/悲観の3シナリオで提示。

- **株式（アナリストカバレッジあり）**: yfinance の `targetHighPrice`/`targetMeanPrice`/`targetLowPrice` から期待リターン算出。`numberOfAnalystOpinions` で信頼度を3段階表示。アナリスト少数時（3名未満）はスプレッド±20%を適用。
- **ETF（カバレッジなし）**: 過去2年の月次リターンからCAGR（複利年率）を算出し、±1σでシナリオ分岐。キャップ±30%。
- **ニュース**: yfinance `ticker.news` で各銘柄の公式メディアニュース（タイトル・要約）を取得。
- **Xセンチメント**: Grok API（`grok-4-1-fast-non-reasoning` + X Search）で銘柄のXポストを分析。`XAI_API_KEY` 未設定時はスキップ（グレースフルデグレード）。
- **`grok_client.py`**: `is_available()` で `XAI_API_KEY` 環境変数を確認。`search_x_sentiment()` でポジティブ/ネガティブ要因を返す。

## Rebalance (KIK-363)

`/stock-portfolio rebalance` でリスク制約付きリバランス提案を生成。forecast/health/concentration/correlationの4データソースを統合。

- **3戦略**: defensive（max_single_ratio=10%, sector_hhi<0.20）、balanced（15%, 0.25）、aggressive（25%, 0.35）
- **アクション生成**: (1) sell: health=EXIT or base<-10%, (2) reduce: overweight/相関集中/指定セクター・通貨, (3) increase: 正リターン+制約内
- **CLIオプション**: `--strategy`, `--reduce-sector`, `--reduce-currency`, `--max-single-ratio`, `--max-sector-hhi`, `--max-region-hhi`, `--additional-cash`, `--min-dividend-yield`
- **出力**: before/after比較テーブル + アクション一覧（売り/減らす/増やす）+ 制約条件表示

## Key Design Decisions

- **yahoo_client はモジュール関数**。`from src.data import yahoo_client` → `yahoo_client.get_stock_info(symbol)`。クラスではないため monkeypatch でモック容易。
- **配当利回りの正規化**: yfinance が `dividendYield` をパーセント値（例: 2.56）で返すことがある。`_normalize_ratio()` が値 > 1 の場合 100 で割って比率に変換。
- **フィールド名のエイリアス**: indicators.py は yfinance 生キー（`trailingPE`, `priceToBook`）と正規化済みキー（`per`, `pbr`）の両方を対応。
- **Market クラス**: `format_ticker()`, `get_default_symbols()`, `get_thresholds()`, `get_region()`, `get_exchanges()` を提供。Legacy モード専用。
- **キャッシュ**: `data/cache/` に銘柄ごと JSON。TTL 24時間。API 間 1秒ディレイ。
- **プリセット**: `config/screening_presets.yaml` で定義。criteria の閾値を YAML で管理。
- **バリュースコア配分**: PER(25) + PBR(25) + 配当利回り(20) + ROE(15) + 売上成長率(15) = 100点。
- **HAS_MODULE パターン**: スクリプト層（run_*.py）は `try/except ImportError` で各モジュールの存在を確認し、`HAS_*` フラグで graceful degradation。

## Testing

- `python3 -m pytest tests/ -q` で全テスト実行（約740テスト、~1秒）
- `tests/conftest.py` に共通フィクスチャ: `stock_info_data`, `stock_detail_data`, `price_history_df`, `mock_yahoo_client`
- `tests/fixtures/` に JSON/CSV テストデータ（Toyota 7203.T ベース）
- `mock_yahoo_client` は monkeypatch で yahoo_client モジュール関数をモック。`return_value` を設定して使用
- テストファイルは `tests/core/`, `tests/data/`, `tests/output/` に機能別に配置

## Git Workflow

- Linear issue（KIK-NNN）ごとに `git worktree add` でワークツリーを作成: `~/stock-skills-kik{NNN}`
- ブランチ名: `feature/kik-{NNN}-{short-desc}`
- 完了後: `git merge --no-ff` → `git push` → `git worktree remove` → `git branch -d` → Linear を Done に更新

## Development Rules

- Python 3.10+、依存は yfinance, pyyaml, numpy, pandas, pytest
- Grok API 利用時は `XAI_API_KEY` 環境変数を設定（未設定でも動作する）
- データ取得は必ず `src/data/yahoo_client.py` 経由（直接 yfinance を呼ばない）
- 新しい市場を追加する場合は `src/markets/base.py` の `Market` を継承
- `data/cache/`、`data/watchlists/`、`data/screening_results/` は gitignore 済み
- ポートフォリオデータ: `.claude/skills/stock-portfolio/data/portfolio.csv`
