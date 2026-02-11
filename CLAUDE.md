# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

割安株スクリーニングシステム。Yahoo Finance API（yfinance）を使って日本株・米国株・ASEAN株から割安銘柄をスクリーニングする。Claude Code Skills として動作し、`/screen-stocks`、`/stock-report`、`/watchlist`、`/stress-test`、`/stock-portfolio` コマンドで利用する。

## Commands

```bash
# スクリーニング実行（EquityQuery方式 - デフォルト）
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset value --top 10
# region: japan / us / asean / sg / th / my / id / ph / hk / kr / tw / cn / all
# preset: value / high-dividend / growth-value / deep-value / quality / pullback
# sector (optional): Technology / Financial Services / Healthcare / Consumer Cyclical / Industrials
#                     Communication Services / Consumer Defensive / Energy / Basic Materials
#                     Real Estate / Utilities

# セクター指定の例
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region us --preset high-dividend --sector Technology

# Legacy モード（銘柄リスト方式、japan/us/asean のみ）
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset value --mode legacy

# 押し目買い型スクリーニング
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset pullback

# 後方互換: --market も使用可能
python3 .claude/skills/screen-stocks/scripts/run_screen.py --market japan --preset value

# 個別銘柄レポート
python3 .claude/skills/stock-report/scripts/generate_report.py 7203.T

# ウォッチリスト操作
python3 .claude/skills/watchlist/scripts/manage_watchlist.py list
python3 .claude/skills/watchlist/scripts/manage_watchlist.py add my-list 7203.T AAPL
python3 .claude/skills/watchlist/scripts/manage_watchlist.py show my-list
python3 .claude/skills/watchlist/scripts/manage_watchlist.py remove my-list 7203.T

# ストレステスト実行
python3 .claude/skills/stress-test/scripts/run_stress_test.py --portfolio 7203.T,AAPL,D05.SI
python3 .claude/skills/stress-test/scripts/run_stress_test.py --portfolio 7203.T,9984.T --scenario トリプル安
python3 .claude/skills/stress-test/scripts/run_stress_test.py --portfolio 7203.T,AAPL --weights 0.6,0.4 --scenario 米国リセッション

# ポートフォリオ管理
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py snapshot
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py buy --symbol 7203.T --shares 100 --price 2850 --currency JPY --date 2025-06-15 --memo トヨタ
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py sell --symbol AAPL --shares 5
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py analyze
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py list

# 依存インストール
pip install -r requirements.txt
```

テストフレームワーク未導入。テストを追加する場合は `tests/` に配置する。

## Architecture

```
Skills Layer (.claude/skills/*/SKILL.md)
  → Claudeへの指示書。ユーザーの /command を受けてスクリプトを実行する
      │
Script Layer (.claude/skills/*/scripts/*.py)
  → エントリーポイント。CLIでも直接実行可能
  → sys.path.insert で project root を追加して src/ を import する
      │
  ┌───┴────────────────────┐
  │                        │
Core Layer (src/core/)     Market Layer (src/markets/)
  │                        │
  ├─ screener.py           ├─ base.py    … 抽象基底クラス Market
  │   ValueScreener +      ├─ japan.py   … .T suffix, get_region()="jp"
  │   QueryScreener +      ├─ us.py      … get_region()="us"
  │   PullbackScreener     └─ asean.py   … get_region()=["sg","th",...]
  │
  ├─ query_builder.py      Config Layer (config/)
  │   build_query() →       ├─ screening_presets.yaml
  │   EquityQuery 構築      └─ exchanges.yaml … 取引所ナレッジ
  │
  ├─ filters.py
  │   apply_filters()
  │
  ├─ indicators.py
  │   calculate_value_score() → 0-100点
  │
  ├─ sharpe.py
  │   calculate_hv() / calculate_upside_downside_vol()
  │
  ├─ concentration.py
  │   compute_hhi() / analyze_concentration()
  │   セクター・地域・通貨の3軸HHI算出
  │
  ├─ shock_sensitivity.py  (Team 2)
  │   compute_shock_sensitivity()
  │
  ├─ scenario_analysis.py  (Team 3)
  │   analyze_scenario()
  │
  ├─ portfolio_manager.py  (Team 2 - PF管理)
  │   load_portfolio() / save_portfolio()
  │   add_position() / sell_position()
  │
  └─ technicals.py
      detect_pullback_in_uptrend()
      compute_rsi() / compute_bollinger_bands()
      │
Data Layer (src/data/)     Output Layer (src/output/)
  └─ yahoo_client.py         ├─ formatter.py
      get_stock_info()        │   format_markdown()
      get_stock_detail()      │   format_query_markdown()
      screen_stocks()         │   format_pullback_markdown()
      get_price_history()     │
      24時間TTLのJSONキャッシュ│
                              ├─ stress_formatter.py (Team 3)
                              │   format_stress_report()
                              │
                              └─ portfolio_formatter.py (Team 3 - PF管理)
                                  format_snapshot() / format_structure_analysis()
```

