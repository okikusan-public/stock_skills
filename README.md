# stock-skills

投資アシスタントシステム。Agentic AI Pattern で設計。自然言語で話しかけるだけで、銘柄探索・分析・ポートフォリオ管理・リスク評価が自動実行される。

## セットアップ

```bash
pip install -r requirements.txt
```

Python 3.10+ が必要。依存: yfinance, pyyaml, numpy, pandas, requests, python-dotenv

### 環境変数

```bash
# Grok API（Xセンチメント分析、任意）
export XAI_API_KEY=xai-xxxxxxxxxxxxx

# Gemini API（マルチLLMレビュー、任意）
export GEMINI_API_KEY=AIzaSy...

# OpenAI API（マルチLLMレビュー、任意）
export OPENAI_API_KEY=sk-proj-...

# Neo4j（GraphRAG、任意）
export NEO4J_URI=bolt://localhost:7688
export NEO4J_MODE=full  # off/summary/full
```

すべて任意。未設定でもデフォルト値で動作する。

## 使い方

自然言語で話しかけるだけ:

```
「いい日本株ある？」      → Screener が自律的にスクリーニング
「トヨタってどう？」      → Analyst がバリュエーション分析
「最新ニュース教えて」    → Researcher が Grok API でニュース取得
「PF大丈夫？」           → Health Checker が数値を出し、Strategist がレコメンド
「暴落したらどうなる？」   → Health Checker がストレステスト実行
「メモしておいて」        → 投資メモを直接保存
```

## アーキテクチャ

```
Orchestrator (.claude/skills/stock-skills/)
  ├─ SKILL.md          — ルーティング・自律制御
  ├─ routing.yaml      — エージェント選択 few-shot
  └─ orchestration.yaml — リトライ・エスカレーション

Agents (.claude/agents/)
  ├─ screener/      — 銘柄探し（region/preset/theme を自律決定）
  ├─ analyst/       — バリュエーション・割安度・ETF評価
  ├─ researcher/    — ニュース・センチメント・業界・市況
  ├─ health-checker/ — PFの事実・数値（判断しない）
  ├─ strategist/    — 投資判断・レコメンド（他エージェントの結果を統合）
  └─ reviewer/      — 品質・リスクチェック（GPT+Gemini+Claude 並列レビュー）

Tools (tools/)
  ├─ yahoo_finance.py — 株価・ファンダメンタルズ
  ├─ graphrag.py      — Neo4j ナレッジグラフ
  ├─ grok.py          — Grok API（X/Web検索）
  └─ llm.py           — マルチLLM（Gemini/GPT/Grok）

Data (src/data/) — yahoo_client, grok_client, graph_store, graph_query, common, ticker_utils, portfolio_io
```

詳細は [docs/architecture.md](docs/architecture.md) を参照。

## Neo4j ナレッジグラフ（オプション）

エージェント実行履歴を Neo4j に蓄積し、過去の分析・取引・リサーチを横断検索できる。

```bash
docker compose up -d
```

Neo4j 未接続でも全機能が正常動作する（graceful degradation）。

## テスト

```bash
python3 -m pytest tests/ -q   # 約2548テスト (~12秒)
```

## 免責事項

本ソフトウェアは投資判断の参考情報を提供するものであり、**投資成果を保証するものではありません**。本ソフトウェアの出力に基づく投資判断はすべて利用者自身の責任で行ってください。開発者は、本ソフトウェアの利用により生じたいかなる損害についても責任を負いません。

## ライセンス

本ソフトウェアはライセンスフリーです。誰でも自由に利用・改変・再配布できます。
