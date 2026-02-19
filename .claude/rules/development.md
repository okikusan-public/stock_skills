# 開発ルール

## 言語・依存

- Python 3.10+
- 主要依存: yfinance, pyyaml, numpy, pandas, pytest
- Grok API 利用時は `XAI_API_KEY` 環境変数を設定（未設定でも動作する）
- Neo4j 書き込み深度は `NEO4J_MODE` 環境変数で制御: `off`/`summary`/`full`（デフォルト: 接続可能なら `full`）(KIK-413)
- TEI ベクトル検索は `TEI_URL` 環境変数で制御（デフォルト: `http://localhost:8081`）。未起動時はベクトル検索スキップ (KIK-420)
- コンテキスト鮮度閾値は `CONTEXT_FRESH_HOURS`（デフォルト: 24）/ `CONTEXT_RECENT_HOURS`（デフォルト: 168）で制御 (KIK-427)

## コーディング規約

- データ取得は必ず `src/data/yahoo_client.py` 経由（直接 yfinance を呼ばない）
- 新しい市場を追加する場合は `src/markets/base.py` の `Market` を継承
- `HAS_MODULE` パターン: スクリプト層（run_*.py）は `try/except ImportError` で各モジュールの存在を確認し、`HAS_*` フラグで graceful degradation
- yahoo_client はモジュール関数（クラスではない）。`from src.data import yahoo_client` → `yahoo_client.get_stock_info(symbol)`
- 配当利回りの正規化: `_normalize_ratio()` が値 > 1 の場合 100 で割って比率に変換
- フィールド名のエイリアス: indicators.py は yfinance 生キー（`trailingPE`, `priceToBook`）と正規化済みキー（`per`, `pbr`）の両方を対応
- `src/core/` はサブフォルダ構成（screening/, portfolio/, risk/, research/）。新モジュールは適切なサブフォルダに配置。import は直接パス（`src.core.screening.screener` 等）を使用

## テスト

- `python3 -m pytest tests/ -q` で全テスト実行（約1706テスト、~5秒）
- `tests/conftest.py` に共通フィクスチャ: `stock_info_data`, `stock_detail_data`, `price_history_df`, `mock_yahoo_client`
- `tests/fixtures/` に JSON/CSV テストデータ（Toyota 7203.T ベース）
- `mock_yahoo_client` は monkeypatch で yahoo_client モジュール関数をモック
- テストファイルは `tests/core/`, `tests/data/`, `tests/output/` に機能別に配置

## Git ワークフロー

- Linear issue（KIK-NNN）ごとに `git worktree add` でワークツリーを作成: `~/stock-skills-kik{NNN}`
- ブランチ名: `feature/kik-{NNN}-{short-desc}`
- 完了後: `git merge --no-ff` → `git push` → `git worktree remove` → `git branch -d` → Linear を Done に更新

## ドキュメント更新リマインダー (KIK-407)

3レイヤーで `src/core/` `src/data/` 変更時のドキュメント更新漏れを防止:

1. **PostToolUse hook**: Edit/Write で `src/(core|data)/*.py` 変更時にリマインドメッセージ表示
2. **Stop hook**: 会話終了時に未更新ドキュメントを指摘
3. **pre-commit hook**: `scripts/hooks/pre-commit` — src/ 変更 + doc 未更新の commit をブロック（`--no-verify` でバイパス可）

## ドキュメント構成 (KIK-412)

- `docs/architecture.md` — システムアーキテクチャ（3層構成、Mermaid図、設計原則、モジュール一覧）
- `docs/neo4j-schema.md` — Neo4j スキーマリファレンス（11ノードタイプ、リレーション、制約/インデックス、サンプルCypher）
- `docs/skill-catalog.md` — 8スキルのカタログ（概要、コマンド例、Core依存、出力形式）

新しいスキルやノードタイプを追加した場合は対応するドキュメントも更新すること。

## 自動コンテキスト注入 (KIK-411)

- `.claude/rules/graph-context.md` — スキル実行前にティッカー/企業名を検出し、Neo4j から過去の経緯を取得するルール
- `src/data/auto_context.py` — コンテキスト取得エンジン（シンボル検出 + グラフ状態判定 + スキル推奨）
- `scripts/get_context.py` — CLI ラッパー（Bash 経由で呼び出し）
- Neo4j 未接続時は graceful degradation（「コンテキストなし」→ intent-routing のみで判断）

## gitignore 対象

- `data/cache/` — 銘柄ごと JSON キャッシュ（TTL 24時間）
- `data/watchlists/` — ウォッチリストデータ
- `data/screening_results/` — スクリーニング結果
- `data/notes/` — 投資メモデータ
- ポートフォリオデータ: `.claude/skills/stock-portfolio/data/portfolio.csv`
