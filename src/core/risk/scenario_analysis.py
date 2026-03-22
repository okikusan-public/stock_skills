"""Scenario-based causal chain analysis for portfolio stress testing (KIK-341)."""

from typing import Optional

from src.core.common import safe_float as _safe_float
from src.core.risk.scenario_definitions import (
    SCENARIOS,
    SCENARIO_ALIASES,
    TARGET_TO_SECTORS,
    SUFFIX_TO_REGION,
    ETF_ASSET_CLASS,
)
from src.core.ticker_utils import infer_currency as _infer_currency


def _get_etf_asset_class(symbol: str, stock_info: dict) -> Optional[str]:
    """Return the ETF asset class if the symbol is a known ETF, else None."""
    # Strip suffix for lookup (e.g., "1326.T" -> not in mapping, just use symbol)
    base_symbol = symbol.split(".")[0] if "." in symbol else symbol
    asset_class = ETF_ASSET_CLASS.get(base_symbol)
    if asset_class:
        return asset_class
    # quoteType fallback
    if stock_info.get("quoteType") == "ETF":
        return "株式インカム"  # Default ETF class (conservative equity)
    return None


def _infer_region(symbol: str, stock_info: dict) -> str:
    """銘柄の地域を推定する。"""
    country = stock_info.get("country") or stock_info.get("region")
    if country:
        return country
    for suffix, region in SUFFIX_TO_REGION.items():
        if symbol.endswith(suffix):
            return region
    return "US"


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
    # 通貨ベースのマッチング（ETF含む全銘柄に適用）
    if target in ("円建て", "円建て外貨資産") and currency == "JPY":
        return True
    if target == "全外貨資産" and currency != "JPY":
        return True

    # ETF資産クラスマッチング（KIK-358）
    # 非株式ETF（金・債券）は自分の資産クラスのみマッチ
    # 地域マッチングより先に判定し、"米国株全般" 等への誤マッチを防ぐ
    if etf_asset_class:
        if etf_asset_class in ("金・安全資産", "長期債"):
            return target == etf_asset_class
        if target == etf_asset_class:
            return True
        # 株式インカムETFはシクリカル株としても反応する
        if etf_asset_class == "株式インカム" and target == "シクリカル株":
            return True
        # 株式インカムETFは地域マッチングにもフォールスルー

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
    if target in ("日本輸出株", "輸出企業") and region == "Japan":
        sector_list = TARGET_TO_SECTORS.get(target)
        if sector_list is None:
            return True
        return sector in sector_list if sector else False
    if target in ("日本内需株", "内需企業") and region == "Japan":
        sector_list = TARGET_TO_SECTORS.get(target)
        if sector_list is None:
            return True
        return sector in sector_list if sector else False

    # 非テック株: テクノロジー・通信以外の全セクター
    if target == "非テック株":
        return sector not in ("Technology", "Communication Services") if sector else True

    # セクターベースのマッチング
    sector_list = TARGET_TO_SECTORS.get(target)
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
