"""Scenario-based causal chain analysis for portfolio stress testing (KIK-341)."""

import math
from typing import Optional


# プリセットシナリオ定義
SCENARIOS = {
    "triple_decline": {
        "name": "トリプル安（株安・債券安・円安）",
        "trigger": "財政不安・格下げ",
        "base_shock": -0.20,
        "effects": {
            "primary": [
                {"target": "日本株全般", "impact": -0.12, "reason": "海外勢売り"},
                {"target": "円建て", "impact": -0.10, "reason": "円安15円"},
            ],
            "secondary": [
                {"target": "グロース株", "impact": -0.12, "reason": "金利上昇"},
                {"target": "輸出企業", "impact": +0.06, "reason": "円安メリット"},
                {"target": "内需企業", "impact": -0.07, "reason": "コスト増"},
                {"target": "銀行", "impact": +0.06, "reason": "利ザヤ改善"},
            ],
            "currency": {"usd_jpy_change": +15, "impact_on_foreign": +0.097},
            "offset": ["輸出企業の円安メリット", "銀行の金利上昇メリット"],
            "time_axis": "即座→数週間で二次効果→介入で急反転リスク",
        },
    },
    "yen_depreciation": {
        "name": "ドル高円安",
        "trigger": "日米金利差拡大",
        "base_shock": -0.10,
        "effects": {
            "primary": [
                {"target": "米国株(円建て)", "impact": +0.097, "reason": "為替益"},
                {"target": "日本輸出株", "impact": +0.06, "reason": "円安メリット"},
                {"target": "日本内需株", "impact": -0.07, "reason": "コスト増"},
            ],
            "secondary": [
                {"target": "全外貨資産", "impact": -0.05, "reason": "介入→急反転リスク(165→158)"},
            ],
            "currency": {"usd_jpy_change": +10, "impact_on_foreign": +0.065},
            "offset": ["輸出企業メリット"],
            "time_axis": "段階的: 155→165(プラス) → 165→175(警戒) → 介入(急反転)",
        },
    },
    "us_recession": {
        "name": "米国リセッション",
        "trigger": "景気後退入り確認",
        "base_shock": -0.25,
        "effects": {
            "primary": [
                {"target": "米国株全般", "impact": -0.25, "reason": "企業業績悪化"},
                {"target": "シクリカル株", "impact": -0.35, "reason": "景気敏感"},
            ],
            "secondary": [
                {"target": "日本輸出株", "impact": -0.15, "reason": "需要減"},
                {"target": "ASEAN株", "impact": -0.10, "reason": "資金引き揚げ"},
                {"target": "ディフェンシブ株", "impact": -0.05, "reason": "相対的に耐性"},
            ],
            "currency": {"usd_jpy_change": -10, "impact_on_foreign": -0.065},
            "offset": ["ディフェンシブ銘柄", "円高で外貨建て資産のヘッジ効果"],
            "time_axis": "確認→半年〜1年で底打ち→金融緩和で反転",
        },
    },
    "boj_rate_hike": {
        "name": "日銀利上げ加速",
        "trigger": "インフレ持続で追加利上げ",
        "base_shock": -0.15,
        "effects": {
            "primary": [
                {"target": "グロース株", "impact": -0.15, "reason": "割引率上昇"},
                {"target": "不動産", "impact": -0.12, "reason": "金利コスト増"},
                {"target": "銀行", "impact": +0.08, "reason": "利ザヤ拡大"},
            ],
            "secondary": [
                {"target": "高配当株", "impact": -0.05, "reason": "債券との比較劣後"},
                {"target": "円建て外貨資産", "impact": -0.05, "reason": "円高"},
            ],
            "currency": {"usd_jpy_change": -8, "impact_on_foreign": -0.052},
            "offset": ["銀行セクター上昇", "円高で輸入コスト低下"],
            "time_axis": "利上げ発表→即座に反応→半年で織り込み",
        },
    },
    "us_china_conflict": {
        "name": "米中対立激化",
        "trigger": "関税・制裁強化",
        "base_shock": -0.15,
        "effects": {
            "primary": [
                {"target": "中国関連株", "impact": -0.20, "reason": "サプライチェーン混乱"},
                {"target": "半導体", "impact": -0.15, "reason": "輸出規制"},
            ],
            "secondary": [
                {"target": "ASEAN株", "impact": +0.05, "reason": "サプライチェーン移転先"},
                {"target": "防衛関連", "impact": +0.08, "reason": "地政学リスク"},
            ],
            "currency": {"usd_jpy_change": -3, "impact_on_foreign": -0.02},
            "offset": ["ASEANへの生産移転メリット", "防衛関連上昇"],
            "time_axis": "発表→数日で急落→数ヶ月で代替先に資金移動",
        },
    },
    "inflation_resurgence": {
        "name": "インフレ再燃",
        "trigger": "CPI再加速",
        "base_shock": -0.15,
        "effects": {
            "primary": [
                {"target": "グロース株", "impact": -0.18, "reason": "利上げ再開懸念"},
                {"target": "長期債", "impact": -0.10, "reason": "金利上昇"},
            ],
            "secondary": [
                {"target": "エネルギー株", "impact": +0.10, "reason": "原油高"},
                {"target": "素材株", "impact": +0.05, "reason": "資源価格上昇"},
                {"target": "消費関連", "impact": -0.08, "reason": "購買力低下"},
            ],
            "currency": {"usd_jpy_change": +5, "impact_on_foreign": +0.032},
            "offset": ["コモディティ関連の上昇", "インフレヘッジ資産"],
            "time_axis": "CPI発表→即座に反応→3-6ヶ月で方向性確定",
        },
    },
    "tech_crash": {
        "name": "テック暴落",
        "trigger": "AI収益化の失望・バリュエーション調整・規制強化",
        "base_shock": -0.30,
        "effects": {
            "primary": [
                {"target": "テック株", "impact": -0.35, "reason": "NASDAQ -30%、バリュエーション修正"},
                {"target": "半導体", "impact": -0.40, "reason": "AI関連の過剰期待修正"},
            ],
            "secondary": [
                {"target": "非テック株", "impact": -0.08, "reason": "リスクオフ波及"},
                {"target": "ディフェンシブ株", "impact": -0.03, "reason": "質への逃避で相対的に耐性"},
                {"target": "金・安全資産", "impact": +0.06, "reason": "安全資産需要"},
            ],
            "currency": {"usd_jpy_change": -8, "impact_on_foreign": -0.052},
            "offset": ["ディフェンシブ銘柄の耐性", "金・債券への資金逃避", "円高による外貨資産圧縮"],
            "time_axis": "暴落→数日で急落→数週間で二次波及→数ヶ月で底値模索",
        },
    },
    "yen_appreciation": {
        "name": "円高ドル安",
        "trigger": "FRB利下げ加速＋日銀追加利上げ",
        "base_shock": -0.10,
        "effects": {
            "primary": [
                {"target": "全外貨資産", "impact": -0.13, "reason": "USD/JPY -20円 (153→133円)"},
                {"target": "日本輸出株", "impact": -0.12, "reason": "円高デメリット"},
            ],
            "secondary": [
                {"target": "日本内需株", "impact": +0.04, "reason": "輸入コスト減"},
                {"target": "金・安全資産", "impact": +0.05, "reason": "ドル安で金価格上昇"},
            ],
            "currency": {"usd_jpy_change": -20, "impact_on_foreign": -0.131},
            "offset": ["内需企業の輸入コスト低下", "日本国内消費改善"],
            "time_axis": "FRB利下げ決定→数日で急速な円高→数ヶ月で新均衡",
        },
    },
}

