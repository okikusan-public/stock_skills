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
python3 /Users/kikuchihiroyuki/stock-skills/.claude/skills/screen-stocks/scripts/run_screen.py --region <region> --preset <preset> [--sector <sector>] [--theme <theme>] [--top <N>] [--mode <query|legacy>]
```

## 自然言語ルーティング

自然言語→スキル判定は [.claude/rules/intent-routing.md](../../rules/intent-routing.md) を参照。

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

## テーマスクリーニング（KIK-439）

`--theme <テーマ>` を任意のプリセットと組み合わせて、特定テーマに絞ったスクリーニングができる。
`trending`/`pullback`/`alpha` プリセットは `--theme` 未対応。

| テーマキー | 説明 | 対象インダストリー（抜粋） |
|:---------|:-----|:-----------------------|
| `ai` | AI・半導体 | Semiconductors, Software—Infrastructure, Electronic Components |
| `ev` | EV・次世代自動車 | Auto Manufacturers, Electrical Equipment & Parts |
| `cloud-saas` | クラウド・SaaS | Software—Application, Software—Infrastructure |
| `cybersecurity` | サイバーセキュリティ | Software—Infrastructure（セキュリティ特化） |
| `biotech` | バイオテック・創薬 | Biotechnology, Drug Manufacturers |
| `renewable-energy` | 再生可能エネルギー | Solar, Utilities—Renewable |
| `fintech` | フィンテック | Software—Application（金融特化）, Capital Markets |
| `defense` | 防衛・宇宙 | Aerospace & Defense |
| `healthcare` | ヘルスケア・医療機器 | Medical Devices, Health Information Services |

テーマ定義は `config/themes.yaml` で管理。

## トレンドテーマ自動検出（KIK-440）

`--auto-theme` を指定すると、Grok API（X/Web検索）でトレンドテーマを自動検出し、各テーマで既存のスクリーニングを順次実行する。

### パイプライン

1. Grok API がX/Webから注目テーマを3〜5つ検出（信頼度付き）
2. `themes.yaml` のキーと照合し、有効テーマのみ実行（未対応テーマはスキップ通知）
3. 各テーマで指定プリセットのスクリーニングを実行

### 制約事項

- `--auto-theme` と `--theme` は排他（同時使用不可）
- `trending`/`pullback`/`alpha` プリセットとは併用不可
- `XAI_API_KEY` 必須（未設定時はエラー終了）

### `trending` プリセットとの違い

| | `--preset trending` | `--auto-theme` |
|:---|:---|:---|
| 検出対象 | X上の話題の**個別銘柄** | トレンドの**テーマ・セクター** |
| 粒度 | 銘柄粒度 | テーマ粒度 |
| スクリーニング | ファンダメンタルズ評価 | テーマ内で任意のプリセットで評価 |

### 実行例

```bash
# 日本のトレンドテーマで割安株をスクリーニング
python3 .../run_screen.py --region japan --preset value --auto-theme

# 米国のトレンドテーマで高成長株
python3 .../run_screen.py --region us --preset high-growth --auto-theme