## Three Screening Engines

### QueryScreener（EquityQuery方式 - デフォルト）
yfinance の EquityQuery API を使い、銘柄リストなしで Yahoo Finance のスクリーナーに直接条件を送信。`query_builder.build_query()` で region/exchange/sector/criteria を EquityQuery に変換し、`yahoo_client.screen_stocks()` で実行。結果は `_normalize_quote()` で正規化後、`calculate_value_score()` でスコア付け。対応地域は約60（jp, us, sg, th, my, id, ph, hk, kr, tw, cn 等）。`--mode query` (デフォルト) で使用。

### ValueScreener（バリュースコア方式 - Legacy）
`config/screening_presets.yaml` の criteria で `apply_filters()` → `calculate_value_score()` の順に処理。スコアは100点満点: PER(25) + PBR(25) + 配当利回り(20) + ROE(15) + 売上成長率(15)。`get_stock_info()` の基本データのみ使用。`--mode legacy` で使用。

### PullbackScreener（押し目買い型）
2段パイプライン: EquityQuery(ファンダ) → テクニカル判定(detect_pullback_in_uptrend)。value_score でスコアリング。
上昇トレンド中の一時調整（-5%〜-20%）を検出。3条件: (1)株価>200日MA＋50日MA>200日MA、
(2)60日高値から-5%〜-20%、(3)RSI30-40反転＋出来高低下 or BB下限タッチ。`--preset pullback` で使用。

## yahoo_client のデータ取得パターン

2つのレベルがある:
- **`get_stock_info(symbol)`**: `ticker.info` のみ。バリュースクリーニング用。キャッシュは `{symbol}.json`。
- **`get_stock_detail(symbol)`**: `get_stock_info` + price_history(6ヶ月) + balance_sheet + cashflow + income_stmt。拡張分析用。キャッシュは `{symbol}_detail.json`。

## Key Design Decisions

- **yahoo_client はモジュール関数**（クラスではない）。`from src.data import yahoo_client` で import し、`yahoo_client.get_stock_info(symbol)` のように使う。
- **配当利回りの正規化**: yfinance v1.1.0 は `dividendYield` をパーセント値（例: 2.56）で返すことがある。`_normalize_ratio()` が値 > 1 の場合に 100 で割って比率に変換する。
- **フィールド名のエイリアス**: indicators.py は yfinance 生キー（`trailingPE`, `priceToBook`）と正規化済みキー（`per`, `pbr`）の両方を `or` で対応する。
- **Market クラス**: 各市場は `format_ticker()`、`get_default_symbols()`、`get_thresholds()`、`get_region()`、`get_exchanges()` を提供。`get_thresholds()` は `rf`（無リスク金利）も含む（日本:0.5%, 米国:4%, ASEAN:3%）。
- **キャッシュ**: `data/cache/` に銘柄ごとのJSONファイル。TTL 24時間。API呼び出しの間に1秒のディレイ。
- **プリセット**: `config/screening_presets.yaml` で定義。

## Development Rules

- Python 3.10+、依存は yfinance, pyyaml, numpy
- データ取得は必ず `src/data/yahoo_client.py` 経由（直接 yfinance を呼ばない）
- 新しい市場を追加する場合は `src/markets/base.py` の `Market` を継承
- `data/cache/`、`data/watchlists/`、`data/screening_results/` は gitignore 済み