# シナリオ名のエイリアス（自然言語対応）
SCENARIO_ALIASES = {
    # triple_decline
    "トリプル安": "triple_decline",
    "triple": "triple_decline",
    "株安・円安・債券安": "triple_decline",
    # yen_depreciation
    "ドル高": "yen_depreciation",
    "ドル高円安": "yen_depreciation",
    "円安": "yen_depreciation",
    "yen": "yen_depreciation",
    "為替ショック": "yen_depreciation",
    # us_recession
    "リセッション": "us_recession",
    "recession": "us_recession",
    "景気後退": "us_recession",
    "米国リセッション": "us_recession",
    # boj_rate_hike
    "利上げ": "boj_rate_hike",
    "日銀": "boj_rate_hike",
    "日銀利上げ": "boj_rate_hike",
    "金利上昇": "boj_rate_hike",
    "boj": "boj_rate_hike",
    # us_china_conflict
    "米中": "us_china_conflict",
    "米中対立": "us_china_conflict",
    "china": "us_china_conflict",
    "地政学リスク": "us_china_conflict",
    "貿易戦争": "us_china_conflict",
    # inflation_resurgence
    "インフレ": "inflation_resurgence",
    "インフレ再燃": "inflation_resurgence",
    "inflation": "inflation_resurgence",
    "物価上昇": "inflation_resurgence",
    # tech_crash
    "テック暴落": "tech_crash",
    "tech暴落": "tech_crash",
    "ai暴落": "tech_crash",
    "ナスダック暴落": "tech_crash",
    "tech": "tech_crash",
    "テクノロジー暴落": "tech_crash",
    # yen_appreciation
    "円高ドル安": "yen_appreciation",
    "円高": "yen_appreciation",
    "ドル安": "yen_appreciation",
}


