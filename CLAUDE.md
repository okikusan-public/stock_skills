# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Design Philosophy

**このシステムは「自然言語ファースト」の Agentic AI Pattern で設計されている。**

ユーザーはコマンドやパラメータを覚える必要はない。日本語で意図を伝えるだけで、オーケストレーターが適切なエージェントを自律的に選択・起動する。

- 「いい日本株ある？」→ Screener が自律的に region/preset を決めてスクリーニング
- 「トヨタってどう？」→ Analyst がバリュエーション・テクニカル分析を実行
- 「PF大丈夫かな」→ Health Checker が事実・数値を出し、Strategist がレコメンド
- 「最新ニュース教えて」→ Researcher が Grok API でニュース・センチメントを取得

エージェントはツール（tools/）を使ってデータを取得し、自分で判断・整形して出力する。

## Project Overview

投資アシスタントシステム。Yahoo Finance API（yfinance）、Grok API（xAI）、Neo4j（GraphRAG）を統合し、自然言語で銘柄探索・分析・ポートフォリオ管理・リスク評価を行う。Claude Code の Agentic AI Pattern で動作する。

## Commands

```bash
# ユニットテスト
python3 -m pytest tests/ -q

# E2E テスト（実際の API でエージェント動作検証）
python3 tests/e2e/run_e2e.py

# 依存インストール
pip install -r requirements.txt
```

エージェントが自律的にツールを呼び出すため、ユーザーがスクリプトを直接実行する必要はない。

## Architecture

詳細は [docs/architecture.md](docs/architecture.md)、[docs/neo4j-schema.md](docs/neo4j-schema.md) を参照。

```
Orchestrator (.claude/skills/stock-skills/)
  SKILL.md          — ルーティング・自律制御
  routing.yaml      — エージェント選択 few-shot
  orchestration.yaml — リトライ・エスカレーション

Agents (.claude/agents/)
  screener/     — 銘柄探し・スクリーニング
  analyst/      — 銘柄分析・バリュエーション評価
  researcher/   — ニュース・センチメント・業界動向
  health-checker/ — PFの事実・数値（判断しない）
  strategist/   — 投資判断・レコメンド
  risk-assessor/ — 市場リスク判定（risk-on/neutral/risk-off）
  reviewer/     — 品質・矛盾・リスクチェック（マルチLLM）

Tools (tools/)
  yahoo_finance.py — 株価・ファンダメンタルズ（src/data/yahoo_client/ のファサード）
  graphrag.py      — Neo4j ナレッジグラフ（src/data/graph_store/ + graph_query/ のファサード）
  grok.py          — Grok API 検索（src/data/grok_client/ のファサード）
  llm.py           — マルチLLM呼び出し（Gemini/GPT/Grok）
  portfolio_io.py  — PF CSV 読み書き（src/data/portfolio_io のファサード）
  notes.py         — 投資メモ読み書き（src/data/note_manager のファサード）
  watchlist.py     — ウォッチリスト読み書き（JSON直接I/O）
  scoring.py       — 3軸品質スコアリング（src/data/scoring.py のファサード）
  disclosure.py    — IR資料読み取り（MarkItDown+スクショ、src/data/disclosure_reader.py のファサード）

Data (src/data/)
  yahoo_client/  — yfinance ラッパー（24h JSONキャッシュ）
  grok_client/   — Grok API (xAI) ラッパー
  graph_store/   — Neo4j 書き込み（dual-write）
  graph_query/   — Neo4j 読み取り
  context/       — 自動コンテキスト注入
  history/       — 実行履歴ストア
  note_manager   — 投資メモ管理
  common.py      — 共通ユーティリティ（is_etf, safe_float 等）
  ticker_utils.py — ティッカー推論（通貨/地域マッピング）
  portfolio_io.py — PF CSV 読み書き
  scoring.py     — 3軸品質スコアリング（還元性・成長性・持続性）
  disclosure_reader.py — IR資料テキスト抽出+スクショ解析（MarkItDown+pdfplumber+PyMuPDF）

Config: .claude/agents/screener/examples.yaml (regions, themes, presets, few-shot)
Config: config/scoring.yaml (スコアリング重み・閾値・セクター別設定)
Rules:  .claude/rules/ (development, workflow, testing)
Docs:   docs/ (architecture, neo4j-schema, data-models)
Tests:  tests/ (unit), tests/e2e/ (E2E agent scenarios)
```

## Post-Implementation Rule

**機能実装後は必ず以下を確認・更新すること。**

- エージェント定義: 該当 `agent.md` + `examples.yaml`
- ルーティング: `routing.yaml` の triggers/examples
- ドキュメント: `CLAUDE.md`、`README.md`、`docs/architecture.md`
- テスト: `python3 -m pytest tests/ -q` で全件 PASS を確認
