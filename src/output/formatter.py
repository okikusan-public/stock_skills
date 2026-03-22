"""Output formatters for screening results (KIK-575: unified renderer)."""

from src.output._format_helpers import (
    fmt_pct as _fmt_pct,
    fmt_float as _fmt_float,
    build_label as _build_label,
    render_screening_table,
)


# ---------------------------------------------------------------------------
# Common cell helpers
# ---------------------------------------------------------------------------

def _price_cell(rank, row):
    return _fmt_float(row.get("price"), decimals=0) if row.get("price") is not None else "-"


# ---------------------------------------------------------------------------
# 1. Default (legacy)
# ---------------------------------------------------------------------------

def format_markdown(results: list[dict]) -> str:
    """Format screening results as a Markdown table."""
    return render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("株価", "-----:", _price_cell),
        ("PER", "----:", lambda r, row: _fmt_float(row.get("per"))),
        ("PBR", "----:", lambda r, row: _fmt_float(row.get("pbr"))),
        ("配当利回り", "---------:", lambda r, row: _fmt_pct(row.get("dividend_yield"))),
        ("ROE", "----:", lambda r, row: _fmt_pct(row.get("roe"))),
        ("スコア", "------:", lambda r, row: _fmt_float(row.get("value_score"))),
    ], empty_msg="該当する銘柄が見つかりませんでした。")


# ---------------------------------------------------------------------------
# 2. Query (value, high-dividend, etc.)
# ---------------------------------------------------------------------------

def format_query_markdown(results: list[dict]) -> str:
    """Format EquityQuery screening results with sector column."""
    return render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("セクター", ":---------", lambda r, row: row.get("sector") or "-"),
        ("株価", "-----:", _price_cell),
        ("PER", "----:", lambda r, row: _fmt_float(row.get("per"))),
        ("PBR", "----:", lambda r, row: _fmt_float(row.get("pbr"))),
        ("配当利回り", "---------:", lambda r, row: _fmt_pct(row.get("dividend_yield"))),
        ("ROE", "----:", lambda r, row: _fmt_pct(row.get("roe"))),
        ("スコア", "------:", lambda r, row: _fmt_float(row.get("value_score"))),
    ], empty_msg="該当する銘柄が見つかりませんでした。")


# ---------------------------------------------------------------------------
# 3. Pullback
# ---------------------------------------------------------------------------

def format_pullback_markdown(results: list[dict]) -> str:
    """Format pullback screening results."""
    def _bounce(r, row):
        bs = row.get("bounce_score")
        return f"{bs:.0f}点" if bs is not None else "-"

    def _match(r, row):
        return "★完全一致" if row.get("match_type", "full") == "full" else "△部分一致"

    return render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("株価", "-----:", _price_cell),
        ("PER", "----:", lambda r, row: _fmt_float(row.get("per"))),
        ("押し目%", "------:", lambda r, row: _fmt_pct(row.get("pullback_pct"))),
        ("RSI", "----:", lambda r, row: _fmt_float(row.get("rsi"), decimals=1)),
        ("出来高比", "-------:", lambda r, row: _fmt_float(row.get("volume_ratio"))),
        ("SMA50", "------:", lambda r, row: _fmt_float(row.get("sma50"), decimals=0) if row.get("sma50") is not None else "-"),
        ("SMA200", "-------:", lambda r, row: _fmt_float(row.get("sma200"), decimals=0) if row.get("sma200") is not None else "-"),
        ("スコア", "------:", _bounce),
        ("一致度", ":------:", _match),
        ("総合スコア", "------:", lambda r, row: _fmt_float(row.get("final_score") or row.get("value_score"))),
    ], empty_msg="押し目条件に合致する銘柄が見つかりませんでした。（上昇トレンド中の押し目銘柄なし）")


# ---------------------------------------------------------------------------
# 4. Growth
# ---------------------------------------------------------------------------

def format_growth_markdown(results: list[dict]) -> str:
    """Format growth screening results."""
    return render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("セクター", ":---------", lambda r, row: row.get("sector") or "-"),
        ("株価", "-----:", _price_cell),
        ("PER", "----:", lambda r, row: _fmt_float(row.get("per"))),
        ("PBR", "----:", lambda r, row: _fmt_float(row.get("pbr"))),
        ("EPS成長", "-------:", lambda r, row: _fmt_pct(row.get("eps_growth"))),
        ("売上成長", "--------:", lambda r, row: _fmt_pct(row.get("revenue_growth"))),
        ("ROE", "----:", lambda r, row: _fmt_pct(row.get("roe"))),
    ], empty_msg="成長条件に合致する銘柄が見つかりませんでした。")


# ---------------------------------------------------------------------------
# 5. Alpha
# ---------------------------------------------------------------------------

def _alpha_indicator(score):
    """Map change sub-score to indicator: ◎/○/△/×."""
    if score is None:
        return "-"
    if score >= 20:
        return "◎"
    if score >= 15:
        return "○"
    if score >= 10:
        return "△"
    return "×"