# ---------------------------------------------------------------------------
# セクター・通貨マッピング
# ---------------------------------------------------------------------------

# シナリオのtargetからセクター名への対応表
_TARGET_TO_SECTORS = {
    "日本株全般": None,  # 全セクター
    "米国株全般": None,
    "グロース株": ["Technology", "Communication Services"],
    "輸出企業": ["Industrials", "Consumer Cyclical", "Technology"],
    "日本輸出株": ["Industrials", "Consumer Cyclical", "Technology"],
    "内需企業": ["Consumer Defensive", "Utilities", "Real Estate"],
    "日本内需株": ["Consumer Defensive", "Utilities", "Real Estate"],
    "銀行": ["Financial Services"],
    "不動産": ["Real Estate"],
    "高配当株": None,  # セクター横断
    "シクリカル株": ["Consumer Cyclical", "Industrials", "Basic Materials"],
    "ディフェンシブ株": ["Consumer Defensive", "Healthcare", "Utilities"],
    "ASEAN株": None,  # 地域
    "中国関連株": None,  # 地域
    "半導体": ["Technology"],
    "防衛関連": ["Industrials"],
    "エネルギー株": ["Energy"],
    "素材株": ["Basic Materials"],
    "消費関連": ["Consumer Cyclical", "Consumer Defensive"],
    "長期債": None,  # 非株式
    "円建て": None,
    "円建て外貨資産": None,
    "米国株(円建て)": None,
    "全外貨資産": None,
    "テック株": ["Technology", "Communication Services"],
    "非テック株": None,  # テック以外の全セクター（callerで判定）
    "金・安全資産": None,  # 非株式
}

# ティッカーサフィックス → 通貨
_SUFFIX_TO_CURRENCY = {
    ".T": "JPY",
    ".SI": "SGD",
    ".BK": "THB",
    ".KL": "MYR",
    ".JK": "IDR",
    ".PS": "PHP",
}

# ティッカーサフィックス → 地域ラベル
_SUFFIX_TO_REGION = {
    ".T": "Japan",
    ".SI": "Singapore",
    ".BK": "Thailand",
    ".KL": "Malaysia",
    ".JK": "Indonesia",
    ".PS": "Philippines",
}

# ETF → 資産クラスマッピング（ティッカーベース）
_ETF_ASSET_CLASS = {
    # 金・安全資産
    "GLDM": "金・安全資産",
    "GLD": "金・安全資産",
    "IAU": "金・安全資産",
    "SGOL": "金・安全資産",
    # 長期債
    "TLT": "長期債",
    "IEF": "長期債",
    "BND": "長期債",
    "AGG": "長期債",
    "VGLT": "長期債",
    # 株式インカム
    "JEPI": "株式インカム",
    "JEPQ": "株式インカム",
    "SCHD": "株式インカム",
    "VYM": "株式インカム",
    "HDV": "株式インカム",
    "SPYD": "株式インカム",
}


def _get_etf_asset_class(symbol: str, stock_info: dict) -> Optional[str]:
    """Return the ETF asset class if the symbol is a known ETF, else None."""
    # Strip suffix for lookup (e.g., "1326.T" -> not in mapping, just use symbol)
    base_symbol = symbol.split(".")[0] if "." in symbol else symbol
    asset_class = _ETF_ASSET_CLASS.get(base_symbol)
    if asset_class:
        return asset_class
    # quoteType fallback
    if stock_info.get("quoteType") == "ETF":
        return "株式インカム"  # Default ETF class (conservative equity)
    return None


def _infer_currency(symbol: str, stock_info: dict) -> str:
    """銘柄の通貨を推定する。stock_info['currency'] があればそちら優先。"""
    currency = stock_info.get("currency")
    if currency:
        return currency
    for suffix, cur in _SUFFIX_TO_CURRENCY.items():
        if symbol.endswith(suffix):
            return cur
    # サフィックスなし → USD と推定
    return "USD"


