---
paths:
  - "src/core/portfolio_manager.py"
  - "src/core/portfolio_bridge.py"
  - "src/core/health_check.py"
  - "src/core/return_estimate.py"
  - "src/core/rebalancer.py"
  - "src/core/concentration.py"
  - "src/core/correlation.py"
  - "src/core/shock_sensitivity.py"
  - "src/core/scenario_analysis.py"
  - "src/core/recommender.py"
  - "src/output/portfolio_formatter.py"
  - "src/output/stress_formatter.py"
  - ".claude/skills/stock-portfolio/**"
  - ".claude/skills/stress-test/**"
---

# ポートフォリオ・ストレステスト開発ルール

## ポートフォリオ管理

- CSV ベース: `.claude/skills/stock-portfolio/data/portfolio.csv`
- `.CASH` シンボル（JPY.CASH, USD.CASH）は Yahoo Finance API をスキップ
- `_is_cash()` / `_cash_currency()` ヘルパーで判定

## ヘルスチェック (KIK-356/357)

- `check_trend_health()`: SMA50/200, RSI から「上昇/横ばい/下降」を判定
- `check_change_quality()`: alpha.py の `compute_change_score()` を再利用。ETF は `_is_etf()` で検出し `quality_label="対象外"`
- `compute_alert_level()`: 3段階（早期警告/注意/撤退）。撤退にはテクニカル崩壊+ファンダ悪化の両方が必要
- ETF判定: `_is_etf()` は `bool()` truthiness チェック

## リターン推定 (KIK-359/360)

- 株式: yfinance の `targetHighPrice`/`targetMeanPrice`/`targetLowPrice` から期待リターン算出
- ETF: 過去2年の月次リターンから CAGR を算出し ±1σ でシナリオ分岐（キャップ±30%）
- ニュース: yfinance `ticker.news` で公式メディアニュースを取得
- Xセンチメント: Grok API (`grok-4-1-fast-non-reasoning` + X Search)。`XAI_API_KEY` 未設定時スキップ

## リバランス (KIK-363)

- 3戦略: defensive（10%, 0.20）、balanced（15%, 0.25）、aggressive（25%, 0.35）
- アクション生成: (1) sell: health=EXIT or base<-10%, (2) reduce: overweight/相関集中, (3) increase: 正リターン+制約内

## シナリオ分析 (KIK-354/358)

- 8シナリオ: トリプル安、ドル高円安、米国リセッション、日銀利上げ、米中対立、インフレ再燃、テック暴落、円高ドル安
- `SCENARIO_ALIASES` で自然言語入力に対応
- ETF資産クラスマッチング: `_ETF_ASSET_CLASS` マッピングで金・長期債・株式インカムに分類
- `_match_target()`: 地域→通貨→輸出/内需→ETF資産クラス→非テック→セクターの優先順