# グローバルのトレンドテーマでデフォルトプリセット
python3 .../run_screen.py --preset value --auto-theme
```

## スクリーニングモード

- `--mode query` (デフォルト): **EquityQuery方式**。yfinance の EquityQuery API を使い、銘柄リスト不要で条件に合う銘柄を直接検索する。全地域に対応。高速。
- `--mode legacy`: **銘柄リスト方式**。従来のValueScreenerを使用。事前定義した銘柄リスト（日経225、S&P500等）を1銘柄ずつ取得・評価。japan/us/asean のみ対応。
- `--with-pullback`: **押し目フィルタ追加**。任意のプリセット（value, high-dividend 等）にテクニカル押し目判定を追加適用する。`--preset pullback` との同時指定は不要（pullback プリセットが優先される）。出力は Pullback モードと同じ列形式。

## プリセット

- `value` : 伝統的バリュー投資（低PER・低PBR・ROE≧5%）
- `high-dividend` : 高配当株（配当利回り3%以上）
- `growth` : 純成長株（高ROE≧15%・売上成長≧10%。PER制約なし。割安度を問わず成長力で選別）
- `growth-value` : 成長バリュー（成長性＋割安度）
- `deep-value` : ディープバリュー（非常に低いPER/PBR）
- `quality` : クオリティバリュー（高ROE≧15%＋割安。value の ROE 閾値を5%→15%に厳格化した上位集合。収益力の高い割安株に限定）
- `pullback` : 押し目買い型（上昇トレンド中の一時調整でエントリー。EquityQuery→テクニカル→SR の3段パイプライン。実行に時間がかかります）
- `alpha` : アルファシグナル（割安＋変化の質＋押し目の3軸統合。EquityQuery→変化の質→押し目判定→2軸スコアリングの4段パイプライン。実行に時間がかかります）
- `trending` : Xトレンド銘柄（Grok API でX上の話題銘柄を発見→Yahoo Financeでファンダメンタルズ評価。`--theme` でテーマ絞り込み可。XAI_API_KEY 必須）
- `long-term` : 長期投資適性（高ROE≧15%・EPS成長≧10%・配当≧2%・PER≦25・PBR≦3・時価総額1000億以上。長期保有に適した安定成長銘柄を検索）
- `shareholder-return` : 株主還元重視（配当利回り+自社株買い利回りの総還元率でランキング。安定度評価付き: ✅安定/📈増加/⚠️一時的/📉低下）
- `high-growth` : 高成長株（利益不問・売上成長率≧20%・直近四半期売上成長≧10%・PSR≦20・粗利率≧20%。赤字成長企業も対象。PERは使わずPSRでバブル防止）（KIK-432）
- `small-cap-growth` : 小型急成長株（時価総額1000億以下・売上成長率≧20%・PSR≦15・粗利率≧20%。機関投資家未発見の10倍株候補。地域別時価総額自動調整付き。リスク★★★★）（KIK-437）

## 出力

結果はMarkdown表形式で表示してください。EquityQuery モードではセクター列が追加される。

### EquityQuery モードの出力列
順位 / 銘柄 / セクター / 株価 / PER / PBR / 配当利回り / ROE / スコア

### Legacy モードの出力列
順位 / 銘柄 / 株価 / PER / PBR / 配当利回り / ROE / スコア

### Pullback モードの出力列
順位 / 銘柄 / 株価 / PER / 押し目% / RSI / 出来高比 / SMA50 / SMA200 / スコア

### Alpha モードの出力列
順位 / 銘柄 / 株価 / PER / PBR / 割安 / 変化 / 総合 / 押し目 / ア / 加速 / FCF / ROE趨勢

### Growth モードの出力列
順位 / 銘柄 / セクター / 株価 / PER / PBR / EPS成長 / 売上成長 / ROE

### Trending モードの出力列
順位 / 銘柄 / 話題の理由 / 株価 / PER / PBR / 配当利回り / ROE / スコア / 判定

### Shareholder Return モードの出力列
順位 / 銘柄 / 株価 / 配当利回り / 自社株買い利回り / 総還元率 / 安定度 / ROE / PER

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

# 日本株のアルファシグナル（割安＋変化＋押し目）
python3 .../run_screen.py --region japan --preset alpha

# 米国株のアルファシグナル
python3 .../run_screen.py --region us --preset alpha

# 日本の割安株 + 押し目フィルタ
python3 .../run_screen.py --region japan --preset value --with-pullback

# 米国の高配当株 + 押し目フィルタ
python3 .../run_screen.py --region us --preset high-dividend --with-pullback

# X (Twitter) で話題の日本株
python3 .../run_screen.py --region japan --preset trending

# X で話題のAI関連米国株
python3 .../run_screen.py --region us --preset trending --theme "AI"

# X で話題の半導体関連銘柄
python3 .../run_screen.py --region japan --preset trending --theme "半導体"

# 日本の長期投資候補
python3 .../run_screen.py --region japan --preset long-term

# 米国の長期投資候補
python3 .../run_screen.py --region us --preset long-term

# 日本の純成長株（割安制約なし）
python3 .../run_screen.py --region japan --preset growth

# 米国の純成長株
python3 .../run_screen.py --region us --preset growth

# 日本の高還元株
python3 .../run_screen.py --region japan --preset shareholder-return

# 米国の高還元株
python3 .../run_screen.py --region us --preset shareholder-return

# 米国の高成長株（利益不問・PSR基準）
python3 .../run_screen.py --region us --preset high-growth

# 日本の高成長株
python3 .../run_screen.py --region japan --preset high-growth

# AI関連の割安株（米国）
python3 .../run_screen.py --region us --preset value --theme ai

# 半導体の高成長株（米国）
python3 .../run_screen.py --region us --preset high-growth --theme ai

# 防衛関連株（米国・割安）
python3 .../run_screen.py --region us --preset value --theme defense

# EV関連の成長株（米国）
python3 .../run_screen.py --region us --preset growth --theme ev

# バイオテックの高成長株
python3 .../run_screen.py --region us --preset high-growth --theme biotech

# 日本の小型急成長株（時価総額1000億以下）
python3 .../run_screen.py --region japan --preset small-cap-growth

# 米国の小型急成長株（時価総額$1B以下に自動調整）
python3 .../run_screen.py --region us --preset small-cap-growth

# AI関連の小型成長株
python3 .../run_screen.py --region us --preset small-cap-growth --theme ai
```

## アノテーション機能 (KIK-418/419)

スクリーニング結果には投資メモと売却履歴に基づくマーカーが自動付与されます。

### マーカー凡例

| マーカー | 意味 | トリガー |
|:---:|:---|:---|
| ⚠️ | 懸念メモあり | 投資メモ type=concern |
| 📝 | 学びメモあり | 投資メモ type=lesson |
| 👀 | 様子見 | 投資メモ type=observation + 「見送り」「待ち」等キーワード |

### 売却済み銘柄の自動除外

直近90日以内に売却した銘柄はスクリーニング結果から自動除外されます。除外数はメッセージで表示されます。

### データソース

1. Neo4j ナレッジグラフ（優先）
2. JSON ファイル（Neo4j 未接続時のフォールバック）

## 前提知識統合ルール (KIK-466)

get_context.py の出力に以下がある場合、スクリーニング結果と統合して回答する:

- **常連銘柄（SURFACED 3回以上）**: 「3回連続上位 → 安定して割安評価。詳細レポート推奨」
- **保有銘柄**: スクリーニング結果に保有銘柄が含まれる場合、「保有中: 追加投資の検討材料」
- **懸念メモ**: 結果銘柄に懸念メモがあれば「⚠️ 懸念メモあり」と付記
- **売却済み**: 売却済み銘柄が再度上位に出た場合、「以前売却 → 再エントリーの検討」
