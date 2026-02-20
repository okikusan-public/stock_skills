"""Output formatters for deep research results (KIK-367)."""

from typing import Optional

from src.output._format_helpers import fmt_pct as _fmt_pct
from src.output._format_helpers import fmt_float as _fmt_float


def _fmt_int(value) -> str:
    """Format a value as a comma-separated integer, or '-' if None."""
    if value is None:
        return "-"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return "-"


def _sentiment_label(score: float) -> str:
    """Convert a sentiment score (-1 to 1) to a Japanese label.

    >= 0.3  -> strong bull
    >= 0.1  -> slightly bull
    >= -0.1 -> neutral
    >= -0.3 -> slightly bear
    else    -> bear
    """
    if score >= 0.3:
        return "強気"
    if score >= 0.1:
        return "やや強気"
    if score >= -0.1:
        return "中立"
    if score >= -0.3:
        return "やや弱気"
    return "弱気"


def _fmt_market_cap(value: Optional[float]) -> str:
    """Format market cap with appropriate unit (億円 or B)."""
    if value is None:
        return "-"
    if value >= 1e12:
        return f"{value / 1e12:.2f}兆"
    if value >= 1e8:
        return f"{value / 1e8:.0f}億"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    return _fmt_int(value)


# ---------------------------------------------------------------------------
# format_stock_research
# ---------------------------------------------------------------------------