def format_alpha_markdown(results: list[dict]) -> str:
    """Format alpha signal screening results (2-axis scoring)."""
    def _pullback(r, row):
        pb = row.get("pullback_match", "none")
        return "★" if pb == "full" else "△" if pb == "partial" else "-"

    return render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("株価", "-----:", _price_cell),
        ("PER", "----:", lambda r, row: _fmt_float(row.get("per"))),
        ("PBR", "----:", lambda r, row: _fmt_float(row.get("pbr"))),
        ("割安", "----:", lambda r, row: _fmt_float(row.get("value_score"))),
        ("変化", "----:", lambda r, row: _fmt_float(row.get("change_score"))),
        ("総合", "----:", lambda r, row: _fmt_float(row.get("total_score"))),
        ("押し目", ":------:", _pullback),
        ("ア", ":--:", lambda r, row: _alpha_indicator(row.get("accruals_score"))),
        ("加速", ":---:", lambda r, row: _alpha_indicator(row.get("rev_accel_score"))),
        ("FCF", ":---:", lambda r, row: _alpha_indicator(row.get("fcf_yield_score"))),
        ("ROE趨勢", ":------:", lambda r, row: _alpha_indicator(row.get("roe_trend_score"))),
    ], empty_msg="アルファシグナル条件に合致する銘柄が見つかりませんでした。", legends=[
        "**凡例**: 割安=割安スコア(100点) / 変化=変化スコア(100点) / 総合=割安+変化(+押し目ボーナス)",
        "**変化指標**: ア=アクルーアルズ(利益の質) / 加速=売上成長加速度 / FCF=FCF利回り / ROE趨勢=ROE改善トレンド",
        "**判定**: ◎=優秀(20+) ○=良好(15+) △=普通(10+) ×=不足(<10)",
    ])


# ---------------------------------------------------------------------------
# 6. Shareholder Return
# ---------------------------------------------------------------------------

def format_shareholder_return_markdown(results: list[dict]) -> str:
    """Format shareholder-return screening results."""
    def _sr_label(r, row):
        name = row.get("name", row.get("symbol", "?"))
        symbol = row.get("symbol", "")
        markers = row.get("_note_markers", "")
        suffix = f" {markers}" if markers else ""
        return f"{name} ({symbol}){suffix}"

    def _pct_manual(val):
        return f"{val*100:.2f}%" if val else "-"

    def _stability(r, row):
        label = row.get("return_stability_label", "-")
        reason = row.get("return_stability_reason")
        return f"{label}（{reason}）" if reason else label

    return render_screening_table(results, columns=[
        ("#", "--:", lambda r, row: str(r)),
        ("銘柄", ":-----", _sr_label),
        ("セクター", ":--------", lambda r, row: row.get("sector", "-")),
        ("PER", "----:", lambda r, row: f"{(row.get('per') or row.get('trailingPE') or 0):.1f}" if (row.get('per') or row.get('trailingPE')) else "-"),
        ("ROE", "----:", lambda r, row: f"{(row.get('roe') or row.get('returnOnEquity') or 0)*100:.1f}%" if (row.get('roe') or row.get('returnOnEquity')) else "-"),
        ("配当利回り", "----------:", lambda r, row: _pct_manual(row.get("dividend_yield_trailing") or row.get("dividend_yield"))),
        ("自社株買い", "---------:", lambda r, row: _pct_manual(row.get("buyback_yield"))),
        ("総還元率", "--------:", lambda r, row: f"**{row.get('total_shareholder_return',0)*100:.2f}%**" if row.get("total_shareholder_return") else "-"),
        ("安定度", ":------", _stability),
    ], empty_msg="_該当銘柄なし_")


# ---------------------------------------------------------------------------
# 7. Trending
# ---------------------------------------------------------------------------

def format_trending_markdown(results: list[dict], market_context: str = "") -> str:
    """Format trending stock screening results."""
    def _cls(r, row):
        c = row.get("classification", "")
        if "データ不足" in c:
            return "⚪不足"
        if "割安" in c:
            return "🟢割安"
        if "適正" in c:
            return "🟡適正"
        return "🔴割高"

    def _reason(r, row):
        reason = row.get("trending_reason") or "-"
        return reason[:37] + "..." if len(reason) > 40 else reason

    prefix = ""
    if market_context:
        prefix = f"> **X市場センチメント**: {market_context}\n\n"

    table = render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("話題の理由", ":---------", _reason),
        ("株価", "-----:", _price_cell),
        ("PER", "----:", lambda r, row: _fmt_float(row.get("per"))),
        ("PBR", "----:", lambda r, row: _fmt_float(row.get("pbr"))),
        ("配当利回り", "---------:", lambda r, row: _fmt_pct(row.get("dividend_yield"))),
        ("ROE", "----:", lambda r, row: _fmt_pct(row.get("roe"))),
        ("スコア", "------:", lambda r, row: _fmt_float(row.get("value_score"))),
        ("判定", ":----:", _cls),
    ], empty_msg="X上でトレンド中の銘柄が見つかりませんでした。", legends=[
        "**判定基準**: 🟢割安(スコア60+) / 🟡適正(スコア30-59) / 🔴割高(スコア30未満) / ⚪不足(データ取得失敗)",
        "**データソース**: X (Twitter) トレンド → Yahoo Finance ファンダメンタルズ",
    ])
    return prefix + table if prefix else table


