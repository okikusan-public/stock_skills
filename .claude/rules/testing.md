---
paths:
  - "tests/**/*.py"
  - "tests/conftest.py"
  - "tests/fixtures/**"
---

# テスト開発ルール

## テスト実行

```bash
python3 -m pytest tests/ -q                       # 全件実行（約740テスト, ~1秒）
python3 -m pytest tests/core/test_indicators.py -v # 特定モジュール
python3 -m pytest tests/ -k "test_value_score"     # キーワード指定
```

## テスト構造

- `tests/core/` — コアロジックのユニットテスト
- `tests/data/` — データ取得層のテスト
- `tests/output/` — フォーマッター層のテスト
- `tests/conftest.py` — 共通フィクスチャ
- `tests/fixtures/` — JSON/CSV テストデータ（Toyota 7203.T ベース）

## モック方法

- `mock_yahoo_client` フィクスチャ: monkeypatch で yahoo_client モジュール関数をモック
- `return_value` を設定して使用
- yahoo_client はクラスではなくモジュール関数なので monkeypatch が容易

## テスト作成の注意点

- 各テストは独立して実行可能であること（外部 API 依存なし）
- yahoo_client の呼び出しは必ずモックする
- テストデータは `tests/fixtures/` の既存データを再利用
- 新しいモジュールには対応するテストファイルを作成