def format_stock_research(data: dict) -> str:
    """Format stock research as a Markdown report.

    Parameters
    ----------
    data : dict
        Output from researcher.research_stock().

    Returns
    -------
    str
        Markdown-formatted report.
    """
    if not data:
        return "リサーチデータがありません。"

    symbol = data.get("symbol", "-")
    name = data.get("name") or ""
    title = f"{name} ({symbol})" if name else symbol

    lines: list[str] = []
    lines.append(f"# {title} 深掘りリサーチ")
    lines.append("")

    fundamentals = data.get("fundamentals", {})

    # --- Basic info table ---
    lines.append("## 基本情報")
    lines.append("| 項目 | 値 |")
    lines.append("|:-----|:---|")
    lines.append(f"| セクター | {fundamentals.get('sector') or '-'} |")
    lines.append(f"| 業種 | {fundamentals.get('industry') or '-'} |")
    lines.append(f"| 株価 | {_fmt_float(fundamentals.get('price'), 0)} |")
    lines.append(f"| 時価総額 | {_fmt_market_cap(fundamentals.get('market_cap'))} |")
    lines.append("")

    # --- Valuation table ---
    lines.append("## バリュエーション")
    lines.append("| 指標 | 値 |")
    lines.append("|:-----|---:|")
    lines.append(f"| PER | {_fmt_float(fundamentals.get('per'))} |")
    lines.append(f"| PBR | {_fmt_float(fundamentals.get('pbr'))} |")
    lines.append(f"| 配当利回り | {_fmt_pct(fundamentals.get('dividend_yield'))} |")
    lines.append(f"| ROE | {_fmt_pct(fundamentals.get('roe'))} |")

    value_score = data.get("value_score")
    score_str = _fmt_float(value_score) if value_score is not None else "-"
    lines.append(f"| 割安スコア | {score_str}/100 |")
    lines.append("")

    # --- News ---
    news = data.get("news", [])
    lines.append("## 最新ニュース")
    if news:
        for item in news[:10]:
            title_text = item.get("title", "")
            publisher = item.get("publisher", "")
            pub_date = item.get("providerPublishTime") or item.get("date", "")
            suffix_parts = []
            if publisher:
                suffix_parts.append(publisher)
            if pub_date:
                suffix_parts.append(str(pub_date))
            suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
            if title_text:
                lines.append(f"- {title_text}{suffix}")
    else:
        lines.append("最新ニュースはありません。")
    lines.append("")

    # --- X Sentiment ---
    x_sentiment = data.get("x_sentiment", {})
    _has_sentiment = (
        x_sentiment.get("positive")
        or x_sentiment.get("negative")
        or x_sentiment.get("raw_response")
    )

    lines.append("## X (Twitter) センチメント")

    if _has_sentiment:
        score = x_sentiment.get("sentiment_score", 0.0)
        label = _sentiment_label(score)
        lines.append(f"**判定: {label}** (スコア: {_fmt_float(score)})")
        lines.append("")

        positive = x_sentiment.get("positive", [])
        if positive:
            lines.append("### ポジティブ要因")
            for p in positive:
                lines.append(f"- {p}")
            lines.append("")

        negative = x_sentiment.get("negative", [])
        if negative:
            lines.append("### ネガティブ要因")
            for n in negative:
                lines.append(f"- {n}")
            lines.append("")
    else:
        lines.append(
            "*Grok API (XAI_API_KEY) が未設定のため、Xセンチメント分析は利用できません。*"
        )
        lines.append("")

    # --- Deep research (Grok API) ---
    grok = data.get("grok_research", {})
    _has_grok = (
        grok.get("recent_news")
        or grok.get("catalysts", {}).get("positive")
        or grok.get("catalysts", {}).get("negative")
        or grok.get("analyst_views")
        or grok.get("competitive_notes")
        or grok.get("raw_response")
    )

    if _has_grok:
        lines.append("## 深掘りリサーチ (Grok API)")
        lines.append("")

        # Recent news
        recent_news = grok.get("recent_news", [])
        if recent_news:
            lines.append("### 最近の重要ニュース")
            for item in recent_news:
                lines.append(f"- {item}")
            lines.append("")

        # Catalysts
        catalysts = grok.get("catalysts", {})
        positive_catalysts = catalysts.get("positive", [])
        negative_catalysts = catalysts.get("negative", [])
        if positive_catalysts or negative_catalysts:
            lines.append("### 業績材料")
            if positive_catalysts:
                lines.append("**ポジティブ:**")
                for c in positive_catalysts:
                    lines.append(f"- {c}")
                lines.append("")
            if negative_catalysts:
                lines.append("**ネガティブ:**")
                for c in negative_catalysts:
                    lines.append(f"- {c}")
                lines.append("")

        # Analyst views
        analyst_views = grok.get("analyst_views", [])
        if analyst_views:
            lines.append("### アナリスト・機関投資家の見方")
            for v in analyst_views:
                lines.append(f"- {v}")
            lines.append("")

        # Competitive notes
        competitive = grok.get("competitive_notes", [])
        if competitive:
            lines.append("### 競合比較の注目点")
            for c in competitive:
                lines.append(f"- {c}")
            lines.append("")
    else:
        lines.append("## 深掘りリサーチ")
        lines.append(
            "*Grok API (XAI_API_KEY) が未設定のため、Web/X検索リサーチは利用できません。*"
        )
        lines.append(
            "*XAI_API_KEY 環境変数を設定すると、X投稿・Web検索による深掘り分析が有効になります。*"
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# format_industry_research
# ---------------------------------------------------------------------------

def format_industry_research(data: dict) -> str:
    """Format industry research as a Markdown report.

    Parameters
    ----------
    data : dict
        Output from researcher.research_industry().

    Returns
    -------
    str
        Markdown-formatted report.
    """
    if not data:
        return "リサーチデータがありません。"

    theme = data.get("theme", "-")

    if data.get("api_unavailable"):
        lines: list[str] = []
        lines.append(f"# {theme} - 業界リサーチ")
        lines.append("")
        lines.append(
            "*業界リサーチにはGrok APIが必要です。"
            "XAI_API_KEY 環境変数を設定してください。*"
        )
        lines.append("")
        return "\n".join(lines)

    grok = data.get("grok_research", {})
    lines: list[str] = []
    lines.append(f"# {theme} - 業界リサーチ")
    lines.append("")

    # Trends
    trends = grok.get("trends", [])
    lines.append("## トレンド")
    if trends:
        for t in trends:
            lines.append(f"- {t}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Key players
    key_players = grok.get("key_players", [])
    lines.append("## 主要プレイヤー")
    if key_players:
        lines.append("| 企業 | ティッカー | 注目理由 |")
        lines.append("|:-----|:----------|:---------|")
        for p in key_players:
            if isinstance(p, dict):
                name = p.get("name", "-")
                ticker = p.get("ticker", "-")
                note = p.get("note", "-")
                lines.append(f"| {name} | {ticker} | {note} |")
            else:
                lines.append(f"| {p} | - | - |")
    else:
        lines.append("情報なし")
    lines.append("")

    # Growth drivers
    drivers = grok.get("growth_drivers", [])
    lines.append("## 成長ドライバー")
    if drivers:
        for d in drivers:
            lines.append(f"- {d}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Risks
    risks = grok.get("risks", [])
    lines.append("## リスク要因")
    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Regulatory
    regulatory = grok.get("regulatory", [])
    lines.append("## 規制・政策動向")
    if regulatory:
        for r in regulatory:
            lines.append(f"- {r}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Investor focus
    focus = grok.get("investor_focus", [])
    lines.append("## 投資家の注目ポイント")
    if focus:
        for f in focus:
            lines.append(f"- {f}")
    else:
        lines.append("情報なし")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# format_market_research
# ---------------------------------------------------------------------------

def _fmt_change(value, is_point_diff: bool) -> str:
    """Format a daily/weekly change value for the macro table."""
    if value is None:
        return "-"
    if is_point_diff:
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.2f}"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.2f}%"


def _vix_label(vix_price: float) -> str:
    """Convert VIX level to a Fear & Greed label."""
    if vix_price < 15:
        return "低ボラティリティ（楽観相場）"
    if vix_price < 25:
        return "通常レンジ"
    if vix_price < 35:
        return "不安拡大"
    return "パニック水準"


def format_market_research(data: dict) -> str:
    """Format market overview research as a Markdown report.

    Parameters
    ----------
    data : dict
        Output from researcher.research_market().

    Returns
    -------
    str
        Markdown-formatted report.
    """
    if not data:
        return "リサーチデータがありません。"

    market = data.get("market", "-")

    lines: list[str] = []
    lines.append(f"# {market} - マーケット概況")
    lines.append("")

    # === Layer 1: Macro indicators table (yfinance) ===
    indicators = data.get("macro_indicators", [])
    if indicators:
        lines.append("## 主要指標")
        lines.append("| 指標 | 現在値 | 前日比 | 週間変化 |")
        lines.append("|:-----|------:|------:|--------:|")
        for ind in indicators:
            name = ind.get("name", "-")
            price = ind.get("price")
            is_point = ind.get("is_point_diff", False)
            price_str = _fmt_float(price, 2) if price is not None else "-"
            daily_str = _fmt_change(ind.get("daily_change"), is_point)
            weekly_str = _fmt_change(ind.get("weekly_change"), is_point)
            lines.append(f"| {name} | {price_str} | {daily_str} | {weekly_str} |")
        lines.append("")

        # Fear & Greed (VIX-based)
        vix = next((i for i in indicators if i.get("name") == "VIX"), None)
        if vix and vix.get("price") is not None:
            vix_price = vix["price"]
            label = _vix_label(vix_price)
            lines.append(f"**Fear & Greed: {label}** (VIX: {_fmt_float(vix_price, 2)})")
            lines.append("")

    # === Layer 2: Grok qualitative ===
    if data.get("api_unavailable"):
        lines.append("*Grok API (XAI_API_KEY) 未設定のため定性分析はスキップ*")
        lines.append("")
        return "\n".join(lines)

    grok = data.get("grok_research", {})

    # Price action
    price_action = grok.get("price_action", "")
    lines.append("## 直近の値動き")
    lines.append(price_action if price_action else "情報なし")
    lines.append("")

    # Macro factors
    macro = grok.get("macro_factors", [])
    lines.append("## マクロ経済要因")
    if macro:
        for m in macro:
            lines.append(f"- {m}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Sentiment
    sentiment = grok.get("sentiment", {})
    score = sentiment.get("score", 0.0) if isinstance(sentiment, dict) else 0.0
    summary = sentiment.get("summary", "") if isinstance(sentiment, dict) else ""
    label = _sentiment_label(score)
    lines.append("## センチメント")
    lines.append(f"**判定: {label}** (スコア: {_fmt_float(score)})")
    if summary:
        lines.append(summary)
    lines.append("")

    # Upcoming events
    events = grok.get("upcoming_events", [])
    lines.append("## 注目イベント・経済指標")
    if events:
        for e in events:
            lines.append(f"- {e}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Sector rotation
    rotation = grok.get("sector_rotation", [])
    lines.append("## セクターローテーション")
    if rotation:
        for r in rotation:
            lines.append(f"- {r}")
    else:
        lines.append("情報なし")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# format_business_research
# ---------------------------------------------------------------------------

def format_business_research(data: dict) -> str:
    """Format business model research as a Markdown report.

    Parameters
    ----------
    data : dict
        Output from researcher.research_business().

    Returns
    -------
    str
        Markdown-formatted report.
    """
    if not data:
        return "リサーチデータがありません。"

    symbol = data.get("symbol", "-")
    name = data.get("name") or ""
    title = f"{name} ({symbol})" if name else symbol

    if data.get("api_unavailable"):
        lines: list[str] = []
        lines.append(f"# {title} - ビジネスモデル分析")
        lines.append("")
        lines.append(
            "*ビジネスモデル分析にはGrok APIが必要です。"
            "XAI_API_KEY 環境変数を設定してください。*"
        )
        lines.append("")
        return "\n".join(lines)

    grok = data.get("grok_research", {})
    lines: list[str] = []
    lines.append(f"# {title} - ビジネスモデル分析")
    lines.append("")

    # Overview
    overview = grok.get("overview", "")
    lines.append("## 事業概要")
    lines.append(overview if overview else "情報なし")
    lines.append("")

    # Segments
    segments = grok.get("segments", [])
    lines.append("## 事業セグメント")
    if segments:
        lines.append("| セグメント | 売上比率 | 概要 |")
        lines.append("|:-----------|:---------|:-----|")
        for seg in segments:
            if isinstance(seg, dict):
                seg_name = seg.get("name", "-")
                share = seg.get("revenue_share", "-")
                desc = seg.get("description", "-")
                lines.append(f"| {seg_name} | {share} | {desc} |")
            else:
                lines.append(f"| {seg} | - | - |")
    else:
        lines.append("情報なし")
    lines.append("")

    # Revenue model
    revenue_model = grok.get("revenue_model", "")
    lines.append("## 収益モデル")
    lines.append(revenue_model if revenue_model else "情報なし")
    lines.append("")

    # Competitive advantages
    advantages = grok.get("competitive_advantages", [])
    lines.append("## 競争優位性")
    if advantages:
        for a in advantages:
            lines.append(f"- {a}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Key metrics
    metrics = grok.get("key_metrics", [])
    lines.append("## 重要KPI")
    if metrics:
        for m in metrics:
            lines.append(f"- {m}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Growth strategy
    strategy = grok.get("growth_strategy", [])
    lines.append("## 成長戦略")
    if strategy:
        for s in strategy:
            lines.append(f"- {s}")
    else:
        lines.append("情報なし")
    lines.append("")

    # Risks
    risks = grok.get("risks", [])
    lines.append("## ビジネスリスク")
    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("情報なし")
    lines.append("")

    return "\n".join(lines)
