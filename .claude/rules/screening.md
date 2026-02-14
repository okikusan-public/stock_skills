---
paths:
  - "src/core/screener.py"
  - "src/core/indicators.py"
  - "src/core/query_builder.py"
  - "src/core/filters.py"
  - "src/core/alpha.py"
  - "src/core/technicals.py"
  - ".claude/skills/screen-stocks/**"
  - "config/screening_presets.yaml"
---

# スクリーニング開発ルール

## 4つのスクリーナーエンジン

- **QueryScreener（デフォルト）**: `build_query()` → `screen_stocks()` [EquityQuery bulk API] → `_normalize_quote()` → `calculate_value_score()` → ソート
- **ValueScreener（Legacy）**: 銘柄リスト方式。`get_stock_info()` → `apply_filters()` → `calculate_value_score()`。japan/us/asean のみ
- **PullbackScreener**: 3段パイプライン。EquityQuery → `detect_pullback_in_uptrend()` → value_score。"full"（完全一致）と"partial"（bounce_score>=30）の2種
- **AlphaScreener**: 4段パイプライン。EquityQuery(割安足切り) → `compute_change_score()` → 押し目判定 → 2軸スコアリング

## バリュースコア配分

PER(25) + PBR(25) + 配当利回り(20) + ROE(15) + 売上成長率(15) = 100点

## EquityQuery ルール

- フィールド名は yfinance 準拠（`trailingPE`, `priceToBook`, `dividendYield` 等）
- プリセットは `config/screening_presets.yaml` で定義。criteria の閾値を YAML で管理

## yahoo_client データ取得

- `get_stock_info(symbol)`: `ticker.info` のみ。キャッシュ `{symbol}.json` (24h TTL)
- `get_stock_detail(symbol)`: info + price_history + balance_sheet + cashflow + income_stmt。キャッシュ `{symbol}_detail.json`
- `screen_stocks(query)`: EquityQuery ベースのバルクスクリーニング（キャッシュなし）
- `get_price_history(symbol, period)`: OHLCV DataFrame（キャッシュなし、デフォルト1年分）

## 異常値ガード

`_sanitize_anomalies()` で以下をサニタイズ:
- 配当利回り > 15% → None
- PBR < 0.1 or PBR > 100 → None
- PER < 0 or PER > 500 → None
- ROE > 200% → None
