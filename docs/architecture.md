# Architecture

## System Overview

自然言語ファーストの投資分析システム。Agentic AI Pattern で設計。
ユーザーは日本語で意図を伝えるだけで、オーケストレーターが適切なエージェントを自律的に選択・起動する。

Claude Code Skills として動作し、Yahoo Finance API (yfinance) + Grok API (X/Web検索) + Neo4j (GraphRAG) + マルチLLM (Gemini/GPT/Grok) を統合。

---

## Layer Architecture

```mermaid
graph TD
    User["ユーザー（自然言語）"]

    subgraph Orchestrator["Orchestrator (.claude/skills/stock-skills/)"]
        SKILL["SKILL.md"]
        ROUTE["routing.yaml"]
        ORCH["orchestration.yaml"]
    end

    subgraph Agents[".claude/agents/"]
        SCR["Screener<br/>銘柄探し"]
        ANA["Analyst<br/>バリュエーション"]
        RES["Researcher<br/>ニュース・センチメント"]
        HC["Health Checker<br/>PFの事実・数値"]
        STR["Strategist<br/>投資判断・レコメンド"]
        REV["Reviewer<br/>品質・リスクチェック"]
    end

    subgraph Tools["tools/"]
        YF["yahoo_finance.py"]
        GR["graphrag.py"]
        GK["grok.py"]
        LLM["llm.py"]
    end

    subgraph Core["src/core/ (minimal)"]
        TU["ticker_utils"]
        CM["common"]
        PIO["portfolio_io"]
    end

    subgraph Data["src/data/"]
        YC["yahoo_client/"]
        GC["grok_client/"]
        GS["graph_store/"]
        GQ["graph_query/"]
        CTX["context/"]
    end

    User --> Orchestrator
    Orchestrator --> Agents
    Agents --> Tools
    Tools --> Core
    Tools --> Data
    Core --> Data
```

---

## Data Flow

```
1. ユーザー発言（自然言語）
   ↓
2. Orchestrator (SKILL.md)
   ├─ routing.yaml で意図→エージェントを判定
   ├─ 記録系（メモ・売買記録）→ 直接実行（action: direct）
   └─ 分析系 → エージェントをサブエージェントとして起動
   ↓
3. Agent (agent.md + examples.yaml)
   ├─ GraphRAG で過去のコンテキストを取得
   ├─ tools/ 経由でデータ取得
   ├─ 自律的に判断・計算・整形
   └─ 投資判断を伴う出力 → Reviewer を自動挿入
   ↓
4. Tools (tools/*.py)
   ├─ yahoo_finance: yfinance + 24h JSON cache
   ├─ graphrag: Neo4j GraphRAG (dual-write)
   ├─ grok: Grok API (X/Web検索)
   └─ llm: Gemini/GPT/Grok (マルチLLMレビュー)
   ↓
5. 結果表示 + GraphRAG に自動蓄積
   ↓
6. Orchestration (orchestration.yaml)
   ├─ 0件 → 条件緩和してリトライ
   ├─ Reviewer FAIL → 差し戻し
   └─ 上限到達 → 現状の結果を提示
```

---

## Design Principles

### 1. Natural Language First
ユーザーインターフェースは自然言語。`routing.yaml` がすべての入口。エージェントが自律的にパラメータを決定する。

### 2. Agentic AI Pattern
- **Orchestrator** (SKILL.md): どのエージェントを呼ぶか
- **Agents** (agent.md): 判断・計算・整形を自律実行
- **Tools** (tools/): データ取得のみ。判断しない
- **Few-shot** (examples.yaml): エージェントの行動をサンプルで示す

### 3. Dual-Write Pattern (JSON master + Neo4j view)
- JSON ファイルが master データソース（常に書き込み成功）
- Neo4j は view（検索・関連付け用）。try/except で graceful degradation
- Neo4j が落ちても全機能が動作する

### 4. Multi-LLM Review
Reviewer エージェントが3つのLLM（GPT/Gemini/Claude）を並列で起動し、異なる視点からレビュー。APIキー未設定時は全て Claude で実行（graceful degradation）。

### 5. Self-Healing Orchestration
orchestration.yaml に基づく自律修正ループ。スクリーニング0件→条件緩和、Reviewer FAIL→差し戻し。ユーザーに聞くのは売買の最終実行のみ。

---

## Agent Summary

| エージェント | 役割 | 使用ツール | デフォルトLLM |
|:---|:---|:---|:---|
| Screener | 銘柄探し・スクリーニング | yahoo_finance | Claude |
| Analyst | バリュエーション・割安度判定 | yahoo_finance, graphrag | Claude |
| Researcher | ニュース・センチメント・業界動向 | grok, graphrag | Grok |
| Health Checker | PFの事実・数値（判断しない） | yahoo_finance, graphrag | Claude |
| Strategist | 投資判断・レコメンド | yahoo_finance, graphrag | Claude |
| Reviewer | 品質・矛盾・リスクチェック | llm, graphrag | GPT+Gemini+Claude |

## Tool Summary

| ツール | ソース | 役割 |
|:---|:---|:---|
| yahoo_finance.py | src/data/yahoo_client/ | 株価・ファンダメンタルズ・スクリーニング |
| graphrag.py | src/data/graph_store/ + graph_query/ | Neo4j ナレッジグラフ |
| grok.py | src/data/grok_client/ | Grok API（X/Web検索） |
| llm.py | (直接API呼び出し) | Gemini/GPT/Grok マルチLLM |

## Config

| ファイル | 内容 |
|:---|:---|
| config/exchanges.yaml | 60+ 地域の取引所・通貨・閾値定義 |
| config/themes.yaml | テーマ定義（セクター・業種マッピング） |
| config/thresholds.yaml | グローバル閾値 |
