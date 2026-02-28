"""History store load/query functions (KIK-512 split)."""

import json
from datetime import date, timedelta
from pathlib import Path


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