def _infer_region(symbol: str, stock_info: dict) -> str:
    """銘柄の地域を推定する。"""
    country = stock_info.get("country") or stock_info.get("region")
    if country:
        return country
    for suffix, region in _SUFFIX_TO_REGION.items():
        if symbol.endswith(suffix):
            return region
    return "US"


def _safe_float(value, default: float = 0.0) -> float:
    """None/NaN を安全にfloatに変換する。"""
    if value is None:
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 公開API
# ---------------------------------------------------------------------------

def resolve_scenario(name: str) -> Optional[dict]:
    """シナリオ名（自然言語含む）からシナリオ定義を解決。

    検索順: 完全一致(SCENARIOS key) → 完全一致(エイリアス) → 部分一致(エイリアス)
    """
    key = name.lower().strip()

    # 1. SCENARIOS キーの完全一致
    if key in SCENARIOS:
        return SCENARIOS[key]

    # 2. エイリアスの完全一致
    alias_key = SCENARIO_ALIASES.get(key) or SCENARIO_ALIASES.get(name)
    if alias_key and alias_key in SCENARIOS:
        return SCENARIOS[alias_key]

    # 3. エイリアスの部分一致（入力がエイリアスを含む or エイリアスが入力を含む）
    if len(key) >= 2:
        for alias, scenario_key in SCENARIO_ALIASES.items():
            if alias in key or key in alias:
                if scenario_key in SCENARIOS:
                    return SCENARIOS[scenario_key]

    return None


def _match_target(
    target: str,
    sector: Optional[str],
    currency: str,
    region: str,
    etf_asset_class: Optional[str] = None,
) -> bool:
    """シナリオのtargetが銘柄の属性にマッチするか判定。"""
    # 地域ベースのマッチング
    if target == "日本株全般" and region == "Japan":
        return True
    if target == "米国株全般" and region == "US":
        return True
    if target == "米国株(円建て)" and region == "US":
        return True
    if target == "ASEAN株" and region in ("Singapore", "Thailand", "Malaysia", "Indonesia", "Philippines"):
        return True
    if target == "中国関連株" and region in ("China", "Hong Kong"):
        return True
    if target in ("円建て", "円建て外貨資産") and currency == "JPY":
        return True
    if target == "全外貨資産" and currency != "JPY":
        return True
    if target in ("日本輸出株", "輸出企業") and region == "Japan":
        sector_list = _TARGET_TO_SECTORS.get(target)
        if sector_list is None:
            return True
        return sector in sector_list if sector else False
    if target in ("日本内需株", "内需企業") and region == "Japan":
        sector_list = _TARGET_TO_SECTORS.get(target)
        if sector_list is None:
            return True
        return sector in sector_list if sector else False

    # ETF資産クラスマッチング（KIK-358）
    # 非株式ETF（金・債券）は自分の資産クラスのみマッチ
    if etf_asset_class:
        if etf_asset_class in ("金・安全資産", "長期債"):
            return target == etf_asset_class
        if target == etf_asset_class:
            return True
        # 株式インカムETFはシクリカル株としても反応する
        if etf_asset_class == "株式インカム" and target == "シクリカル株":
            return True

    # 非テック株: テクノロジー・通信以外の全セクター
    if target == "非テック株":
        return sector not in ("Technology", "Communication Services") if sector else True

    # セクターベースのマッチング
    sector_list = _TARGET_TO_SECTORS.get(target)
    if sector_list is not None and sector in (sector_list or []):
        return True

    # 高配当株: dividend_yield で判定するが、ここでは単純にFalse
    # (caller側でdividend_yieldチェックが必要な場合は別途)
    return False


