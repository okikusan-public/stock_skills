"""History store -- save and load screening/report/trade/health/research JSON files."""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

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
) -> str:
    """Save a trade record to JSON.

    Returns the absolute path of the saved file.
    """
    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    identifier = f"{trade_type}_{_safe_filename(symbol)}"
    filename = f"{today}_{identifier}.json"

    payload = {
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

    d = _history_dir("trade", base_dir)
    path = d / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize(payload), f, ensure_ascii=False, indent=2)
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
    return str(path.resolve())


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
