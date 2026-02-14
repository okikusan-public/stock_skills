---
name: stock-portfolio
description: "ポートフォリオ管理。保有銘柄の一覧表示・売買記録・構造分析。ストレステストの入力データ基盤。"
argument-hint: "[command] [args]  例: snapshot, buy 7203.T 100 2850, sell AAPL 5, analyze, list"
allowed-tools: Bash(python3 *)
---

# ポートフォリオ管理スキル

$ARGUMENTS を解析してコマンドを判定し、以下のコマンドを実行してください。

## 実行コマンド

```bash
python3 /Users/kikuchihiroyuki/stock-skills/.claude/skills/stock-portfolio/scripts/run_portfolio.py <command> [args]
```

## コマンド一覧

### snapshot -- PFスナップショット

現在価格・損益・通貨換算を含むポートフォリオのスナップショットを生成する。

```bash
python3 .../run_portfolio.py snapshot
```

### buy -- 購入記録追加

```bash
python3 .../run_portfolio.py buy --symbol <sym> --shares <n> --price <p> [--currency JPY] [--date YYYY-MM-DD] [--memo テキスト]
```

### sell -- 売却記録

```bash
python3 .../run_portfolio.py sell --symbol <sym> --shares <n>
```

### analyze -- 構造分析

地域/セクター/通貨のHHI（ハーフィンダール指数）を算出し、ポートフォリオの偏りを分析する。

```bash
python3 .../run_portfolio.py analyze
```

### health -- ヘルスチェック

保有銘柄の投資仮説がまだ有効かをチェックする。テクニカル（SMA50/200, RSI）とファンダメンタル（変化スコア）の2軸で3段階アラートを出力。

```bash
python3 .../run_portfolio.py health
```

アラートレベル:
- **早期警告**: SMA50割れ / RSI急低下 / 変化スコア1指標悪化
- **注意**: SMA50がSMA200に接近 + 指標悪化 / 変化スコア複数悪化
- **撤退**: デッドクロス / トレンド崩壊 + 変化スコア悪化

### rebalance -- リバランス提案

現在のポートフォリオ構造を分析し、集中リスクの低減と目標配分への調整案を提示する。

```bash
python3 .../run_portfolio.py rebalance [options]
```

CLIオプション:
- `--strategy defensive|balanced|aggressive` (デフォルト: balanced)
- `--reduce-sector SECTOR` (例: Technology)
- `--reduce-currency CURRENCY` (例: USD)
- `--max-single-ratio RATIO` (例: 0.15)
- `--max-sector-hhi HHI` (例: 0.25)
- `--max-region-hhi HHI` (例: 0.30)
- `--additional-cash AMOUNT` (円, 例: 1000000)
- `--min-dividend-yield YIELD` (例: 0.03)

### simulate -- 複利シミュレーション

現在のポートフォリオを基に、複利計算で将来の資産推移をシミュレーションする。forecast の期待リターン + 配当再投資 + 毎月積立を複利で計算し、楽観/ベース/悲観の3シナリオで表示。

```bash
python3 .../run_portfolio.py simulate [options]
```

CLIオプション:
- `--years N` (シミュレーション年数, デフォルト: 10)
- `--monthly-add AMOUNT` (月額積立額, 円, デフォルト: 0)
- `--target AMOUNT` (目標額, 円, 例: 15000000)
- `--reinvest-dividends` (配当再投資する, デフォルト: ON)
- `--no-reinvest-dividends` (配当再投資しない)

### list -- 保有銘柄一覧

portfolio.csv の内容をそのまま表示する。

```bash
python3 .../run_portfolio.py list
```

## 引数の解釈ルール（自然言語対応）

ユーザーの自然言語入力を以下のようにコマンドに変換する。

| ユーザー入力 | コマンド |
|:-----------|:--------|
| 「PFを見せて」「ポートフォリオ」「スナップショット」「損益」 | snapshot |
| 「〇〇を△株買った」「〇〇を△株 ¥XXXXで購入」 | buy |
| 「〇〇を△株売った」「〇〇を売却」 | sell |
| 「構造分析」「偏りを調べて」「集中度」「HHI」 | analyze |
| 「ヘルスチェック」「健全性チェック」「利確判断」「損切り判断」 | health |
| 「リバランス」「偏りを直したい」「配分調整」「リスクを抑えたい」 | rebalance |
| 「5年後にいくらになる？」「シミュレーション」「複利」 | simulate |
| 「一覧」「リスト」「CSV」 | list |

