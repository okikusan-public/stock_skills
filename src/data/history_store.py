"""History store -- save and load screening/report/trade/health/research JSON files."""

import json
import os
import re as _re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_filename(s: str) -> str:
    """Replace '.' and '/' with '_' for filesystem-safe filenames."""
    return s.replace(".", "_").replace("/", "_")


def _history_dir(category: str, base_dir: str) -> Path:
    """Return category sub-directory, creating it if needed."""
    d = Path(base_dir) / category
    d.mkdir(parents=True, exist_ok=True)
    return d


class _HistoryEncoder(json.JSONEncoder):
    """Custom encoder for numpy types and NaN/Inf values."""

    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _sanitize(obj):
    """Recursively convert numpy types and NaN/Inf to JSON-safe values."""
    import math
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


# ---------------------------------------------------------------------------
# Embedding helper (KIK-420)
# ---------------------------------------------------------------------------

def _build_embedding(category: str, **kwargs) -> tuple[str, list[float] | None]:
    """Build semantic summary and get embedding vector.

    Returns (summary_text, embedding_vector). Both may be empty/None on failure.
    """
    try:
        from src.data import summary_builder, embedding_client
    except ImportError:
        return ("", None)

    builders = {
        "screen": lambda: summary_builder.build_screen_summary(
            kwargs.get("date", ""), kwargs.get("preset", ""),
            kwargs.get("region", ""), kwargs.get("top_symbols")),
        "report": lambda: summary_builder.build_report_summary(
            kwargs.get("symbol", ""), kwargs.get("name", ""),
            kwargs.get("score", 0), kwargs.get("verdict", ""),
            kwargs.get("sector", "")),
        "trade": lambda: summary_builder.build_trade_summary(
            kwargs.get("date", ""), kwargs.get("trade_type", ""),
            kwargs.get("symbol", ""), kwargs.get("shares", 0),
            kwargs.get("memo", "")),
        "health": lambda: summary_builder.build_health_summary(
            kwargs.get("date", ""), kwargs.get("summary")),
        "research": lambda: summary_builder.build_research_summary(
            kwargs.get("research_type", ""), kwargs.get("target", ""),
            kwargs.get("result", {})),
        "market_context": lambda: summary_builder.build_market_context_summary(
            kwargs.get("date", ""), kwargs.get("indices"),
            kwargs.get("grok_research")),
        "note": lambda: summary_builder.build_note_summary(
            kwargs.get("symbol", ""), kwargs.get("note_type", ""),
            kwargs.get("content", "")),
        "watchlist": lambda: summary_builder.build_watchlist_summary(
            kwargs.get("name", ""), kwargs.get("symbols")),
        "stress_test": lambda: summary_builder.build_stress_test_summary(
            kwargs.get("date", ""), kwargs.get("scenario", ""),
            kwargs.get("portfolio_impact", 0), kwargs.get("symbol_count", 0)),
        "forecast": lambda: summary_builder.build_forecast_summary(
            kwargs.get("date", ""), kwargs.get("optimistic"),
            kwargs.get("base"), kwargs.get("pessimistic"),
            kwargs.get("symbol_count", 0)),
    }
    builder = builders.get(category)
    if builder is None:
        return ("", None)

    try:
        text = builder()
        emb = embedding_client.get_embedding(text) if text else None
        return (text, emb)
    except Exception:
        return ("", None)


# ---------------------------------------------------------------------------
# Dual-write helper
# ---------------------------------------------------------------------------

def _dual_write_graph(graph_callable, embed_category: str, embed_kwargs: dict):
    """Execute Neo4j dual-write with graceful degradation.

    Args:
        graph_callable: Function that performs graph operations.
                       Called with (sem_summary, embedding) as arguments.
        embed_category: Category for _build_embedding()
        embed_kwargs: Keyword args for _build_embedding()
    """
    try:
        sem_summary, emb = _build_embedding(embed_category, **embed_kwargs)
        graph_callable(sem_summary, emb)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Save functions
# ---------------------------------------------------------------------------

