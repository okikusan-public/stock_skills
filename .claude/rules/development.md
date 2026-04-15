# 開発ルール

## 言語・依存

- Python 3.10+
- 主要依存: yfinance, pyyaml, numpy, pandas, pytest
- Grok API 利用時は `XAI_API_KEY` 環境変数を設定（未設定でも動作する）
- Neo4j 書き込み深度は `NEO4J_MODE` 環境変数で制御: `off`/`summary`/`full`（デフォルト: 接続可能なら `full`）(KIK-413)
- TEI ベクトル検索は `TEI_URL` 環境変数で制御（デフォルト: `http://localhost:8081`）。未起動時はベクトル検索スキップ (KIK-420)
- コンテキスト鮮度閾値は `CONTEXT_FRESH_HOURS`（デフォルト: 24）/ `CONTEXT_RECENT_HOURS`（デフォルト: 168）で制御 (KIK-427)
- Linear 連携は `LINEAR_ENABLED=on` で有効化（デフォルト: off）。`LINEAR_API_KEY`（APIトークン）、`LINEAR_TEAM_ID`（issue作成先チームID）、`LINEAR_PROJECT_ID`（任意、プロジェクトID）を設定 (KIK-472)

## コーディング規約

- データ取得は必ず `src/data/yahoo_client.py` 経由（直接 yfinance を呼ばない）
- 新しい市場を追加する場合は `src/markets/base.py` の `Market` を継承
- `HAS_MODULE` パターン: スクリプト層（run_*.py）は `try/except ImportError` で各モジュールの存在を確認し、`HAS_*` フラグで graceful degradation。複数スクリプトで共通のモジュール可用性フラグ（`HAS_HISTORY_STORE`, `HAS_GRAPH_QUERY`, `HAS_GRAPH_STORE`）は `scripts/common.py` に一元管理 (KIK-448)。スクリプト固有のフラグは各スクリプト内に残す
- コンテキスト・提案の自動組み込み (KIK-465): 各スキルスクリプトは冒頭で `print_context()` 、末尾で `print_suggestions()` を呼び出す。両関数は `scripts/common.py` に定義。10秒タイムアウト（SIGALRM）、全例外を握り潰し graceful degradation
- yahoo_client はモジュール関数（クラスではない）。`from src.data import yahoo_client` → `yahoo_client.get_stock_info(symbol)`
- 配当利回りの正規化: `_normalize_ratio()` が値 > 1 の場合 100 で割って比率に変換
- フィールド名のエイリアス: indicators.py は yfinance 生キー（`trailingPE`, `priceToBook`）と正規化済みキー（`per`, `pbr`）の両方を対応
- `src/core/` はサブフォルダ構成（screening/, portfolio/, risk/, research/）。新モジュールは適切なサブフォルダに配置。import は直接パス（`src.core.screening.screener` 等）を使用
- データモデル定義: `stock_info` / `stock_detail` dict のスキーマ（全フィールド名・型・yfinance マッピング）は `docs/data-models.md` を参照 (KIK-524)

## テスト

- `python3 -m pytest tests/ -q` で全テスト実行（約3154テスト、~20秒）
- `tests/conftest.py` に共通フィクスチャ: `stock_info_data`, `stock_detail_data`, `price_history_df`, `mock_yahoo_client`
- `tests/conftest.py` に autouse `_block_external_io` フィクスチャ: Neo4j/TEI/Grok を全テストで自動モック（KIK-529）。`@pytest.mark.no_auto_mock` でオプトアウト可
- `tests/fixtures/` に JSON/CSV テストデータ（Toyota 7203.T ベース）
- `mock_yahoo_client` は monkeypatch で yahoo_client モジュール関数をモック
- テストファイルは `tests/core/`, `tests/data/`, `tests/output/` に機能別に配置

## Git ワークフロー

開発フロー（Worktree作成→設計→実装→テスト→レビュー→結合試験→マージ）は [workflow.md](workflow.md) を参照。

- ブランチ名: `feature/kik-{NNN}-{short-desc}`
- ワークツリー: `~/stock-skills-kik{NNN}`

## ファイル構成ガイドライン (KIK-572)

### サイズ上限
- プロダクションコード: 400行以下推奨、500行で分割検討
- テスト: 600行以下推奨
- スクリプト: 300行以下推奨

### 新モジュール配置
- ドメインロジック → src/core/{screening,portfolio,risk,research,health}/
- データ取得/保存 → src/data/{yahoo_client,graph_store,graph_query,history,context}/
- 出力整形 → src/output/
- 汎用ユーティリティ → src/core/common.py
- テスト → tests/{core,data,output}/ （src/ と1:1対応）

### 分割基準
- 1ファイルに3つ以上の独立した責務 → 分割
- 500行超 → 分割を検討
- 2つ以上のスキルから参照される共通ロジック → src/core/ に昇格

### 後方互換パターン（shim）
- 分割時は旧パスに sys.modules リダイレクトの shim を残す
- shim には DeprecationWarning を追加（KIK-572）
- 新コードは直接パスを使用

## ドキュメント自動生成 (KIK-525)

`scripts/generate_docs.py` で以下のドキュメントをソースコードから自動生成:

| ターゲット | 対象ファイル | 内容 |
|:---|:---|:---|
| `api-reference` | `docs/api-reference.md` | AST 解析で public 関数・クラスのシグネチャ+docstring を抽出 |
| `architecture` | `CLAUDE.md` | マーカー間のレイヤー概要を src/ スキャンで再生成 |
| `test-count` | `.claude/rules/development.md` | `pytest --co -q` でテスト数を更新 |
| `skill-catalog` | `docs/skill-catalog.md` | SKILL.md frontmatter から概要テーブルを再生成 |
| `data-models-verify` | `docs/data-models.md` | fixture との整合性検証（手動維持、不一致で警告） |

```bash
python3 scripts/generate_docs.py all           # 全ターゲット実行
python3 scripts/generate_docs.py check --quiet  # 陳腐化チェック（hook 用）
```

**自動化レイヤー:**

1. **PostToolUse hook**: `.py` ファイル編集時に `check --quiet` で陳腐化を検出・報告
2. **pre-commit hook**: `scripts/hooks/pre-commit` — src/ 変更時に `generate_docs.py all` を自動実行 + `data-models-verify` で不一致をブロック

**手動更新が必要なドキュメント:** `intent-routing.md`、各 `SKILL.md`、`rules/portfolio.md`、`rules/screening.md`

**KIK アノテーション:** `config/module_annotations.yaml` にモジュール→KIK issue のマッピングを管理。CLAUDE.md Architecture に自動付与

## ドキュメント構成 (KIK-412)

- `docs/architecture.md` — システムアーキテクチャ（3層構成、Mermaid図、設計原則、モジュール一覧）
- `docs/neo4j-schema.md` — Neo4j スキーマリファレンス（21ノードタイプ、リレーション、制約/インデックス、サンプルCypher）
- `docs/skill-catalog.md` — 8スキルのカタログ（概要、コマンド例、Core依存、出力形式）
- `docs/data-models.md` — stock_info / stock_detail dict スキーマ定義（全フィールド名・型・yfinanceマッピング・正規化ルール）(KIK-524)
- `docs/api-reference.md` — src/ の public API リファレンス（自動生成, KIK-525）
- `docs/patterns.md` — 頻出開発タスクのパターンガイド（新プリセット・PFサブコマンド・Neo4jノード・ヘルスチェック指標）(KIK-527)

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