### buy コマンドの自然言語変換例

| ユーザー入力 | 変換結果 |
|:-----------|:--------|
| 「トヨタを100株 2850円で買った」 | `buy --symbol 7203.T --shares 100 --price 2850 --currency JPY` |
| 「AAPLを10株 $178.50で購入」 | `buy --symbol AAPL --shares 10 --price 178.50 --currency USD` |
| 「DBSを100株 35.20SGDで買った」 | `buy --symbol D05.SI --shares 100 --price 35.20 --currency SGD` |

企業名が指定された場合はティッカーシンボルに変換してから --symbol に指定すること。

### sell コマンドの自然言語変換例

| ユーザー入力 | 変換結果 |
|:-----------|:--------|
| 「トヨタを100株売った」 | `sell --symbol 7203.T --shares 100` |
| 「AAPLを5株売却」 | `sell --symbol AAPL --shares 5` |

### rebalance コマンドの自然言語変換例

| ユーザー入力 | 変換結果 |
|:-----------|:--------|
| 「リスクを抑えたい」 | `rebalance --strategy defensive` |
| 「もっと攻めたい」 | `rebalance --strategy aggressive` |
| 「配当で安定させたい」 | `rebalance --min-dividend-yield 0.03` |
| 「テック偏重を直したい」 | `rebalance --reduce-sector Technology` |
| 「円安ヘッジしたい」 | `rebalance --reduce-currency USD` |
| 「100万円追加投入したい」 | `rebalance --additional-cash 1000000` |

### simulate コマンドの自然言語変換例

| ユーザー入力 | 変換結果 |
|:-----------|:--------|
| 「5年後にいくらになる？」 | `simulate --years 5` |
| 「月10万追加して3年後に2000万いける？」 | `simulate --years 3 --monthly-add 100000 --target 20000000` |
| 「複利でシミュレーション」 | `simulate --years 10` |
| 「配当再投資しなかったら？」 | `simulate --years 5 --no-reinvest-dividends` |
| 「老後資金のシミュレーション」 | `simulate --years 20 --monthly-add 100000` |

## 制約事項

- 日本株: 100株単位（単元株）
- ASEAN株: 100株単位（最低手数料 3,300円）
- 楽天証券対応（手数料体系）
- portfolio.csv のパス: `.claude/skills/stock-portfolio/data/portfolio.csv`

## 出力

結果はMarkdown形式で表示してください。

### snapshot の出力項目
- 銘柄 / 名称 / 保有数 / 取得単価 / 現在価格 / 評価額 / 損益 / 損益率 / 通貨

### analyze の出力項目
- セクターHHI / 地域HHI / 通貨HHI
- 各軸の構成比率
- リスクレベル判定

### health の出力項目
- 銘柄 / 損益率 / トレンド（上昇/横ばい/下降） / 変化の質（良好/1指標↓/複数悪化） / アラート
- アラートがある銘柄の詳細（理由、SMA/RSI値、変化スコア、推奨アクション）

### rebalance の出力項目
- 現状のHHI（セクター/地域/通貨）と目標HHI
- 売却候補（銘柄・株数・理由）
- 購入候補（銘柄・株数・理由・配当利回り）
- リバランス後のHHI予測値

### simulate の出力項目
- 年次推移テーブル（年/評価額/累計投入/運用益/配当累計）
- 3シナリオ比較（楽観/ベース/悲観の最終年）
- 目標達成分析（到達年/必要積立額）
- 配当再投資の複利効果

## 実行例

```bash
# スナップショット
python3 .../run_portfolio.py snapshot

# 購入記録
python3 .../run_portfolio.py buy --symbol 7203.T --shares 100 --price 2850 --currency JPY --date 2025-06-15 --memo トヨタ

# 売却記録
python3 .../run_portfolio.py sell --symbol AAPL --shares 5

# 構造分析
python3 .../run_portfolio.py analyze

# 一覧表示
python3 .../run_portfolio.py list

# ヘルスチェック
python3 .../run_portfolio.py health

# リバランス提案
python3 .../run_portfolio.py rebalance
python3 .../run_portfolio.py rebalance --strategy defensive
python3 .../run_portfolio.py rebalance --reduce-sector Technology --additional-cash 1000000
```
