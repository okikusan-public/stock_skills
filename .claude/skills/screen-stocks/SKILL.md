---
name: screen-stocks
description: 割安株スクリーニング。EquityQuery で銘柄リスト不要のスクリーニング。PER/PBR/配当利回り/ROE等で日本株・米国株・ASEAN株・香港株・韓国株・台湾株等60地域から割安銘柄を検索する。
argument-hint: "[region] [preset] [--sector SECTOR]  例: japan value, us high-dividend, asean quality, hk value --sector Technology"
allowed-tools: Bash(python3 *)
---

# 割安株スクリーニングスキル

$ARGUMENTS を解析して region、preset、sector を判定し、以下のコマンドを実行してください。

## 実行コマンド

```bash
python3 /Users/kikuchihiroyuki/stock-skills/.claude/skills/screen-stocks/scripts/run_screen.py --region <region> --preset <preset> [--sector <sector>] [--top <N>] [--mode <query|legacy>]
```

## 引数の解釈ルール

### region（第1引数）
ユーザーの自然言語入力を以下のように解釈する。デフォルト: japan

| ユーザー入力 | --region 値 |
|:-----------|:-----------|
| 「日本株」「日本」「japan」「JP」 | japan |
| 「米国株」「アメリカ」「US」 | us |
| 「ASEAN」「アセアン」「東南アジア」 | asean |
| 「シンガポール」「singapore」 | sg |
| 「タイ」「thailand」 | th |
| 「マレーシア」「malaysia」 | my |
| 「インドネシア」「indonesia」 | id |
| 「フィリピン」「philippines」 | ph |
| 「香港」「hongkong」「HK」 | hk |
| 「韓国」「korea」「KR」 | kr |
| 「台湾」「taiwan」「TW」 | tw |
| 「中国」「china」「CN」 | cn |
| 「全部」「all」 | all |

### preset（第2引数）
デフォルト: value

| ユーザー入力 | --preset 値 |
|:-----------|:-----------|
| 「割安」「バリュー」 | value |
| 「高配当」 | high-dividend |
| 「成長」「グロース」 | growth-value |
| 「超割安」「ディープバリュー」 | deep-value |
| 「クオリティ」「高品質」 | quality |
| 「押し目」「pullback」 | pullback |
| 「割安で押し目」「バリュー+押し目」 | value --with-pullback |
| 「高配当で押し目」 | high-dividend --with-pullback |

### sector（--sector オプション）
指定なしの場合は全セクターが対象。ユーザーが特定セクターに言及した場合に使用する。

| ユーザー入力 | --sector 値 |
|:-----------|:-----------|
| 「テクノロジー」「IT」「ハイテク」 | Technology |
| 「金融」「銀行」 | Financial Services |
| 「ヘルスケア」「医療」「製薬」 | Healthcare |
| 「消費循環」「小売」「自動車」 | Consumer Cyclical |
| 「産業」「工業」「製造」 | Industrials |
| 「通信」「メディア」 | Communication Services |
| 「生活必需品」「食品」「日用品」 | Consumer Defensive |
| 「エネルギー」「石油」 | Energy |
| 「素材」「化学」「鉄鋼」 | Basic Materials |
| 「不動産」「REIT」 | Real Estate |
| 「公益」「電力」「ガス」 | Utilities |

## 利用可能な地域コード（yfinance EquityQuery）

主要地域: jp, us, sg, th, my, id, ph, hk, kr, tw, cn, gb, de, fr, in, au, br, ca 等（約60地域）

## 利用可能な取引所コード

| 取引所 | コード |
|:------|:------|
| 東京証券取引所 | JPX |
| NASDAQ | NMS |
| NYSE | NYQ |
| シンガポール証券取引所 | SES |
| タイ証券取引所 | SET |
| マレーシア証券取引所 | KLS |
| インドネシア証券取引所 | JKT |
| フィリピン証券取引所 | PHS |
| 香港証券取引所 | HKG |
| 韓国証券取引所 | KSC/KOE |
| 台湾証券取引所 | TAI |

## スクリーニングモード

- `--mode query` (デフォルト): **EquityQuery方式**。yfinance の EquityQuery API を使い、銘柄リスト不要で条件に合う銘柄を直接検索する。全地域に対応。高速。
- `--mode legacy`: **銘柄リスト方式**。従来のValueScreenerを使用。事前定義した銘柄リスト（日経225、S&P500等）を1銘柄ずつ取得・評価。japan/us/asean のみ対応。
- `--with-pullback`: **押し目フィルタ追加**。任意のプリセット（value, high-dividend 等）にテクニカル押し目判定を追加適用する。`--preset pullback` との同時指定は不要（pullback プリセットが優先される）。出力は Pullback モードと同じ列形式。

## プリセット

- `value` : 伝統的バリュー投資（低PER・低PBR）
- `high-dividend` : 高配当株（配当利回り3%以上）
- `growth-value` : 成長バリュー（成長性＋割安度）
- `deep-value` : ディープバリュー（非常に低いPER/PBR）
- `quality` : クオリティバリュー（高ROE＋割安）
- `pullback` : 押し目買い型（上昇トレンド中の一時調整でエントリー。EquityQuery→テクニカル→SR の3段パイプライン。実行に時間がかかります）

## 出力

結果はMarkdown表形式で表示してください。EquityQuery モードではセクター列が追加される。

### EquityQuery モードの出力列
順位 / 銘柄 / セクター / 株価 / PER / PBR / 配当利回り / ROE / スコア

### Legacy モードの出力列
順位 / 銘柄 / 株価 / PER / PBR / 配当利回り / ROE / スコア

### Pullback モードの出力列
順位 / 銘柄 / 株価 / PER / 押し目% / RSI / 出来高比 / SMA50 / SMA200 / スコア

## 実行例

```bash
# 日本の割安株（デフォルト）
python3 .../run_screen.py --region japan --preset value

# 米国の高配当テクノロジー株
python3 .../run_screen.py --region us --preset high-dividend --sector Technology

# 香港のバリュー株
python3 .../run_screen.py --region hk --preset value

# ASEAN の成長バリュー株（sg, th, my, id, ph を順次実行）
python3 .../run_screen.py --region asean --preset growth-value

# Legacy モードで米国株をスクリーニング
python3 .../run_screen.py --region us --preset value --mode legacy

# 日本株の押し目買い候補
python3 .../run_screen.py --region japan --preset pullback

# 日本の割安株 + 押し目フィルタ
python3 .../run_screen.py --region japan --preset value --with-pullback

# 米国の高配当株 + 押し目フィルタ
python3 .../run_screen.py --region us --preset high-dividend --with-pullback
```
