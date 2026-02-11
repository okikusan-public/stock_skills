# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

割安株スクリーニングシステム。Yahoo Finance API（yfinance）を使って日本株・米国株・ASEAN株から割安銘柄をスクリーニングする。Claude Code Skills として動作し、`/screen-stocks`、`/stock-report`、`/watchlist` コマンドで利用する。

## Commands

```bash
# スクリーニング実行
python3 .claude/skills/screen-stocks/scripts/run_screen.py --market japan --preset value --top 10

# 個別銘柄レポート
python3 .claude/skills/stock-report/scripts/generate_report.py 7203.T

# ウォッチリスト操作
python3 .claude/skills/watchlist/scripts/manage_watchlist.py list
python3 .claude/skills/watchlist/scripts/manage_watchlist.py add my-list 7203.T AAPL
python3 .claude/skills/watchlist/scripts/manage_watchlist.py show my-list

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
      │
  ┌───┴────────────────────┐
  │                        │
Core Layer (src/core/)     Market Layer (src/markets/)
  │                        │
  ├─ screener.py           ├─ base.py    … 抽象基底クラス Market
  │   ValueScreener が     ├─ japan.py   … .T suffix, Nikkei225
  │   全体を統合           ├─ us.py      … suffix なし, S&P500
  │                        └─ asean.py   … .SI/.BK/.KL/.JK/.PS
  ├─ filters.py
  │   apply_filters()
  │
  └─ indicators.py
      calculate_value_score() → 0-100点
      │
Data Layer (src/data/)
  └─ yahoo_client.py
      get_stock_info() / get_multiple_stocks()
      24時間TTLのJSONキャッシュ (data/cache/)
```

## Key Design Decisions

- **yahoo_client はモジュール関数**（クラスではない）。`from src.data import yahoo_client` で import し、`yahoo_client.get_stock_info(symbol)` のように使う。
- **配当利回りの正規化**: yfinance v1.1.0 は `dividendYield` をパーセント値（例: 2.56）で返すことがある。`_normalize_ratio()` が値 > 1 の場合に 100 で割って比率に変換する。
- **スクリーニングプリセット**: `config/screening_presets.yaml` に5種類定義。各プリセットは `max_per`、`max_pbr`、`min_dividend_yield`、`min_roe`、`min_revenue_growth` の組み合わせ。
- **Market クラス**: 各市場は `format_ticker()`（取引所サフィックスの付与）、`get_default_symbols()`（デフォルト銘柄リスト）、`get_thresholds()`（市場固有の閾値）を提供する。
- **キャッシュ**: `data/cache/` に銘柄ごとのJSONファイル。TTL 24時間。API呼び出しの間に1秒のディレイ。

## Development Rules

- Python 3.10+
- データ取得は必ず `src/data/yahoo_client.py` 経由（直接 yfinance を呼ばない）
- 新しい市場を追加する場合は `src/markets/base.py` の `Market` を継承
- `data/cache/`、`data/watchlists/` は gitignore 済み