def save_screening(
    preset: str,
    region: str,
    results: list[dict],
    sector: str | None = None,
    base_dir: str = "data/history",
) -> str:
    """Save screening results to JSON.

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    identifier = f"{_safe_filename(region)}_{_safe_filename(preset)}"
    filename = f"{today}_{identifier}.json"

    payload = {
        "category": "screen",
        "date": today,
        "timestamp": now,
        "preset": preset,
        "region": region,
        "sector": sector,
        "count": len(results),
        "results": results,
        "_saved_at": now,
    }

    d = _history_dir("screen", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/420) -- graceful degradation
    symbols = [r.get("symbol") for r in results if r.get("symbol")]

    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_screen, merge_stock
        for r in results:
            sym = r.get("symbol")
            if sym:
                merge_stock(symbol=sym, name=r.get("name", ""), sector=r.get("sector", ""))
        merge_screen(today, preset, region, len(results), symbols,
                     semantic_summary=sem_summary, embedding=emb)

    _dual_write_graph(
        _graph_write, "screen",
        dict(date=today, preset=preset, region=region, top_symbols=symbols[:5]),
    )

    return str(path.resolve())


def save_report(
    symbol: str,
    data: dict,
    score: float,
    verdict: str,
    base_dir: str = "data/history",
) -> str:
    """Save a stock report to JSON.

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    identifier = _safe_filename(symbol)
    filename = f"{today}_{identifier}.json"

    payload = {
        "category": "report",
        "date": today,
        "timestamp": now,
        "symbol": symbol,
        "name": data.get("name"),
        "sector": data.get("sector"),
        "industry": data.get("industry"),
        "price": data.get("price"),
        "per": data.get("per"),
        "pbr": data.get("pbr"),
        "dividend_yield": data.get("dividend_yield"),
        "roe": data.get("roe"),
        "roa": data.get("roa"),
        "revenue_growth": data.get("revenue_growth"),
        "market_cap": data.get("market_cap"),
        "value_score": score,
        "verdict": verdict,
        "_saved_at": now,
    }

    d = _history_dir("report", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/413/420) -- graceful degradation
    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_report_full, merge_stock
        merge_stock(symbol=symbol, name=data.get("name", ""), sector=data.get("sector", ""))
        merge_report_full(
            report_date=today, symbol=symbol, score=score, verdict=verdict,
            price=data.get("price", 0), per=data.get("per", 0),
            pbr=data.get("pbr", 0), dividend_yield=data.get("dividend_yield", 0),
            roe=data.get("roe", 0), market_cap=data.get("market_cap", 0),
            semantic_summary=sem_summary, embedding=emb,
        )

    _dual_write_graph(
        _graph_write, "report",
        dict(symbol=symbol, name=data.get("name", ""),
             score=score, verdict=verdict, sector=data.get("sector", "")),
    )

    # KIK-434: AI graph linking (graceful degradation)
    try:
        from src.data.graph_linker import link_report
        _rid = f"report_{today}_{symbol}"
        link_report(_rid, symbol, data.get("sector", ""), score, verdict)
    except Exception:
        pass

    return str(path.resolve())


