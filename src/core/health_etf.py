"""ETF-specific health check logic (KIK-469).

Extracted from health_check.py as part of KIK-512 module split.
"""


def check_etf_health(stock_detail: dict) -> dict:
    """ETF固有のヘルスチェック (KIK-469).

    Returns dict with:
        expense_ratio, expense_label, aum, aum_label, score (0-100), alerts,
        fund_category, fund_family.
    """
    info = stock_detail.get("info", stock_detail)
    er = info.get("expense_ratio")
    aum = info.get("total_assets_fund")
    alerts: list[str] = []

    # 経費率評価
    if er is not None:
        if er <= 0.001:
            expense_label = "超低コスト"
        elif er <= 0.005:
            expense_label = "低コスト"
        elif er <= 0.01:
            expense_label = "やや高め"
            alerts.append(f"経費率 {er*100:.2f}% はやや高め")
        else:
            expense_label = "高コスト"
            alerts.append(f"経費率 {er*100:.2f}% は高コスト（長期保有に不利）")
    else:
        expense_label = "-"

    # AUM評価
    if aum is not None:
        if aum >= 1_000_000_000:
            aum_label = "十分"
        elif aum >= 100_000_000:
            aum_label = "小規模"
            alerts.append("AUM小規模（流動性・償還リスクに注意）")
        else:
            aum_label = "極小"
            alerts.append("AUM極小（償還リスクあり）")
    else:
        aum_label = "-"

    # ETFスコア（0-100、経費率とAUMベース）
    score = 50  # baseline
    if er is not None:
        if er <= 0.001:
            score += 25
        elif er <= 0.005:
            score += 15
        elif er <= 0.01:
            score += 0
        else:
            score -= 15
    if aum is not None:
        if aum >= 10_000_000_000:
            score += 25
        elif aum >= 1_000_000_000:
            score += 15
        elif aum >= 100_000_000:
            score += 0
        else:
            score -= 15

    return {
        "expense_ratio": er,
        "expense_label": expense_label,
        "aum": aum,
        "aum_label": aum_label,
        "score": max(0, min(100, score)),
        "alerts": alerts,
        "fund_category": info.get("fund_category"),
        "fund_family": info.get("fund_family"),
    }
