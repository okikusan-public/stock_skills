# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

割安株スクリーニングシステム。Yahoo Finance API（yfinance）を使って日本株・米国株・ASEAN株・香港株・韓国株・台湾株等60地域から割安銘柄をスクリーニングする。Claude Code Skills として動作し、`/screen-stocks`、`/stock-report`、`/watchlist`、`/stress-test`、`/stock-portfolio` コマンドで利用する。

## Commands

```bash
# スクリーニング実行（EquityQuery方式 - デフォルト）
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset value --top 10

# 個別銘柄レポート
python3 .claude/skills/stock-report/scripts/generate_report.py 7203.T

# ウォッチリスト操作
python3 .claude/skills/watchlist/scripts/manage_watchlist.py list

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
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py list

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

  Rules: .claude/rules/
          intent-routing.md  ─ 自然言語→スキル判定ルール
          development.md     ─ 開発ルール・Git・テスト
          screening.md       ─ スクリーニング開発ルール (path-specific)
          portfolio.md       ─ ポートフォリオ開発ルール (path-specific)
          testing.md         ─ テスト開発ルール (path-specific)
```