def save_trade(
    symbol: str,
    trade_type: str,
    shares: int,
    price: float,
    currency: str,
    date_str: str,
    memo: str = "",
    base_dir: str = "data/history",
    sell_price: Optional[float] = None,
    realized_pnl: Optional[float] = None,
    pnl_rate: Optional[float] = None,
    hold_days: Optional[int] = None,
    cost_price: Optional[float] = None,
) -> str:
    """Save a trade record to JSON.

    Returns the absolute path of the saved file.

    Parameters
    ----------
    sell_price : float, optional
        売却単価（KIK-441）。sell 時のみ。
    realized_pnl : float, optional
        実現損益（KIK-441）。
    pnl_rate : float, optional
        損益率（KIK-441）。
    hold_days : int, optional
        保有日数（KIK-441）。
    cost_price : float, optional
        取得単価（KIK-441）。sell 時に保存。
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    identifier = f"{trade_type}_{_safe_filename(symbol)}"
    filename = f"{today}_{identifier}.json"

    payload: dict = {
        "category": "trade",
        "date": date_str,
        "timestamp": now,
        "symbol": symbol,
        "trade_type": trade_type,
        "shares": shares,
        "price": price,
        "currency": currency,
        "memo": memo,
        "_saved_at": now,
    }

    # KIK-441: sell P&L フィールド
    if sell_price is not None:
        payload["sell_price"] = sell_price
    if realized_pnl is not None:
        payload["realized_pnl"] = realized_pnl
    if pnl_rate is not None:
        payload["pnl_rate"] = pnl_rate
    if hold_days is not None:
        payload["hold_days"] = hold_days
    if cost_price is not None:
        payload["cost_price"] = cost_price

    d = _history_dir("trade", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/420) -- graceful degradation
    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_trade, merge_stock
        merge_stock(symbol=symbol)
        merge_trade(
            trade_date=date_str, trade_type=trade_type, symbol=symbol,
            shares=shares, price=price, currency=currency, memo=memo,
            semantic_summary=sem_summary, embedding=emb,
            sell_price=sell_price, realized_pnl=realized_pnl,
            hold_days=hold_days,
        )

    _dual_write_graph(
        _graph_write, "trade",
        dict(date=date_str, trade_type=trade_type,
             symbol=symbol, shares=shares, memo=memo),
    )

    return str(path.resolve())


def save_health(
    health_data: dict,
    base_dir: str = "data/history",
) -> str:
    """Save health check results to JSON.

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    filename = f"{today}_health.json"

    positions_out = []
    for pos in health_data.get("positions", []):
        positions_out.append({
            "symbol": pos.get("symbol"),
            "pnl_pct": pos.get("pnl_pct"),
            "trend": pos.get("trend_health", {}).get("trend", "不明"),
            "quality_label": pos.get("change_quality", {}).get("quality_label", "-"),
            "alert_level": pos.get("alert", {}).get("level", "none"),
        })

    summary_raw = health_data.get("summary", {})
    summary = {
        "total": summary_raw.get("total", len(positions_out)),
        "healthy": summary_raw.get("healthy", 0),
        "early_warning": summary_raw.get("early_warning", 0),
        "caution": summary_raw.get("caution", 0),
        "exit": summary_raw.get("exit", 0),
    }

    payload = {
        "category": "health",
        "date": today,
        "timestamp": now,
        "summary": summary,
        "positions": positions_out,
        "_saved_at": now,
    }

    d = _history_dir("health", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/420) -- graceful degradation
    symbols = [p.get("symbol") for p in health_data.get("positions", []) if p.get("symbol")]

    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_health
        merge_health(today, summary, symbols,
                     semantic_summary=sem_summary, embedding=emb)

    _dual_write_graph(
        _graph_write, "health",
        dict(date=today, summary=summary),
    )

    return str(path.resolve())


def _build_research_summary(research_type: str, result: dict) -> str:
    """Build a summary string from research result for Neo4j storage (KIK-416).

    Extracts key information from grok_research and other fields to create
    a concise summary (max 200 chars) for GraphRAG queries.
    """
    grok = result.get("grok_research")
    if grok is None or not isinstance(grok, dict):
        grok = {}

    parts: list[str] = []

    if research_type == "stock":
        # Name + first news headline + sentiment score + value_score
        name = result.get("name", "")
        if name:
            parts.append(name)
        news = grok.get("recent_news") or result.get("news") or []
        if news and isinstance(news, list) and isinstance(news[0], (str, dict)):
            headline = news[0] if isinstance(news[0], str) else news[0].get("title", "")
            headline = headline.split("<")[0].strip()  # strip grok citation tags
            if headline:
                parts.append(headline[:80])
        xs = grok.get("x_sentiment") or result.get("x_sentiment") or {}
        if isinstance(xs, dict) and xs.get("score") is not None:
            parts.append(f"Xセンチメント{xs['score']}")
        vs = result.get("value_score")
        if vs is not None:
            parts.append(f"スコア{vs}")

    elif research_type == "market":
        # price_action + sentiment score
        pa = grok.get("price_action", "")
        if pa:
            if isinstance(pa, list):
                pa = "\n".join(pa)
            pa_clean = pa.split("<")[0].strip()
            parts.append(pa_clean[:120])
        sent = grok.get("sentiment") or {}
        if isinstance(sent, dict) and sent.get("score") is not None:
            parts.append(f"センチメント{sent['score']}")

    elif research_type == "industry":
        # trends
        trends = grok.get("trends", "")
        if trends:
            if isinstance(trends, list):
                trends = "\n".join(trends)
            trends_clean = trends.split("<")[0].strip()
            parts.append(trends_clean[:120])

    elif research_type == "business":
        # name + overview
        name = result.get("name", "")
        if name:
            parts.append(name)
        overview = grok.get("overview", "")
        if overview:
            if isinstance(overview, list):
                overview = "\n".join(overview)
            overview_clean = overview.split("<")[0].strip()
            parts.append(overview_clean[:120])

    summary = ". ".join(parts)
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return summary


