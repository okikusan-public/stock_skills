"""Proactive action suggestions based on accumulated knowledge graph (KIK-435).

Rule-based triggers — no LLM required.
Graceful degradation: returns empty list when Neo4j unavailable or any exception occurs.

Trigger categories:
  Time:        thesis note >90d old, last health check >14d ago, earnings within 7d,
               theme staleness >90d (KIK-605)
  State:       recurring screening picks, concern notes, held stock w/ new report
  Contextual:  research sector matches held stocks
  Context:     execution result keyword matching (KIK-465)

KIK-513: ProactiveEngine accepts an optional ``graph_reader`` parameter
(GraphReader Protocol) for dependency injection. When omitted, falls back to
importing graph_query functions directly (backward compatible).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.core._thresholds import th

if TYPE_CHECKING:
    from src.core.ports.graph import GraphReader

_THESIS_REVIEW_DAYS = 90   # thesis note older than this → suggest review
_HEALTH_STALE_DAYS  = 14   # no health check for N days → suggest check
_HEALTH_HIGH_DAYS   = 30   # > this → urgency=high
_EARNINGS_WARN_DAYS = 7    # upcoming earnings within N days → warn
_RECURRING_MIN      = 3    # screened N+ times → suggest deeper report

# ---------------------------------------------------------------------------
# Context-based trigger patterns (KIK-465)
# ---------------------------------------------------------------------------

_CONTEXT_PATTERNS: dict[str, dict] = {
    "energy": {
        "keywords": ["エネルギー", "原油", "石油", "天然ガス", "energy", "oil"],
        "emoji": "\u26a1",
        "title": "エネルギーセクターの確認",
        "command_hint": "screen-stocks --sector Energy",
    },
    "tech_weak": {
        "keywords": ["テック軟調", "ハイテク下落", "テクノロジー下落", "tech decline"],
        "emoji": "\U0001f4c9",
        "title": "テック銘柄のリスク確認",
        "command_hint": "stress-test --scenario テック暴落",
    },
    "gold": {
        "keywords": ["金急騰", "金価格", "ゴールド", "gold"],
        "emoji": "\U0001f947",
        "title": "コモディティ関連の影響確認",
        "command_hint": "stress-test",
    },
    "rate": {
        "keywords": ["利上げ", "金利上昇", "rate hike", "利下げ", "金利低下"],
        "emoji": "\U0001f3e6",
        "title": "金利変動のPF影響確認",
        "command_hint": "stress-test --scenario 日銀利上げ",
    },
    "earnings": {
        "keywords": ["決算", "好決算", "悪決算", "earnings", "上方修正", "下方修正"],
        "emoji": "\U0001f4ca",
        "title": "決算関連銘柄のフォローアップ",
        "command_hint": "stock-report",
    },
    "health_warning": {
        "keywords": ["警戒", "EXIT", "損切り", "バリュートラップ", "デッドクロス"],
        "emoji": "\U0001f6a8",
        "title": "警戒銘柄の対応検討",
        "command_hint": "screen-stocks --preset alpha",
    },
    "screening_result": {
        "keywords": ["スクリーニング完了", "銘柄発見", "上位ランクイン"],
        "emoji": "\U0001f50d",
        "title": "上位銘柄の詳細分析",
        "command_hint": "stock-report",
    },
}


class ProactiveEngine:
    """Generate proactive next-action suggestions from the knowledge graph.

    KIK-513: Accepts an optional ``graph_reader`` (GraphReader Protocol).
    When not provided, imports from src.data.graph_query directly (backward compatible).
    """

    def __init__(self, graph_reader: GraphReader | None = None) -> None:
        self._graph_reader = graph_reader

    def get_suggestions(
        self,
        context: str = "",
        symbol: str = "",
        sector: str = "",
    ) -> list[dict]:
        """Return up to 3 suggestions sorted by urgency (high > medium > low).

        Each item: {emoji, title, reason, command_hint, urgency}
        """
        suggestions: list[dict] = []
        suggestions += self._check_time_triggers()
        suggestions += self._check_state_triggers(symbol)
        suggestions += self._check_contextual_triggers(sector)
        suggestions += self._check_context_triggers(context)
        suggestions += self._check_theme_staleness()

        # Sort by urgency, deduplicate by title
        _order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: _order.get(s.get("urgency", "low"), 2))
        seen: set[str] = set()
        result: list[dict] = []
        for s in suggestions:
            key = s.get("title", "")
            if key not in seen:
                seen.add(key)
                result.append(s)
        return result[:3]

    # ------------------------------------------------------------------
    # Time triggers
    # ------------------------------------------------------------------

    def _check_time_triggers(self) -> list[dict]:
        out: list[dict] = []

        # Health check staleness
        try:
            if self._graph_reader is not None:
                last_hc = self._graph_reader.get_last_health_check_date()
            else:
                from src.data.graph_query import get_last_health_check_date
                last_hc = get_last_health_check_date()
            if last_hc is None:
                out.append({
                    "emoji": "📋",
                    "title": "ヘルスチェックの実施",
                    "reason": "ヘルスチェックの記録がありません",
                    "command_hint": "portfolio health",
                    "urgency": "medium",
                })
            else:
                delta = (date.today() - date.fromisoformat(last_hc)).days
                if delta >= _HEALTH_STALE_DAYS:
                    out.append({
                        "emoji": "📋",
                        "title": "ヘルスチェックの実施",
                        "reason": f"最終チェックから{delta}日経過",
                        "command_hint": "portfolio health",
                        "urgency": "high" if delta >= _HEALTH_HIGH_DAYS else "medium",
                    })
        except Exception:
            pass

        # Old thesis notes
        try:
            if self._graph_reader is not None:
                old_theses = self._graph_reader.get_old_thesis_notes(older_than_days=_THESIS_REVIEW_DAYS)
            else:
                from src.data.graph_query import get_old_thesis_notes
                old_theses = get_old_thesis_notes(older_than_days=_THESIS_REVIEW_DAYS)
            for note in old_theses[:1]:
                sym = note.get("symbol") or "保有銘柄"
                days = note.get("days_old", _THESIS_REVIEW_DAYS)
                out.append({
                    "emoji": "🔄",
                    "title": f"{sym}の投資テーゼを見直す",
                    "reason": f"テーゼ記録から{days}日経過（要再検証）",
                    "command_hint": (
                        f"investment-note list --symbol {sym}"
                        if sym != "保有銘柄" else "investment-note list --type thesis"
                    ),
                    "urgency": "medium",
                })
        except Exception:
            pass

        # Upcoming earnings events
        try:
            if self._graph_reader is not None:
                events = self._graph_reader.get_upcoming_events(within_days=_EARNINGS_WARN_DAYS)
            else:
                from src.data.graph_query import get_upcoming_events
                events = get_upcoming_events(within_days=_EARNINGS_WARN_DAYS)
            for ev in events[:1]:
                ev_date = ev.get("date", "")
                ev_text = str(ev.get("text", ""))[:60]
                out.append({
                    "emoji": "📅",
                    "title": "決算イベントが近い",
                    "reason": f"{ev_date} に予定: {ev_text} — 直前のレポート確認を推奨",
                    "command_hint": "market-research market",
                    "urgency": "high",
                })
        except Exception:
            pass

        return out

    # ------------------------------------------------------------------
    # State triggers
    # ------------------------------------------------------------------

    def _check_state_triggers(self, symbol: str = "") -> list[dict]:
        out: list[dict] = []

        # Recurring screening picks
        try:
            if self._graph_reader is not None:
                picks = self._graph_reader.get_recurring_picks(min_count=_RECURRING_MIN)
            else:
                from src.data.graph_query import get_recurring_picks
                picks = get_recurring_picks(min_count=_RECURRING_MIN)
            for pick in picks[:1]:
                sym = pick.get("symbol", "")
                cnt = pick.get("count", _RECURRING_MIN)
                out.append({
                    "emoji": "🔍",
                    "title": f"{sym}の詳細分析",
                    "reason": f"スクリーニングで{cnt}回上位にランクイン",
                    "command_hint": f"stock-report {sym}",
                    "urgency": "medium",
                })
        except Exception:
            pass

        # Concern notes
        try:
            if self._graph_reader is not None:
                concerns = self._graph_reader.get_concern_notes(limit=1)
            else:
                from src.data.graph_query import get_concern_notes
                concerns = get_concern_notes(limit=1)
            for c in concerns:
                sym = c.get("symbol") or ""
                days = c.get("days_old", 0)
                sym_display = sym if sym else "銘柄"
                out.append({
                    "emoji": "⚠️",
                    "title": f"{sym_display}の懸念メモを再確認",
                    "reason": f"{days}日前に懸念を記録済み — 状況変化を確認",
                    "command_hint": (
                        f"investment-note list --symbol {sym}"
                        if sym else "investment-note list --type concern"
                    ),
                    "urgency": "medium",
                })
        except Exception:
            pass

        return out

    # ------------------------------------------------------------------
    # Contextual triggers
    # ------------------------------------------------------------------

    def _check_contextual_triggers(self, sector: str = "") -> list[dict]:
        out: list[dict] = []
        if not sector:
            return out
        try:
            if self._graph_reader is not None:
                research = self._graph_reader.get_industry_research_for_linking(sector, days=14, limit=1)
                if not research:
                    return out
                holdings = self._graph_reader.get_current_holdings()
            else:
                from src.data.graph_query import get_current_holdings, get_industry_research_for_linking
                research = get_industry_research_for_linking(sector, days=14, limit=1)
                if not research:
                    return out
                holdings = get_current_holdings()
            held_sectors = {h.get("sector", "") for h in holdings}
            if sector in held_sectors:
                out.append({
                    "emoji": "💡",
                    "title": f"{sector}セクターの最新リサーチがあります",
                    "reason": "保有銘柄のセクターに関連する直近リサーチを検出",
                    "command_hint": f"market-research industry {sector}",
                    "urgency": "low",
                })
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------
    # Context triggers (KIK-465) — keyword matching on execution results
    # ------------------------------------------------------------------

    def _check_context_triggers(self, context: str = "") -> list[dict]:
        """Generate suggestions based on execution result context."""
        if not context:
            return []
        out: list[dict] = []
        context_lower = context.lower()
        for _key, pattern in _CONTEXT_PATTERNS.items():
            if any(kw.lower() in context_lower for kw in pattern["keywords"]):
                out.append({
                    "emoji": pattern["emoji"],
                    "title": pattern["title"],
                    "reason": f"実行結果に関連: {context[:60]}",
                    "command_hint": pattern["command_hint"],
                    "urgency": "low",
                })
        return out[:2]

    # ------------------------------------------------------------------
    # Theme staleness trigger (KIK-605)
    # ------------------------------------------------------------------

    def _check_theme_staleness(self) -> list[dict]:
        """Suggest re-validating themes when PF holds themed stocks with stale themes."""
        stale_days = int(th("theme_balance", "theme_stale_days", 90))
        out: list[dict] = []
        try:
            # Get current holdings
            if self._graph_reader is not None:
                holdings = self._graph_reader.get_current_holdings()
            else:
                from src.data.graph_query import get_current_holdings
                holdings = get_current_holdings()
            if not holdings:
                return out

            # Get themes for held symbols
            symbols = [h.get("symbol", "") for h in holdings if h.get("symbol")]
            if not symbols:
                return out

            try:
                from src.data.graph_query import get_themes_for_symbols_batch
                themes_map = get_themes_for_symbols_batch(symbols)
            except Exception:
                return out

            if not themes_map:
                return out

            # Collect unique themes held in PF
            held_themes: set[str] = set()
            for sym_themes in themes_map.values():
                for t in sym_themes:
                    held_themes.add(t)

            if not held_themes:
                return out

            # Check theme node freshness — look for Theme nodes with updated_at
            try:
                from src.data.graph_query._common import _get_driver
                driver = _get_driver()
                if driver is None:
                    return out
                with driver.session() as session:
                    result = session.run(
                        "MATCH (t:Theme) WHERE t.name IN $names "
                        "RETURN t.name AS name, t.updated_at AS updated_at",
                        names=list(held_themes),
                    )
                    today = date.today()
                    for record in result:
                        name = record["name"]
                        updated = record["updated_at"]
                        if updated is None:
                            # No updated_at → treat as stale
                            out.append({
                                "emoji": "\U0001f4c5",
                                "title": f"テーマ「{name}」の再検証",
                                "reason": f"テーマの鮮度情報なし — PF銘柄が属するテーマの再検証を推奨",
                                "command_hint": f"screen-stocks --auto-theme",
                                "urgency": "medium",
                            })
                        else:
                            try:
                                updated_date = date.fromisoformat(str(updated)[:10])
                                delta = (today - updated_date).days
                                if delta >= stale_days:
                                    out.append({
                                        "emoji": "\U0001f4c5",
                                        "title": f"テーマ「{name}」の再検証",
                                        "reason": f"テーマ更新から{delta}日経過 — トレンド変化の確認を推奨",
                                        "command_hint": f"screen-stocks --auto-theme",
                                        "urgency": "medium",
                                    })
                            except (ValueError, TypeError):
                                pass
            except Exception:
                pass
        except Exception:
            pass
        return out[:1]  # At most one theme staleness suggestion


# ---------------------------------------------------------------------------
# Public convenience functions
# ---------------------------------------------------------------------------

def get_suggestions(
    context: str = "",
    symbol: str = "",
    sector: str = "",
    *,
    graph_reader: GraphReader | None = None,
) -> list[dict]:
    """Return proactive suggestions from the knowledge graph (KIK-435).

    Parameters
    ----------
    graph_reader : GraphReader, optional
        Optional dependency-injected graph reader (KIK-513 DIP).
        When None, falls back to importing graph_query functions directly.
    """
    return ProactiveEngine(graph_reader=graph_reader).get_suggestions(
        context=context, symbol=symbol, sector=sector
    )


def format_suggestions(suggestions: list[dict]) -> str:
    """Format suggestion list as markdown for display after skill output."""
    if not suggestions:
        return ""
    lines = [f"\n---\n💡 **次のアクション提案** ({len(suggestions)}件)\n"]
    for i, s in enumerate(suggestions, 1):
        emoji = s.get("emoji", "💡")
        title = s.get("title", "")
        reason = s.get("reason", "")
        cmd = s.get("command_hint", "")
        lines.append(f"{i}. {emoji} **{title}**")
        lines.append(f"   {reason}")
        if cmd:
            lines.append(f"   → `{cmd}` を実行してください")
        lines.append("")
    return "\n".join(lines)
