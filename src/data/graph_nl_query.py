"""Natural language → graph query dispatcher (KIK-409 Phase 1).

Template-matching engine: regex patterns → graph_query.py functions → formatted markdown.
Returns None when no template matches or Neo4j is unavailable.
"""

import re
from typing import Optional

from src.data import graph_query


# ---------------------------------------------------------------------------
# Symbol extraction helpers
# ---------------------------------------------------------------------------

_SYMBOL_PATTERN = re.compile(r"(\d{4}\.[A-Z]+|[A-Z][A-Z0-9]{0,4}(?:\.[A-Z]{1,2})?)")



def _extract_symbol(text: str) -> Optional[str]:
    """Extract a ticker symbol from text (e.g. 7203.T, AAPL, D05.SI)."""
    m = _SYMBOL_PATTERN.search(text)
    return m.group(1) if m else None


def _extract_symbol_and_type(text: str) -> dict:
    """Extract symbol and research type from text."""
    symbol = _extract_symbol(text)
    rtype = "stock"
    if any(w in text for w in ("業界", "業種", "セクター", "industry")):
        rtype = "industry"
    elif any(w in text for w in ("市場", "マーケット", "相場", "market")):
        rtype = "market"
    elif any(w in text for w in ("ビジネス", "事業", "business")):
        rtype = "business"
    return {"symbol": symbol, "research_type": rtype}


# ---------------------------------------------------------------------------
# Templates: (pattern, query_type, param_extractor)
# ---------------------------------------------------------------------------

_TEMPLATES = [
    (r"前回|以前|過去.*レポート|直近.*レポート", "prior_report", _extract_symbol),
    (r"何回.*スクリーニング|繰り返し.*候補|頻出|常連|よく.*出", "recurring_picks", None),
    (r"リサーチ.*履歴|前に.*調べた|調査.*履歴", "research_chain", _extract_symbol_and_type),
    (r"最近.*相場|市況|マーケット.*コンテキスト|市場.*状況", "market_context", None),
    (r"取引.*履歴|売買.*記録|買った.*理由|トレード.*記録", "trade_context", _extract_symbol),
    (r"よく.*出.*買って.*ない|頻出.*未購入|買い忘れ", "recurring_picks", None),
    (r"メモ|ノート.*一覧|記録.*見せて|投資メモ", "notes", _extract_symbol),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), qtype, extractor) for pat, qtype, extractor in _TEMPLATES]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query(user_input: str) -> Optional[dict]:
    """Match user input to a template and execute the corresponding graph query.

    Returns:
        {"query_type": str, "result": any, "formatted": str} or None if no match.
    """
    for pattern, query_type, extractor in _COMPILED:
        if not pattern.search(user_input):
            continue

        params = {}
        if extractor is not None:
            extracted = extractor(user_input)
            if isinstance(extracted, dict):
                params = extracted
            else:
                params = {"symbol": extracted}

        result = _execute(query_type, params)
        if result is None:
            return None

        formatted = format_result(query_type, result, params)
        return {"query_type": query_type, "result": result, "formatted": formatted}

    return None


# ---------------------------------------------------------------------------
# Execution dispatcher
# ---------------------------------------------------------------------------

def _execute(query_type: str, params: dict):
    """Dispatch to the appropriate graph_query function."""
    if query_type == "prior_report":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_prior_report(symbol)

    if query_type == "recurring_picks":
        return graph_query.get_recurring_picks()

    if query_type == "research_chain":
        symbol = params.get("symbol")
        rtype = params.get("research_type", "stock")
        if not symbol:
            return None
        return graph_query.get_research_chain(rtype, symbol)

    if query_type == "market_context":
        return graph_query.get_recent_market_context()

    if query_type == "trade_context":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_trade_context(symbol)

    if query_type == "notes":
        symbol = params.get("symbol")
        if not symbol:
            return None
        return graph_query.get_trade_context(symbol)

    return None


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_result(query_type: str, result, params: dict) -> str:
    """Format query result as markdown."""
    formatter = _FORMATTERS.get(query_type)
    if formatter:
        return formatter(result, params)
    return str(result)


def _fmt_prior_report(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    if not result:
        return f"{symbol} の過去レポートは見つかりませんでした。"
    return (
        f"## {symbol} の前回レポート\n\n"
        f"- 日付: {result.get('date', '-')}\n"
        f"- スコア: {result.get('score', '-')}\n"
        f"- 判定: {result.get('verdict', '-')}\n"
    )


def _fmt_recurring_picks(result, params: dict) -> str:
    if not result:
        return "繰り返し候補に上がっている未購入銘柄はありません。"
    lines = ["## 繰り返し候補（未購入）\n", "| 銘柄 | 出現回数 | 最終日 |", "|:-----|:---------|:-------|"]
    for r in result:
        lines.append(f"| {r.get('symbol', '-')} | {r.get('count', 0)} | {r.get('last_date', '-')} |")
    return "\n".join(lines)


def _fmt_research_chain(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    rtype = params.get("research_type", "stock")
    if not result:
        return f"{symbol} ({rtype}) のリサーチ履歴は見つかりませんでした。"
    lines = [f"## {symbol} のリサーチ履歴 ({rtype})\n", "| 日付 | サマリー |", "|:-----|:---------|"]
    for r in result:
        summary = (r.get("summary") or "-")[:80]
        lines.append(f"| {r.get('date', '-')} | {summary} |")
    return "\n".join(lines)


def _fmt_market_context(result, params: dict) -> str:
    if not result:
        return "最近の市況データは見つかりませんでした。"
    date = result.get("date", "-")
    indices = result.get("indices", [])
    lines = [f"## 市況コンテキスト ({date})\n"]
    if indices:
        lines.append("| 指標 | 値 |")
        lines.append("|:-----|:---|")
        for idx in indices:
            if isinstance(idx, dict):
                lines.append(f"| {idx.get('name', '-')} | {idx.get('value', '-')} |")
            else:
                lines.append(f"| {idx} | - |")
    else:
        lines.append("指標データなし")
    return "\n".join(lines)


def _fmt_trade_context(result, params: dict) -> str:
    symbol = params.get("symbol", "?")
    trades = result.get("trades", [])
    notes = result.get("notes", [])
    if not trades and not notes:
        return f"{symbol} の取引履歴・メモは見つかりませんでした。"
    lines = [f"## {symbol} の取引コンテキスト\n"]
    if trades:
        lines.append("### 取引履歴\n")
        lines.append("| 日付 | 種別 | 株数 | 価格 |")
        lines.append("|:-----|:-----|:-----|:-----|")
        for t in trades:
            lines.append(f"| {t.get('date', '-')} | {t.get('type', '-')} | {t.get('shares', '-')} | {t.get('price', '-')} |")
    if notes:
        lines.append("\n### メモ\n")
        lines.append("| 日付 | タイプ | 内容 |")
        lines.append("|:-----|:-------|:-----|")
        for n in notes:
            content = (n.get("content") or "-")[:50]
            lines.append(f"| {n.get('date', '-')} | {n.get('type', '-')} | {content} |")
    return "\n".join(lines)


def _fmt_notes(result, params: dict) -> str:
    return _fmt_trade_context(result, params)


_FORMATTERS = {
    "prior_report": _fmt_prior_report,
    "recurring_picks": _fmt_recurring_picks,
    "research_chain": _fmt_research_chain,
    "market_context": _fmt_market_context,
    "trade_context": _fmt_trade_context,
    "notes": _fmt_notes,
}