def save_research(
    research_type: str,
    target: str,
    result: dict,
    base_dir: str = "data/history",
) -> str:
    """Save research results to JSON (KIK-405).

    Parameters
    ----------
    research_type : str
        "stock", "industry", "market", or "business".
    target : str
        Symbol (e.g. "7203.T") or theme name (e.g. "半導体").
    result : dict
        Return value from researcher.research_*() functions.
    base_dir : str
        Root history directory.

    Returns
    -------
    str
        Absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    identifier = f"{_safe_filename(research_type)}_{_safe_filename(target)}"
    filename = f"{today}_{identifier}.json"

    payload = {
        "category": "research",
        "date": today,
        "timestamp": now,
        "research_type": research_type,
        "target": target,
        **{k: v for k, v in result.items() if k != "type"},
        "_saved_at": now,
    }

    d = _history_dir("research", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/413/416/420) -- graceful degradation
    summary = result.get("summary", "") or _build_research_summary(research_type, result)

    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_research_full, merge_stock, link_research_supersedes
        if research_type in ("stock", "business"):
            merge_stock(symbol=target, name=result.get("name", ""))
        merge_research_full(
            research_date=today, research_type=research_type,
            target=target, summary=summary,
            grok_research=result.get("grok_research"),
            x_sentiment=result.get("x_sentiment"),
            news=result.get("news"),
            semantic_summary=sem_summary, embedding=emb,
        )
        link_research_supersedes(research_type, target)

    _dual_write_graph(
        _graph_write, "research",
        dict(research_type=research_type, target=target, result=result),
    )

    # KIK-434: AI graph linking (graceful degradation)
    try:
        from src.data.graph_linker import link_research
        _rid = f"research_{today}_{research_type}_{_re.sub(r'[^a-zA-Z0-9]', '_', target)}"
        link_research(_rid, research_type, target, summary)
    except Exception:
        pass

    return str(path.resolve())


def save_market_context(
    context: dict,
    base_dir: str = "data/history",
) -> str:
    """Save market context snapshot to JSON (KIK-405).

    Parameters
    ----------
    context : dict
        Market context data. Expected key: "indices" (list of dicts from
        get_macro_indicators) or a flat dict with indicator values.
    base_dir : str
        Root history directory.

    Returns
    -------
    str
        Absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    filename = f"{today}_context.json"

    payload = {
        "category": "market_context",
        "date": today,
        "timestamp": now,
        **context,
        "_saved_at": now,
    }

    d = _history_dir("market_context", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-399/413/420) -- graceful degradation
    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_market_context_full
        merge_market_context_full(
            context_date=today, indices=context.get("indices", []),
            grok_research=context.get("grok_research"),
            semantic_summary=sem_summary, embedding=emb,
        )

    _dual_write_graph(
        _graph_write, "market_context",
        dict(date=today, indices=context.get("indices", []),
             grok_research=context.get("grok_research")),
    )

    return str(path.resolve())