def compute_stock_scenario_impact(
    stock_info: dict,
    sensitivity: dict,
    scenario: dict,
) -> dict:
    """1銘柄のシナリオ別影響を算出。

    Parameters
    ----------
    stock_info : dict
        銘柄のファンダメンタルデータ（sector, country, currency等含む）
    sensitivity : dict
        shock_sensitivity.analyze_stock_sensitivity() の結果。
        未実装の場合は空dictでもOK。利用可能なキー:
        - "composite_shock": float (統合ショック影響率)
        - "fundamental_score": float
        - "technical_score": float
    scenario : dict
        SCENARIOS の1エントリ

    Returns
    -------
    dict
        {
            "symbol": str,
            "direct_impact": float,      # 直接影響率
            "currency_impact": float,     # 通貨効果率
            "total_impact": float,        # 合計影響率
            "price_impact": float,        # 株価変動額
            "causal_chain": list[str],    # 因果連鎖の説明
        }
    """
    symbol = stock_info.get("symbol", "")
    sector = stock_info.get("sector")
    currency = _infer_currency(symbol, stock_info)
    region = _infer_region(symbol, stock_info)
    price = _safe_float(stock_info.get("price"))
    beta = _safe_float(stock_info.get("beta"), default=1.0)
    etf_asset_class = _get_etf_asset_class(symbol, stock_info)

    effects = scenario.get("effects", {})
    base_shock = _safe_float(scenario.get("base_shock"))
    causal_chain: list[str] = []

    # 1. base_shock をbetaで調整（フォールバック用）
    beta_impact = base_shock * beta
    causal_chain.append(
        f"ベースショック {base_shock:+.1%} x beta({beta:.2f}) = {beta_impact:+.1%}"
    )

    # 2. primary/secondary effects のマッチング
    matched_impacts: list[float] = []
    for effect_group in ("primary", "secondary"):
        for effect in effects.get(effect_group, []):
            target = effect.get("target", "")
            impact = _safe_float(effect.get("impact"))
            reason = effect.get("reason", "")
            if _match_target(target, sector, currency, region, etf_asset_class):
                matched_impacts.append(impact)
                sign = "+" if impact >= 0 else ""
                causal_chain.append(
                    f"[{effect_group}] {target}: {sign}{impact:.1%} ({reason})"
                )

    # マッチした影響がある場合はその平均を採用し、betaで微調整する
    # セクター影響は base_shock を既に内包しているため加算ではなく置換する
    # beta調整は抑制（dampened）: multiplier = 0.7 + 0.3 * beta
    #   beta=1.0 → 1.0（中立）, beta=0.5 → 0.85, beta=2.0 → 1.30
    if matched_impacts:
        avg_matched = sum(matched_impacts) / len(matched_impacts)
        beta_multiplier = 0.7 + 0.3 * beta
        direct_impact = avg_matched * beta_multiplier
        causal_chain.append(
            f"セクター影響平均: {avg_matched:+.1%} x beta調整({beta_multiplier:.2f})"
            f" = {direct_impact:+.1%}"
        )
    else:
        direct_impact = beta_impact
        causal_chain.append("マッチするセクター影響なし → ベースショック×beta を使用")

    # 3. sensitivity による調整（利用可能な場合）
    composite_shock = _safe_float(sensitivity.get("composite_shock"))
    if composite_shock != 0.0:
        # sensitivity のスコアで影響を微調整（最大 +/- 20%）
        adjustment = composite_shock * 0.2
        direct_impact *= (1.0 + adjustment)
        causal_chain.append(
            f"感応度調整: composite_shock={composite_shock:+.2f} → 影響率 x{1.0 + adjustment:.2f}"
        )

    # 4. 通貨効果
    currency_data = effects.get("currency", {})
    currency_impact = 0.0
    if currency != "JPY":
        # 外貨建て資産への為替影響
        impact_on_foreign = _safe_float(currency_data.get("impact_on_foreign"))
        currency_impact = impact_on_foreign
        usd_jpy_change = _safe_float(currency_data.get("usd_jpy_change"))
        if currency_impact != 0.0:
            causal_chain.append(
                f"通貨効果: USD/JPY {usd_jpy_change:+.0f}円 → 外貨資産 {currency_impact:+.1%}"
            )
    elif currency == "JPY":
        # 円建て資産: 円安→マイナス方向の影響は既にprimary/secondaryで反映
        pass

    # 5. 合計
    total_impact = direct_impact + currency_impact
    price_impact = price * total_impact

    causal_chain.append(
        f"合計影響: 直接{direct_impact:+.1%} + 通貨{currency_impact:+.1%} = {total_impact:+.1%}"
    )

    return {
        "symbol": symbol,
        "name": stock_info.get("name", ""),
        "direct_impact": round(direct_impact, 4),
        "currency_impact": round(currency_impact, 4),
        "total_impact": round(total_impact, 4),
        "price_impact": round(price_impact, 2),
        "causal_chain": causal_chain,
    }


