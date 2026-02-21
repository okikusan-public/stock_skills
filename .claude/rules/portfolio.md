---
paths:
  - "src/core/portfolio/**"
  - "src/core/risk/**"
  - "src/core/health_check.py"
  - "src/core/return_estimate.py"
  - "src/core/value_trap.py"
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

## ヘルスチェック (KIK-356/357/374/403/438)

- `check_trend_health()`: SMA50/200, RSI から「上昇/横ばい/下降」を判定
  - **ゴールデンクロス/デッドクロス検出（KIK-374）**: 60日 lookback でクロスイベントを検出。`cross_signal`, `days_since_cross`, `cross_date` を返す
  - **小型株クロスルックバック短縮（KIK-438）**: 小型株は `cross_lookback=30` で直近の変動を早期検出
- `check_change_quality()`: alpha.py の `compute_change_score()` を再利用。ETF は `_is_etf()` で検出し `quality_label="対象外"`
- `compute_alert_level()`: 3段階（早期警告/注意/撤退）。撤退にはテクニカル崩壊+ファンダ悪化の両方が必要。デッドクロス検出時は EXIT 発動
  - **株主還元安定度（KIK-403）**: `temporary`（一時的高還元）→ EARLY_WARNING 昇格、`decreasing`（減少傾向）→ 理由追加のみ
  - **小型株アラート引き上げ（KIK-438）**: `is_small_cap=True` の場合、EARLY_WARNING → CAUTION に自動昇格
- `check_long_term_suitability()`: 長期適性判定。`shareholder_return_data` があれば `total_return_rate`（配当+自社株買い）で判定、なければ `dividend_yield` にフォールバック
- ETF判定: `_is_etf()` は `bool()` truthiness チェック

## 小型株アロケーション (KIK-438)

- `src/core/portfolio/small_cap.py`: 小型株分類・アロケーション判定の一元モジュール
- `classify_market_cap(market_cap, region_code)`: 地域別閾値で「小型/中型/大型/不明」に分類
  - JP: ≤1000億円、US: ≤$1B、SG: ≤SGD 2B、他は `_SMALL_CAP_THRESHOLDS` 参照
  - 大型閾値 = 小型閾値 × 5
- `check_small_cap_allocation(small_cap_weight)`: PF全体の小型株比率をチェック
  - `>25%` → warning、`>35%` → critical（`thresholds.yaml` で設定可能）
- `src/core/ticker_utils.py` に `infer_region_code()` を追加（suffix → 2文字リージョンコード）
- ヘルスチェック出力: `[小型]` バッジ付きシンボル + PF全体の小型株比率サマリー
- 構造分析（analyze）: 規模別構成テーブル（大型/中型/小型/不明）+ size_hhi を追加（4軸化）

## 株主還元率 (KIK-375)

- `calculate_shareholder_return()`: 配当 + 自社株買い の総還元率を算出
- yahoo_client が cashflow から `dividend_paid` と `stock_repurchase` を抽出（3段階フォールバック）
- stock-report で「## 株主還元」セクションに出力

## リターン推定 (KIK-359/360)

- 株式: yfinance の `targetHighPrice`/`targetMeanPrice`/`targetLowPrice` から期待リターン算出
- ETF: 過去2年の月次リターンから CAGR を算出し ±1σ でシナリオ分岐（キャップ±30%）
- ニュース: yfinance `ticker.news` で公式メディアニュースを取得
- Xセンチメント: Grok API (`grok-4-1-fast-non-reasoning` + X Search)。`XAI_API_KEY` 未設定時スキップ

## リバランス (KIK-363)

- 3戦略: defensive（10%, 0.20）、balanced（15%, 0.25）、aggressive（25%, 0.35）
- アクション生成: (1) sell: health=EXIT or base<-10%, (2) reduce: overweight/相関集中, (3) increase: 正リターン+制約内

## 入替提案ルール (KIK-450)

PF 入替提案（EXIT 銘柄の乗り換え・代替候補の提示）を行う際は、**必ず `what-if` シミュレーションを実行してから提案する**。

- **スワップ提案時**: `what-if --remove "<EXIT銘柄>:SHARES" --add "<代替>:SHARES:PRICE"` を実行し、HHI変化・資金収支・判定ラベルをユーザーに提示する
- **追加提案のみの場合**: `what-if --add "<追加銘柄>:SHARES:PRICE"` を実行してから提案する
- シミュレーションを実行せず口頭だけで「〇〇に乗り換えてはどうか」と提案することは禁止
- **単元株コスト制限**: 1単元コスト（株数 × 株価）が PF 総額の 20% を超える場合は「1単元 ¥XX 万はPF総額の YY% 相当のため高額です」と必ず明記する
- `what-if` 実行に必要な株価が不明な場合は `yahoo_client.get_stock_info(symbol)["price"]` を取得してから計算する

### 提案フロー（必須手順）

1. `health` で EXIT/注意銘柄を検出
2. `/screen-stocks`（同セクター/リージョン）で代替候補を検索
3. **`what-if --remove "<EXIT銘柄>:<保有株数>" --add "<代替>:<株数>:<株価>"` を実行**
4. シミュレーション結果（HHI変化・資金収支・スワップ判定）を提示してから提案する

## シナリオ分析 (KIK-354/358)

- 8シナリオ: トリプル安、ドル高円安、米国リセッション、日銀利上げ、米中対立、インフレ再燃、テック暴落、円高ドル安
- `SCENARIO_ALIASES` で自然言語入力に対応
- ETF資産クラスマッチング: `_ETF_ASSET_CLASS` マッピングで金・長期債・株式インカムに分類
- `_match_target()`: 地域→通貨→輸出/内需→ETF資産クラス→非テック→セクターの優先順