def save_stress_test(
    scenario: str,
    symbols: list[str],
    portfolio_impact: float,
    per_stock_impacts: list[dict] | None = None,
    var_result: dict | None = None,
    high_correlation_pairs: list | None = None,
    concentration: dict | None = None,
    recommendations: list | None = None,
    base_dir: str = "data/history",
) -> str:
    """Save stress test results to JSON (KIK-428).

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    identifier = _safe_filename(scenario)
    filename = f"{today}_{identifier}.json"

    payload = {
        "category": "stress_test",
        "date": today,
        "timestamp": now,
        "scenario": scenario,
        "symbols": symbols,
        "portfolio_impact": portfolio_impact,
        "per_stock_impacts": per_stock_impacts or [],
        "var_result": var_result or {},
        "high_correlation_pairs": high_correlation_pairs or [],
        "concentration": concentration or {},
        "recommendations": recommendations or [],
        "_saved_at": now,
    }

    d = _history_dir("stress_test", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-428) -- graceful degradation
    var = var_result or {}

    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_stress_test, merge_stock
        for sym in symbols:
            merge_stock(symbol=sym)
        merge_stress_test(
            test_date=today, scenario=scenario,
            portfolio_impact=portfolio_impact, symbols=symbols,
            var_95=var.get("var_95_daily", 0), var_99=var.get("var_99_daily", 0),
            semantic_summary=sem_summary, embedding=emb,
        )

    _dual_write_graph(
        _graph_write, "stress_test",
        dict(date=today, scenario=scenario,
             portfolio_impact=portfolio_impact, symbol_count=len(symbols)),
    )

    return str(path.resolve())


def save_forecast(
    positions: list[dict],
    total_value_jpy: float = 0,
    base_dir: str = "data/history",
) -> str:
    """Save forecast results to JSON (KIK-428).

    Parameters
    ----------
    positions : list[dict]
        Per-position forecast data with optimistic/base/pessimistic returns.
    total_value_jpy : float
        Total portfolio value in JPY.
    base_dir : str
        Root history directory.

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    filename = f"{today}_forecast.json"

    # Extract portfolio-level 3-scenario returns from positions
    symbols = [p.get("symbol", "") for p in positions if p.get("symbol")]
    opt_returns = [p.get("optimistic", 0) for p in positions if p.get("symbol")]
    base_returns = [p.get("base", 0) for p in positions if p.get("symbol")]
    pess_returns = [p.get("pessimistic", 0) for p in positions if p.get("symbol")]
    avg_opt = sum(opt_returns) / len(opt_returns) if opt_returns else 0
    avg_base = sum(base_returns) / len(base_returns) if base_returns else 0
    avg_pess = sum(pess_returns) / len(pess_returns) if pess_returns else 0

    payload = {
        "category": "forecast",
        "date": today,
        "timestamp": now,
        "portfolio": {
            "optimistic": avg_opt,
            "base": avg_base,
            "pessimistic": avg_pess,
        },
        "positions": positions,
        "total_value_jpy": total_value_jpy,
        "_saved_at": now,
    }

    d = _history_dir("forecast", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)

    # Neo4j dual-write (KIK-428) -- graceful degradation
    def _graph_write(sem_summary, emb):
        from src.data.graph_store import merge_forecast, merge_stock
        for sym in symbols:
            merge_stock(symbol=sym)
        merge_forecast(
            forecast_date=today, optimistic=avg_opt, base=avg_base,
            pessimistic=avg_pess, symbols=symbols,
            total_value_jpy=total_value_jpy,
            semantic_summary=sem_summary, embedding=emb,
        )

    _dual_write_graph(
        _graph_write, "forecast",
        dict(date=today, optimistic=avg_opt, base=avg_base,
             pessimistic=avg_pess, symbol_count=len(symbols)),
    )

    return str(path.resolve())


# ---------------------------------------------------------------------------
# Load functions
# ---------------------------------------------------------------------------

def load_history(
    category: str,
    days_back: int | None = None,
    base_dir: str = "data/history",
) -> list[dict]:
    """Load history files for a category, sorted newest-first.

    Parameters
    ----------
    category : str
        "screen", "report", "trade", or "health"
    days_back : int | None
        If set, only return files from the last N days.
    base_dir : str
        Root history directory.

    Returns
    -------
    list[dict]
        Parsed JSON contents, sorted by date descending.
    """
    d = Path(base_dir) / category
    if not d.exists():
        return []

    cutoff = None
    if days_back is not None:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    results = []
    for fp in sorted(d.glob("*.json"), reverse=True):
        # Extract date prefix from filename (YYYY-MM-DD_...)
        fname = fp.name
        file_date = fname[:10]  # YYYY-MM-DD

        if cutoff is not None and file_date < cutoff:
            continue

        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            results.append(data)
        except (json.JSONDecodeError, OSError):
            # Skip corrupted files
            continue

    return results


def list_history_files(
    category: str,
    base_dir: str = "data/history",
) -> list[str]:
    """List history file paths for a category, sorted newest-first.

    Returns
    -------
    list[str]
        Absolute file paths, sorted by date descending.
    """
    d = Path(base_dir) / category
    if not d.exists():
        return []

    return [
        str(fp.resolve())
        for fp in sorted(d.glob("*.json"), reverse=True)
    ]