# ---------------------------------------------------------------------------
# 8. Contrarian
# ---------------------------------------------------------------------------

_GRADE_ICON = {"A": "\U0001f7e2", "B": "\U0001f7e1", "C": "\u26aa", "D": "\U0001f534"}


def format_contrarian_markdown(results: list[dict]) -> str:
    """Format contrarian screening results (3-axis scoring)."""
    def _grade(r, row):
        g = row.get("contrarian_grade", "-")
        return f"{_GRADE_ICON.get(g, '')}{g}"

    return render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("株価", "-----:", _price_cell),
        ("PER", "----:", lambda r, row: _fmt_float(row.get("per"))),
        ("PBR", "----:", lambda r, row: _fmt_float(row.get("pbr"))),
        ("RSI", "----:", lambda r, row: _fmt_float(row.get("rsi"), decimals=1)),
        ("SMA200乖離", "---------:", lambda r, row: _fmt_pct(row.get("sma200_deviation"))),
        ("テク", "----:", lambda r, row: _fmt_float(row.get("tech_score"), decimals=0)),
        ("バリュ", "-----:", lambda r, row: _fmt_float(row.get("val_score"), decimals=0)),
        ("ファンダ", "------:", lambda r, row: _fmt_float(row.get("fund_score"), decimals=0)),
        ("総合", "----:", lambda r, row: _fmt_float(row.get("contrarian_score"), decimals=0)),
        ("判定", ":----:", _grade),
    ], empty_msg="逆張り条件に合致する銘柄が見つかりませんでした。", legends=[
        "**凡例**: テク=テクニカル逆張り(40pt) / バリュ=バリュエーション逆張り(30pt) / ファンダ=ファンダ乖離(30pt)",
        "**判定**: \U0001f7e2A(70+)=強い逆張り / \U0001f7e1B(50+)=逆張りあり / \u26aaC(30+)=弱い / \U0001f534D(<30)=なし",
    ])


# ---------------------------------------------------------------------------
# 9. Momentum
# ---------------------------------------------------------------------------

_SURGE_ICONS = {"accelerating": "\U0001f7e2", "surging": "\U0001f7e1", "overheated": "\U0001f534", "none": "\u26aa"}
_SURGE_LABELS = {"accelerating": "加速", "surging": "急騰", "overheated": "過熱", "none": "-"}


def format_momentum_markdown(results: list[dict]) -> str:
    """Format momentum/surge screening results."""
    def _level(r, row):
        lv = row.get("surge_level", "none")
        return f"{_SURGE_ICONS.get(lv, '')}{_SURGE_LABELS.get(lv, '-')}"

    return render_screening_table(results, columns=[
        ("順位", "---:", lambda r, row: str(r)),
        ("銘柄", ":-----", lambda r, row: _build_label(row)),
        ("株価", "-----:", _price_cell),
        ("50MA乖離", "-------:", lambda r, row: _fmt_pct(row.get("ma50_deviation"))),
        ("出来高比", "-------:", lambda r, row: _fmt_float(row.get("volume_ratio"), decimals=2)),
        ("RSI", "----:", lambda r, row: _fmt_float(row.get("rsi"), decimals=1)),
        ("52w高値比", "--------:", lambda r, row: _fmt_pct(row.get("high_change_pct"))),
        ("スコア", "------:", lambda r, row: _fmt_float(row.get("surge_score"), decimals=0)),
        ("レベル", ":------:", _level),
    ], empty_msg="モメンタム条件に合致する銘柄が見つかりませんでした。", legends=[
        "**レベル**: \U0001f7e2加速(+10~15%)=エントリー好機 / \U0001f7e1急騰(+15~30%)=勢い継続 / \U0001f534過熱(+30%超)=\u26a0\ufe0f利確注意",
    ])


# ---------------------------------------------------------------------------
# Auto-theme header (not a table formatter)
# ---------------------------------------------------------------------------

def format_auto_theme_header(themes: list[dict], skipped: list[dict] | None = None) -> str:
    """Format Grok trending themes header (KIK-440)."""
    from datetime import date
    lines = [f"\U0001f525 Grok が検出したトレンドテーマ（{date.today().isoformat()}）\n"]
    for i, t in enumerate(themes, 1):
        conf_pct = int(t.get("confidence", 0) * 100)
        lines.append(f"{i}. **{t['theme']}** (信頼度: {conf_pct}%)")
        if t.get("reason"):
            lines.append(f"   {t['reason']}")
        lines.append("")
    if skipped:
        lines.append(f"\u203b 未対応テーマ（スキップ）: {', '.join(t['theme'] for t in skipped)}\n")
    lines.append("---\n")
    return "\n".join(lines)
