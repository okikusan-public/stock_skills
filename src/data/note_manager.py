"""Note manager -- dual-write to JSON files and Neo4j (KIK-397).

Notes are investment memos (thesis, observation, concern, review, target)
attached to specific stocks. The JSON file is the master; Neo4j is a view.
"""

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional


_NOTES_DIR = "data/notes"
_VALID_TYPES = {"thesis", "observation", "concern", "review", "target", "lesson"}


def _notes_dir(base_dir: str = _NOTES_DIR) -> Path:
    d = Path(base_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_note(
    symbol: str,
    note_type: str,
    content: str,
    source: str = "",
    base_dir: str = _NOTES_DIR,
) -> dict:
    """Save a note to JSON file and Neo4j.

    Parameters
    ----------
    symbol : str
        Stock ticker (e.g., "7203.T").
    note_type : str
        One of: thesis, observation, concern, review, target.
    content : str
        The note text.
    source : str
        Where this note came from (e.g., "manual", "health-check", "report").
    base_dir : str
        Notes directory.

    Returns
    -------
    dict
        The saved note record.
    """
    if note_type not in _VALID_TYPES:
        raise ValueError(f"Invalid note type: {note_type}. Must be one of {_VALID_TYPES}")

    today = date.today().isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    note_id = f"note_{today}_{symbol}_{uuid.uuid4().hex[:8]}"

    note = {
        "id": note_id,
        "date": today,
        "timestamp": now,
        "symbol": symbol,
        "type": note_type,
        "content": content,
        "source": source,
    }

    # 1. Write to JSON file (master)
    d = _notes_dir(base_dir)
    safe_symbol = symbol.replace(".", "_").replace("/", "_")
    filename = f"{today}_{safe_symbol}_{note_type}.json"
    path = d / filename

    # Append to existing file if same date/symbol/type, else create new
    existing = []
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            existing = data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            existing = []

    existing.append(note)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # 2. Write to Neo4j (view) -- graceful degradation
    try:
        from src.data.graph_store import merge_note
        merge_note(
            note_id=note_id,
            note_date=today,
            note_type=note_type,
            content=content,
            symbol=symbol,
            source=source,
        )
    except Exception:
        pass  # Neo4j unavailable, JSON is the master

    return note


def load_notes(
    symbol: Optional[str] = None,
    note_type: Optional[str] = None,
    base_dir: str = _NOTES_DIR,
) -> list[dict]:
    """Load notes from JSON files.

    Parameters
    ----------
    symbol : str, optional
        Filter by stock symbol.
    note_type : str, optional
        Filter by note type.
    base_dir : str
        Notes directory.

    Returns
    -------
    list[dict]
        Notes sorted by date descending.
    """
    d = Path(base_dir)
    if not d.exists():
        return []

    all_notes = []
    for fp in d.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            notes = data if isinstance(data, list) else [data]
            all_notes.extend(notes)
        except (json.JSONDecodeError, OSError):
            continue

    # Filter
    if symbol:
        all_notes = [n for n in all_notes if n.get("symbol") == symbol]
    if note_type:
        all_notes = [n for n in all_notes if n.get("type") == note_type]

    # Sort by date descending
    all_notes.sort(key=lambda n: n.get("date", ""), reverse=True)
    return all_notes


def delete_note(
    note_id: str,
    base_dir: str = _NOTES_DIR,
) -> bool:
    """Delete a note by ID from JSON files.

    Returns True if found and deleted.
    """
    d = Path(base_dir)
    if not d.exists():
        return False

    for fp in d.glob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            notes = data if isinstance(data, list) else [data]
            filtered = [n for n in notes if n.get("id") != note_id]
            if len(filtered) < len(notes):
                if filtered:
                    with open(fp, "w", encoding="utf-8") as f:
                        json.dump(filtered, f, ensure_ascii=False, indent=2)
                else:
                    fp.unlink()
                return True
        except (json.JSONDecodeError, OSError):
            continue

    return False
