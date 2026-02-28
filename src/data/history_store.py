"""History store -- save and load screening/report/trade/health/research JSON files.

Sub-modules (KIK-512):
  - history_helpers.py: Internal helpers (_sanitize, _build_embedding, _dual_write_graph)
  - history_save.py: All save_* functions
  - history_load.py: load_history, list_history_files

This module re-exports everything for backward compatibility.
"""

# Re-export Path for backward compat (tests may patch src.data.history_store.Path)
from pathlib import Path  # noqa: F401

# Re-export helpers (used by note_manager, manage_watchlist, backfill_embeddings)
from src.data.history_helpers import (  # noqa: F401
    _safe_filename,
    _history_dir,
    _HistoryEncoder,
    _sanitize,
    _build_embedding,
    _dual_write_graph,
)

# Re-export save functions
from src.data.history_save import (  # noqa: F401
    save_screening,
    save_report,
    save_trade,
    save_health,
    _build_research_summary,
    save_research,
    save_market_context,
    save_stress_test,
    save_forecast,
)

# Re-export load functions
from src.data.history_load import (  # noqa: F401
    load_history,
    list_history_files,
)
