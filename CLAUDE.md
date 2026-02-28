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

各スキルのコマンド詳細は [docs/skill-catalog.md](docs/skill-catalog.md) を参照。

### 代表コマンド
```bash
# スクリーニング
python3 .claude/skills/screen-stocks/scripts/run_screen.py --region japan --preset alpha --top 10

# 個別レポート
python3 .claude/skills/stock-report/scripts/generate_report.py 7203.T

# ポートフォリオ
python3 .claude/skills/stock-portfolio/scripts/run_portfolio.py snapshot

# テスト
python3 -m pytest tests/ -q

# 依存インストール
pip install -r requirements.txt
```

## Architecture

詳細は [docs/architecture.md](docs/architecture.md)（3層構成・Mermaid図）、[docs/neo4j-schema.md](docs/neo4j-schema.md)（グラフスキーマ）、[docs/skill-catalog.md](docs/skill-catalog.md)（8スキル）を参照。

### レイヤー概要
<!-- BEGIN AUTO-GENERATED ARCHITECTURE -->
```
Skills (.claude/skills/*/SKILL.md → scripts/*.py) — 8スキル
Core   (src/core/) — portfolio/, ports/, research/, risk/, screening/, action_item_bridge (KIK-472: GraphRAG紐付け), action_item_detector (KIK-472: Linear連携), common, health_check (KIK-469: ETF対応+PF統合), health_etf (KIK-469/512: ETFヘルスチェック), health_labels (KIK-371/512: 長期適性ラベル生成), models, proactive_engine (KIK-435), return_estimate (KIK-469 P2: volatility+is_etf), ticker_utils (KIK-449), value_trap (KIK-381)
Data   (src/data/) — graph_query/ (KIK-508: submodule分割), graph_store/ (KIK-507: submodule分割), grok_client/ (KIK-508: submodule分割), yahoo_client/ (KIK-449: submodule分割, KIK-469: ETFフィールド), auto_context (KIK-411/420: ハイブリッド検索), embedding_client (KIK-420: TEIベクトル検索), graph_linker (KIK-434), graph_nl_query (KIK-411), grok_context (KIK-488: Neo4j知識→Grokプロンプト注入), history_helpers (KIK-512: シリアライズ・埋め込みヘルパー), history_load (KIK-512: load/query関数群), history_save (KIK-512: save_*関数群), history_store (KIK-428), linear_client (KIK-472), note_manager (KIK-473: journal type + auto symbol detection), screen_annotator (KIK-452: GraphRAGコンテキスト), screening_context (KIK-452), summary_builder
Output (src/output/) — adjust_formatter (KIK-496), analyze_formatter, forecast_formatter, formatter, health_formatter (KIK-469 P2: stock/ETFテーブル分離), portfolio_formatter, rebalance_formatter (KIK-376), research_formatter, review_formatter (KIK-441), screening_summary_formatter (KIK-452/532), simulate_formatter (KIK-376), stress_formatter

Config: config/screening_presets.yaml (15 presets), config/exchanges.yaml (60+ regions)
Rules:  .claude/rules/ (graph-context, intent-routing, workflow, development, screening, portfolio, testing)
Docs:   docs/ (architecture, neo4j-schema, skill-catalog, api-reference, data-models)
```
<!-- END AUTO-GENERATED ARCHITECTURE -->

## Post-Implementation Rule

**機能実装後は必ずドキュメント・ルールを更新すること。** 詳細は `.claude/rules/workflow.md` の「7. ドキュメント・ルール更新」を参照。

自動生成: `docs/api-reference.md`、`CLAUDE.md` Architecture、`development.md` テスト数、`docs/skill-catalog.md` 概要（pre-commit hook で自動実行）
手動更新: `intent-routing.md`、該当 `SKILL.md`、`rules/*.md`、`README.md`
