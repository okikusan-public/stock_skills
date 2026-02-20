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
```
Skills (.claude/skills/*/SKILL.md → scripts/*.py) — 8スキル
Core   (src/core/) — screening/ portfolio/ risk/ research/ + proactive_engine (KIK-435), ...
Data   (src/data/) — yahoo_client, grok_client, history_store, graph_store, graph_linker (KIK-434), ...
Output (src/output/) — formatter, stress_formatter, portfolio_formatter, research_formatter

Config: config/screening_presets.yaml (11 presets), config/exchanges.yaml (60+ regions)
Rules:  .claude/rules/ (graph-context, intent-routing, workflow, development, screening, portfolio, testing)
Docs:   docs/ (architecture, neo4j-schema, skill-catalog)
```

## Post-Implementation Rule

**機能実装後は必ずドキュメント・ルールを更新すること。** 詳細は `.claude/rules/workflow.md` の「7. ドキュメント・ルール更新」を参照。

更新対象: `intent-routing.md`、該当 `SKILL.md`、`CLAUDE.md`、`rules/*.md`、`README.md`
