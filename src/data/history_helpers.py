"""Internal helpers for history store (KIK-512 split).

Contains serialization helpers, embedding builder, and dual-write helper.
"""

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


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
        if text and emb is None:
            logger.warning(
                "TEI unavailable: node saved without embedding (category=%s). "
                "Run 'python3 scripts/backfill_embeddings.py' later to backfill.",
                category,
            )
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
