# 開発ルール

## 言語・依存

- Python 3.10+
- 主要依存: yfinance, pyyaml, numpy, pandas, pytest, requests, python-dotenv
- Grok API 利用時は `XAI_API_KEY` 環境変数を設定（未設定でも動作する）
- Gemini API 利用時は `GEMINI_API_KEY` 環境変数を設定（未設定でも動作する）
- OpenAI API 利用時は `OPENAI_API_KEY` 環境変数を設定（未設定でも動作する）
- Neo4j 書き込み深度は `NEO4J_MODE` 環境変数で制御: `off`/`summary`/`full`（デフォルト: 接続可能なら `full`）
- TEI ベクトル検索は `TEI_URL` 環境変数で制御（デフォルト: `http://localhost:8081`）。未起動時はベクトル検索スキップ
- Linear 連携は `LINEAR_ENABLED=on` で有効化（デフォルト: off）

## コーディング規約

### ツール層 (tools/)
- 薄いファサード。`src/data/` の関数を re-export するだけ
- 判断ロジックを含めない
- `try/except ImportError` で `HAS_*` フラグを設定し graceful degradation

### エージェント層 (.claude/agents/)
- `agent.md` — 役割・判断プロセス・使用ツール・出力方針
- `examples.yaml` — few-shot（intent → steps → reasoning）
- エージェントが判断・計算・整形を全て担う

### データ層 (src/data/)
- データ取得は必ず `src/data/yahoo_client/` 経由（直接 yfinance を呼ばない）
- yahoo_client はモジュール関数（クラスではない）
- 配当利回りの正規化: `_normalize_ratio()` が値 > 1 の場合 100 で割って比率に変換
- データモデル定義: `docs/data-models.md` を参照

### コア層 (src/core/)
- サブフォルダ構成（screening/, portfolio/, risk/, research/, health/）
- 新モジュールは適切なサブフォルダに配置
- import は直接パス（`src.core.screening.screener` 等）を使用

## テスト

- `python3 -m pytest tests/ -q` で全テスト実行（約979テスト、~4秒）
- `tests/conftest.py` に共通フィクスチャ: `stock_info_data`, `stock_detail_data`, `price_history_df`, `mock_yahoo_client`
- `tests/conftest.py` に autouse `_block_external_io` フィクスチャ: Neo4j/TEI/Grok を全テストで自動モック
- `tests/fixtures/` に JSON/CSV テストデータ（Toyota 7203.T ベース）
- テストファイルは `tests/core/`, `tests/data/` に機能別に配置

## Git ワークフロー

開発フロー（Worktree作成→設計→実装→テスト→レビュー→結合試験→マージ）は [workflow.md](workflow.md) を参照。

- ブランチ名: `feature/kik-{NNN}-{short-desc}`
- ワークツリー: `~/stock-skills-kik{NNN}`

## ファイル構成ガイドライン

### サイズ上限
- プロダクションコード: 400行以下推奨、500行で分割検討
- テスト: 600行以下推奨
- エージェント定義: agent.md は簡潔に、examples.yaml は20例程度

### 新モジュール配置
- ドメインロジック → src/core/{screening,portfolio,risk,research,health}/
- データ取得/保存 → src/data/{yahoo_client,graph_store,graph_query,history,context}/
- ツールファサード → tools/
- エージェント定義 → .claude/agents/<name>/
- テスト → tests/{core,data}/（src/ と1:1対応）

## ドキュメント構成

- `docs/architecture.md` — システムアーキテクチャ（Agentic AI Pattern、Mermaid図）
- `docs/neo4j-schema.md` — Neo4j スキーマリファレンス（ノードタイプ、リレーション）
- `docs/data-models.md` — stock_info / stock_detail dict スキーマ定義

## 自動コンテキスト注入

- `src/data/context/` — コンテキスト取得エンジン（シンボル検出 + グラフ状態判定）
- `tools/graphrag.py` の `get_context()` 経由でエージェントが取得
- Neo4j 未接続時は graceful degradation

## gitignore 対象

- `data/cache/` — 銘柄ごと JSON キャッシュ（TTL 24時間）
- `data/watchlists/` — ウォッチリストデータ
- `data/screening_results/` — スクリーニング結果
- `data/notes/` — 投資メモデータ
- ポートフォリオデータ: `data/portfolio.csv`