def analyze_portfolio_scenario(
    portfolio: list[dict],
    sensitivities: list[dict],
    weights: list[float],
    scenario: dict,
) -> dict:
    """PF全体のシナリオ分析。

    Parameters
    ----------
    portfolio : list[dict]
        各銘柄のstock_infoリスト
    sensitivities : list[dict]
        各銘柄のsensitivityリスト（空dictのリストでもOK）
    weights : list[float]
        各銘柄のPF比率（合計≒1.0）
    scenario : dict
        SCENARIOS の1エントリ

    Returns
    -------
    dict
        {
            "scenario_name": str,
            "trigger": str,
            "portfolio_impact": float,      # PF全体の影響率
            "portfolio_value_change": float, # PF全体の評価額変動
            "stock_impacts": list[dict],     # 各銘柄の影響
            "causal_chain_summary": str,     # 因果連鎖の全体サマリ
            "offset_factors": list[str],     # 相殺要因
            "time_axis": str,                # 時間軸
            "judgment": str,                 # "継続" / "認識" / "要対応"
        }
    """
    # 入力の整合性チェック
    n = len(portfolio)
    if len(sensitivities) < n:
        sensitivities = sensitivities + [{}] * (n - len(sensitivities))
    if len(weights) < n:
        # 足りない場合は均等配分で埋める
        remaining = max(0.0, 1.0 - sum(weights))
        missing_count = n - len(weights)
        if missing_count > 0:
            weights = list(weights) + [remaining / missing_count] * missing_count

    # 各銘柄のシナリオ影響を計算
    stock_impacts: list[dict] = []
    portfolio_impact = 0.0
    portfolio_value_change = 0.0

    for i, (stock, sens, weight) in enumerate(zip(portfolio, sensitivities, weights)):
        impact = compute_stock_scenario_impact(stock, sens, scenario)
        impact["weight"] = round(weight, 4)
        impact["pf_contribution"] = round(impact["total_impact"] * weight, 4)
        stock_impacts.append(impact)

        portfolio_impact += impact["total_impact"] * weight
        portfolio_value_change += impact["price_impact"] * weight

    # 因果連鎖サマリを生成
    effects = scenario.get("effects", {})
    chain_lines: list[str] = []
    chain_lines.append(f"トリガー: {scenario.get('trigger', '不明')}")
    chain_lines.append(f"  ↓")
    chain_lines.append(f"ベースショック: {_safe_float(scenario.get('base_shock')):+.1%}")
    chain_lines.append(f"  ↓")

    # Primary effects
    for effect in effects.get("primary", []):
        target = effect.get("target", "")
        impact = _safe_float(effect.get("impact"))
        reason = effect.get("reason", "")
        chain_lines.append(f"[一次] {target} {impact:+.1%} ({reason})")

    if effects.get("secondary"):
        chain_lines.append(f"  ↓")
        for effect in effects.get("secondary", []):
            target = effect.get("target", "")
            impact = _safe_float(effect.get("impact"))
            reason = effect.get("reason", "")
            chain_lines.append(f"[二次] {target} {impact:+.1%} ({reason})")

    currency_data = effects.get("currency", {})
    if currency_data:
        usd_jpy = _safe_float(currency_data.get("usd_jpy_change"))
        fx_impact = _safe_float(currency_data.get("impact_on_foreign"))
        chain_lines.append(f"  ↓")
        chain_lines.append(f"[為替] USD/JPY {usd_jpy:+.0f}円 → 外貨資産 {fx_impact:+.1%}")

    chain_lines.append(f"  ↓")
    chain_lines.append(f"PF全体影響: {portfolio_impact:+.1%}")

    causal_chain_summary = "\n".join(chain_lines)

    # 相殺要因
    offset_factors = effects.get("offset", [])

    # 時間軸
    time_axis = effects.get("time_axis", "不明")

    # 判定
    if portfolio_impact <= -0.30:
        judgment = "要対応"
    elif portfolio_impact <= -0.15:
        judgment = "認識"
    else:
        judgment = "継続"

    return {
        "scenario_name": scenario.get("name", "不明"),
        "trigger": scenario.get("trigger", "不明"),
        "portfolio_impact": round(portfolio_impact, 4),
        "portfolio_value_change": round(portfolio_value_change, 2),
        "stock_impacts": stock_impacts,
        "causal_chain_summary": causal_chain_summary,
        "offset_factors": offset_factors,
        "time_axis": time_axis,
        "judgment": judgment,
    }
